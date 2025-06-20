import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

from .models import Commit, ContributionStats, PullRequest
from .protocols import GitHubSource, ProgressReporter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LineStats:
    """Container for line statistics from pull requests."""

    lines_added: int
    lines_deleted: int
    pr_count: int = 0


@dataclass(frozen=True)
class RateLimit:
    limit: int
    remaining: int
    reset_at: datetime
    used: int
    node_count: int

    def seconds_until_reset(self) -> float:
        """Calculate seconds until rate limit resets."""
        return max(0, (self.reset_at - datetime.now(timezone.utc)).total_seconds())

    def needs_wait(self, threshold: int = 100) -> bool:
        """Check if we need to wait for rate limit reset."""
        return self.remaining < threshold


@dataclass(frozen=True)
class RequestConfig:
    base_url: str
    token: str
    timeout_seconds: int = 300
    min_remaining_threshold: int = 100
    safety_buffer: int = 10

    def headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v4+json",
            "User-Agent": "GitHub-GraphQL-Python-Client/1.0",
        }


@dataclass(frozen=True)
class YearRange:
    year: int

    def from_date(self) -> str:
        """Get ISO string for start of year."""
        return f"{self.year}-01-01T00:00:00Z"

    def to_date(self) -> str:
        """Get ISO string for end of year."""
        return f"{self.year}-12-31T23:59:59Z"


class GraphQLClient:
    def __init__(self, config: RequestConfig):
        self._config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limit: Optional[RateLimit] = None

    async def __aenter__(self) -> "GraphQLClient":
        """Async context manager entry."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self._config.timeout_seconds)
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        del exc_type, exc_val, exc_tb  # Unused parameters
        if self._session:
            await self._session.close()

    async def query(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a GraphQL query."""
        if not self._session:
            raise RuntimeError("Client not initialized. Use as async context manager.")

        await self._check_rate_limit()

        payload = {"query": query, "variables": variables or {}}

        async with self._session.post(
            self._config.base_url, json=payload, headers=self._config.headers()
        ) as response:
            self._rate_limit = self._extract_rate_limit(dict(response.headers))

            if response.status == 401:
                raise GitHubAPIError("Authentication failed. Check your token.")
            elif response.status == 403:
                raise GitHubAPIError("Forbidden. You may have exceeded rate limits.")
            elif response.status >= 400:
                error_text = await response.text()
                raise GitHubAPIError(f"HTTP {response.status}: {error_text}")

            try:
                data = await response.json()
            except json.JSONDecodeError as e:
                raise GitHubAPIError(f"Failed to parse JSON response: {e}")

            if "errors" in data:
                errors = data["errors"]
                error_messages = [
                    error.get("message", "Unknown error") for error in errors
                ]
                raise GitHubAPIError(f"GraphQL errors: {'; '.join(error_messages)}")

            return data.get("data", {})

    async def _check_rate_limit(self) -> None:
        """Check if we need to wait for rate limit reset."""
        if not self._rate_limit:
            return

        if self._rate_limit.needs_wait(self._config.min_remaining_threshold):
            wait_time = (
                self._rate_limit.seconds_until_reset() + self._config.safety_buffer
            )
            if wait_time > 0:
                logger.warning(
                    f"Rate limit nearly exhausted. "
                    f"Remaining: {self._rate_limit.remaining}/{self._rate_limit.limit}. "
                    f"Waiting {wait_time:.1f} seconds until reset."
                )
                await asyncio.sleep(wait_time)

    def _extract_rate_limit(self, headers: Dict[str, str]) -> Optional[RateLimit]:
        """Extract rate limit information from response headers."""
        try:
            limit = int(headers.get("x-ratelimit-limit", 0))
            remaining = int(headers.get("x-ratelimit-remaining", 0))

            if limit == 0 and remaining == 0:
                return None

            return RateLimit(
                limit=limit,
                remaining=remaining,
                reset_at=datetime.fromtimestamp(
                    int(headers.get("x-ratelimit-reset", 0)), tz=timezone.utc
                ),
                used=int(headers.get("x-ratelimit-used", 0)),
                node_count=int(headers.get("x-ratelimit-resource", 0)),
            )
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to parse rate limit headers: {e}")
            return None


class GitHubContributionSource:
    def __init__(self, client: GraphQLClient):
        self._client = client

    async def contributions(self, username: str, year: int) -> ContributionStats:
        """Fetch user contribution statistics for a specific year."""
        async with self._client as client:
            year_range = YearRange(year)

            query = """
            query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                  totalCommitContributions
                  totalIssueContributions
                  totalPullRequestContributions
                  totalPullRequestReviewContributions
                  totalRepositoriesWithContributedCommits
                  totalRepositoriesWithContributedPullRequests
                  totalRepositoriesWithContributedIssues
                  restrictedContributionsCount
                  commitContributionsByRepository {
                    repository {
                      name
                      primaryLanguage { name }
                    }
                    contributions { totalCount }
                  }
                }
                repositories(first: 100, ownerAffiliations: OWNER) {
                  totalCount
                }
                starredRepositories { totalCount }
                followers { totalCount }
                following { totalCount }
                issues(first: 100, states: [OPEN, CLOSED]) {
                  totalCount
                }
                repositoryDiscussions(first: 100) {
                  totalCount
                }
              }
            }
            """

            variables = {
                "login": username,
                "from": year_range.from_date(),
                "to": year_range.to_date(),
            }

            try:
                data = await client.query(query, variables)
                user_data = data["user"]
                contributions = user_data["contributionsCollection"]

                # Calculate language statistics
                languages: Dict[str, int] = {}
                for repo_contrib in contributions["commitContributionsByRepository"]:
                    if repo_contrib["repository"]["primaryLanguage"]:
                        lang = repo_contrib["repository"]["primaryLanguage"]["name"]
                        count = repo_contrib["contributions"]["totalCount"]
                        languages[lang] = languages.get(lang, 0) + count

                # Get total repositories contributed to
                repos_contributed = (
                    contributions["totalRepositoriesWithContributedCommits"]
                    + contributions["totalRepositoriesWithContributedPullRequests"]
                    + contributions["totalRepositoriesWithContributedIssues"]
                )

                return ContributionStats(
                    username=username,
                    year=year,
                    total_commits=contributions["totalCommitContributions"],
                    total_prs=contributions["totalPullRequestContributions"],
                    total_issues=contributions["totalIssueContributions"],
                    total_discussions=user_data["repositoryDiscussions"]["totalCount"],
                    total_reviews=contributions["totalPullRequestReviewContributions"],
                    repositories_contributed=repos_contributed,
                    languages=languages,
                    starred_repos=user_data["starredRepositories"]["totalCount"],
                    followers=user_data["followers"]["totalCount"],
                    following=user_data["following"]["totalCount"],
                    public_repos=user_data["repositories"]["totalCount"],
                    private_contributions=contributions["restrictedContributionsCount"],
                    lines_added=0,  # Will be calculated separately
                    lines_deleted=0,  # Will be calculated separately
                )

            except Exception as e:
                logger.error(
                    f"Error fetching contributions for {username} ({year}): {e}"
                )
                raise GitHubAPIError(f"Failed to fetch contributions: {e}")

    async def calculate_line_stats(self, username: str, year: int) -> LineStats:
        """Calculate line statistics using pull requests method."""
        return await self._calculate_lines_from_prs(username, year)

    async def _calculate_lines_from_prs(self, username: str, year: int) -> LineStats:
        """Calculate lines added/deleted from merged pull requests in the given year."""
        async with self._client as client:
            year_range = YearRange(year)

            pr_query = """
            query($login: String!, $cursor: String) {
              user(login: $login) {
                pullRequests(
                  first: 100,
                  states: [MERGED],
                  after: $cursor,
                  orderBy: {field: CREATED_AT, direction: DESC}
                ) {
                  pageInfo {
                    hasNextPage
                    endCursor
                  }
                  nodes {
                    createdAt
                    mergedAt
                    additions
                    deletions
                    baseRepository {
                      owner {
                        login
                      }
                    }
                  }
                }
              }
            }
            """

            total_added = 0
            total_deleted = 0
            pr_count = 0
            cursor = None

            try:
                while True:
                    data = await client.query(
                        pr_query,
                        {
                            "login": username,
                            "cursor": cursor,
                        },
                    )

                    pr_result = data["user"]["pullRequests"]
                    year_prs = []

                    # Filter PRs by year and merge status
                    for pr_node in pr_result["nodes"]:
                        created_at = datetime.fromisoformat(
                            pr_node["createdAt"].replace("Z", "+00:00")
                        )
                        merged_at = pr_node.get("mergedAt")

                        # Include PR if created in target year or merged in target year
                        if created_at.year == year_range.year or (
                            merged_at
                            and datetime.fromisoformat(
                                merged_at.replace("Z", "+00:00")
                            ).year
                            == year_range.year
                        ):
                            year_prs.append(pr_node)

                    # Calculate stats for year PRs
                    for pr_node in year_prs:
                        total_added += pr_node["additions"] or 0
                        total_deleted += pr_node["deletions"] or 0
                        pr_count += 1

                    if not pr_result["pageInfo"]["hasNextPage"]:
                        break
                    cursor = pr_result["pageInfo"]["endCursor"]

                return LineStats(
                    lines_added=total_added,
                    lines_deleted=total_deleted,
                    pr_count=pr_count,
                )

            except Exception as e:
                logger.warning(f"Failed to calculate lines from PRs: {e}")
                # Return empty stats on failure
                return LineStats(0, 0)

    async def commits(self, username: str, year: int) -> List[Commit]:
        """Fetch all commits for a user in a specific year."""
        async with self._client as client:
            year_range = YearRange(year)

            # First get repository contributions
            repos_query = """
            query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                id
                contributionsCollection(from: $from, to: $to) {
                  commitContributionsByRepository {
                    repository {
                      name
                      owner { login }
                    }
                  }
                }
              }
            }
            """

            try:
                data = await client.query(
                    repos_query,
                    {
                        "login": username,
                        "from": year_range.from_date(),
                        "to": year_range.to_date(),
                    },
                )

                repo_contribs = data["user"]["contributionsCollection"][
                    "commitContributionsByRepository"
                ]
                user_id = data["user"]["id"]
                all_commits = []
                for repo_contrib in repo_contribs:
                    repo_name = repo_contrib["repository"]["name"]
                    owner_login = repo_contrib["repository"]["owner"]["login"]

                    repo_commits = await self._fetch_repo_commits(
                        client, owner_login, repo_name, user_id, year_range
                    )
                    all_commits.extend(repo_commits)

                return all_commits

            except Exception as e:
                logger.error(f"Error fetching commits for {username} ({year}): {e}")
                raise GitHubAPIError(f"Failed to fetch commits: {e}")

    async def pull_requests(self, username: str) -> List[PullRequest]:
        """Fetch all pull requests for a user."""
        async with self._client as client:
            pr_query = """
            query($login: String!, $cursor: String) {
              user(login: $login) {
                pullRequests(first: 100, states: [OPEN, MERGED, CLOSED], after: $cursor) {
                  pageInfo {
                    hasNextPage
                    endCursor
                  }
                  nodes {
                    createdAt
                    additions
                    deletions
                  }
                }
              }
            }
            """

            all_prs = []
            cursor = None

            try:
                while True:
                    data = await client.query(
                        pr_query, {"login": username, "cursor": cursor}
                    )
                    pr_result = data["user"]["pullRequests"]

                    # Convert to PullRequest objects
                    for pr_node in pr_result["nodes"]:
                        all_prs.append(
                            PullRequest(
                                created_at=pr_node["createdAt"],
                                additions=pr_node["additions"] or 0,
                                deletions=pr_node["deletions"] or 0,
                            )
                        )

                    if not pr_result["pageInfo"]["hasNextPage"]:
                        break
                    cursor = pr_result["pageInfo"]["endCursor"]

                return all_prs

            except Exception as e:
                logger.error(f"Error fetching PRs for {username}: {e}")
                raise GitHubAPIError(f"Failed to fetch pull requests: {e}")

    async def _fetch_repo_commits(
        self,
        client: GraphQLClient,
        owner: str,
        repo: str,
        user_id: str,
        year_range: YearRange,
    ) -> List[Commit]:
        """Fetch commits from a specific repository for a given author and year."""
        repo_commits_query = """
        query($owner: String!, $repo: String!, $user_id: ID!, $since: GitTimestamp!, $until: GitTimestamp!, $cursor: String) {
          repository(owner: $owner, name: $repo) {
            object(expression: "HEAD") {
              ... on Commit {
                history(first: 100, since: $since, until: $until, author: {id: $user_id}, after: $cursor) {
                  pageInfo {
                    hasNextPage
                    endCursor
                  }
                  nodes {
                    oid
                    committedDate
                    additions
                    deletions
                    author {
                      user {
                        login
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        commits = []
        cursor = None

        try:
            while True:
                data = await client.query(
                    repo_commits_query,
                    {
                        "owner": owner,
                        "repo": repo,
                        "user_id": user_id,
                        "since": year_range.from_date(),
                        "until": year_range.to_date(),
                        "cursor": cursor,
                    },
                )

                if not data["repository"] or not data["repository"]["object"]:
                    break

                history = data["repository"]["object"]["history"]
                repo_commits = history["nodes"]

                # Convert to Commit objects
                for commit in repo_commits:
                    commits.append(
                        Commit(
                            oid=commit["oid"],
                            committed_date=commit["committedDate"],
                            additions=commit["additions"] or 0,
                            deletions=commit["deletions"] or 0,
                            author_login=commit["author"]["user"]["login"]
                            if commit["author"]["user"]
                            else "",
                        )
                    )

                if not history["pageInfo"]["hasNextPage"]:
                    break
                cursor = history["pageInfo"]["endCursor"]

        except Exception as e:
            logger.warning(f"Error fetching commits from {owner}/{repo}: {e}")

        return commits


class GitHubAPIError(Exception):
    """Exception for GitHub API errors."""

    pass


class ProgressiveGitHubSource:
    """GitHub source with progress reporting."""

    def __init__(
        self,
        source: GitHubSource,
        progress: ProgressReporter,
    ):
        self._source = source
        self._progress = progress

    async def contributions(self, username: str, year: int) -> ContributionStats:
        """Fetch contributions with progress reporting."""
        await self._progress.report(
            f"Fetching contribution data for {username} ({year})..."
        )

        base_stats = await self._source.contributions(username, year)

        # Calculate lines using pull requests method
        await self._progress.report("Calculating lines using pull requests method...")

        try:
            line_stats = await self._source.calculate_line_stats(username, year)

            await self._progress.report(
                f"Found {line_stats.lines_added:,} lines added, "
                f"{line_stats.lines_deleted:,} lines deleted "
                f"({line_stats.pr_count} PRs)"
            )

            lines_added = line_stats.lines_added
            lines_deleted = line_stats.lines_deleted

            # Return new stats with line information
            return ContributionStats(
                username=base_stats.username,
                year=base_stats.year,
                total_commits=base_stats.total_commits,
                total_prs=base_stats.total_prs,
                total_issues=base_stats.total_issues,
                total_discussions=base_stats.total_discussions,
                total_reviews=base_stats.total_reviews,
                repositories_contributed=base_stats.repositories_contributed,
                languages=base_stats.languages,
                starred_repos=base_stats.starred_repos,
                followers=base_stats.followers,
                following=base_stats.following,
                public_repos=base_stats.public_repos,
                private_contributions=base_stats.private_contributions,
                lines_added=lines_added,
                lines_deleted=lines_deleted,
                created_at=base_stats.created_at,
            )

        except Exception as e:
            logger.warning(f"Failed to calculate lines using pull requests method: {e}")
            # Return stats with zero lines on failure
            return ContributionStats(
                username=base_stats.username,
                year=base_stats.year,
                total_commits=base_stats.total_commits,
                total_prs=base_stats.total_prs,
                total_issues=base_stats.total_issues,
                total_discussions=base_stats.total_discussions,
                total_reviews=base_stats.total_reviews,
                repositories_contributed=base_stats.repositories_contributed,
                languages=base_stats.languages,
                starred_repos=base_stats.starred_repos,
                followers=base_stats.followers,
                following=base_stats.following,
                public_repos=base_stats.public_repos,
                private_contributions=base_stats.private_contributions,
                lines_added=0,
                lines_deleted=0,
                created_at=base_stats.created_at,
            )

    async def commits(self, username: str, year: int) -> List[Commit]:
        """Fetch commits with progress reporting."""
        await self._progress.report(f"Fetching commits for {username} ({year})...")
        return await self._source.commits(username, year)

    async def pull_requests(self, username: str) -> List[PullRequest]:
        """Fetch pull requests with progress reporting."""
        await self._progress.report(f"Fetching pull requests for {username}...")
        return await self._source.pull_requests(username)
