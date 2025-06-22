import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from typing import Any

import aiohttp

from .models import Commit
from .models import ContributionStats
from .models import LineStats
from .models import PullRequest
from .protocols import ProgressReporter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimit:
    limit: int
    remaining: int
    reset_at: datetime
    used: int
    node_count: int

    def seconds_until_reset(self) -> float:
        return max(0, (self.reset_at - datetime.now(UTC)).total_seconds())

    def needs_wait(self, threshold: int = 100) -> bool:
        return self.remaining < threshold


@dataclass(frozen=True)
class RequestConfig:
    base_url: str
    token: str
    timeout_seconds: int = 300
    min_remaining_threshold: int = 100
    safety_buffer: int = 10

    def headers(self) -> dict[str, str]:
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
        return f"{self.year}-01-01T00:00:00Z"

    def to_date(self) -> str:
        return f"{self.year}-12-31T23:59:59Z"


class GraphQLClient:
    def __init__(self, config: RequestConfig) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self._rate_limit: RateLimit | None = None

    async def __aenter__(self) -> "GraphQLClient":
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self._config.timeout_seconds))
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        del exc_type, exc_val, exc_tb  # Unused parameters
        if self._session:
            await self._session.close()

    async def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._session:
            raise RuntimeError("Client not initialized. Use as async context manager.")

        await self._check_rate_limit()

        payload = {"query": query, "variables": variables or {}}

        async with self._session.post(self._config.base_url, json=payload, headers=self._config.headers()) as response:
            self._rate_limit = self._extract_rate_limit(dict(response.headers))

            if response.status == 401:
                raise GitHubAPIError("Authentication failed. Check your token.")
            if response.status == 403:
                raise GitHubAPIError("Forbidden. You may have exceeded rate limits.")
            if response.status >= 400:
                error_text = await response.text()
                raise GitHubAPIError(f"HTTP {response.status}: {error_text}")

            try:
                data = await response.json()
            except json.JSONDecodeError as e:
                raise GitHubAPIError(f"Failed to parse JSON response: {e}") from e

            if "errors" in data:
                errors = data["errors"]
                error_messages = [error.get("message", "Unknown error") for error in errors]
                raise GitHubAPIError(f"GraphQL errors: {'; '.join(error_messages)}")

            return data.get("data", {})

    async def _check_rate_limit(self) -> None:
        if not self._rate_limit:
            return

        if self._rate_limit.needs_wait(self._config.min_remaining_threshold):
            wait_time = self._rate_limit.seconds_until_reset() + self._config.safety_buffer
            if wait_time > 0:
                remaining = self._rate_limit.remaining
                limit = self._rate_limit.limit
                logger.warning(
                    f"Rate limit nearly exhausted. "
                    f"Remaining: {remaining}/{limit}. "
                    f"Waiting {wait_time:.1f} seconds until reset."
                )
                await asyncio.sleep(wait_time)

    def _extract_rate_limit(self, headers: dict[str, str]) -> RateLimit | None:
        try:
            limit = int(headers.get("x-ratelimit-limit", 0))
            remaining = int(headers.get("x-ratelimit-remaining", 0))

            if limit == 0 and remaining == 0:
                return None

            return RateLimit(
                limit=limit,
                remaining=remaining,
                reset_at=datetime.fromtimestamp(int(headers.get("x-ratelimit-reset", 0)), tz=UTC),
                used=int(headers.get("x-ratelimit-used", 0)),
                node_count=int(headers.get("x-ratelimit-resource", 0)),
            )
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to parse rate limit headers: {e}")
            return None


class GitHubContributionSource:
    def __init__(self, client: GraphQLClient, progress: ProgressReporter | None = None) -> None:
        self._client = client
        self._progress = progress

    async def _report_progress(self, message: str) -> None:
        if self._progress:
            await self._progress.report(message)

    def with_progress_reporter(self, progress: ProgressReporter) -> "GitHubContributionSource":
        return GitHubContributionSource(self._client, progress)

    async def contributions(self, username: str, year: int) -> ContributionStats:
        await self._report_progress("Fetching contribution statistics...")

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
                repositories(ownerAffiliations: OWNER) {
                  totalCount
                }
                starredRepositories { totalCount }
                followers { totalCount }
                following { totalCount }
                issues(states: [OPEN, CLOSED]) {
                  totalCount
                }
                repositoryDiscussions {
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

                await self._report_progress("Processing contribution data...")

                languages: dict[str, int] = {}
                for repo_contrib in contributions["commitContributionsByRepository"]:
                    if repo_contrib["repository"]["primaryLanguage"]:
                        lang = repo_contrib["repository"]["primaryLanguage"]["name"]
                        count = repo_contrib["contributions"]["totalCount"]
                        languages[lang] = languages.get(lang, 0) + count

                repos_contributed = (
                    contributions["totalRepositoriesWithContributedCommits"]
                    + contributions["totalRepositoriesWithContributedPullRequests"]
                    + contributions["totalRepositoriesWithContributedIssues"]
                )

                await self._report_progress("Calculating line statistics...")

                try:
                    line_stats = await self._calculate_lines_from_prs(client, username, year)
                    if line_stats.pr_count == 0:
                        await self._report_progress("No PRs found, falling back to commit-based calculation...")
                        line_stats = await self._calculate_lines_from_commits(client, username, year)
                    lines_added = line_stats.lines_added
                    lines_deleted = line_stats.lines_deleted
                    calculation_method = line_stats.calculation_method
                except Exception as e:
                    logger.warning(f"Failed to calculate line stats: {e}")
                    lines_added = 0
                    lines_deleted = 0
                    calculation_method = "none"

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
                    lines_added=lines_added,
                    lines_deleted=lines_deleted,
                    lines_calculation_method=calculation_method,
                )

            except Exception as e:
                logger.exception(f"Error fetching contributions for {username} ({year})")
                raise GitHubAPIError(f"Failed to fetch contributions: {e}") from e

    async def _calculate_lines_from_prs(self, client: GraphQLClient, username: str, year: int) -> LineStats:
        await self._report_progress("Fetching pull request data...")
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

                if pr_count > 0 and pr_count % 100 == 0:
                    await self._report_progress(f"Processed {pr_count} pull requests...")

                pr_result = data["user"]["pullRequests"]
                year_prs = []

                for pr_node in pr_result["nodes"]:
                    created_at = datetime.fromisoformat(pr_node["createdAt"])
                    merged_at = pr_node.get("mergedAt")

                    if created_at.year == year_range.year or (
                        merged_at and datetime.fromisoformat(merged_at).year == year_range.year
                    ):
                        year_prs.append(pr_node)

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
                calculation_method="pull_requests",
                pr_count=pr_count,
            )

        except Exception as e:
            logger.warning(f"Failed to calculate lines from PRs: {e}")
            return LineStats(
                lines_added=0,
                lines_deleted=0,
                calculation_method="error",
                pr_count=0,
            )

    async def _calculate_lines_from_commits(self, client: GraphQLClient, username: str, year: int) -> LineStats:
        await self._report_progress("Calculating lines from commits...")

        try:
            year_range = YearRange(year)

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

            data = await client.query(
                repos_query,
                {
                    "login": username,
                    "from": year_range.from_date(),
                    "to": year_range.to_date(),
                },
            )

            repo_contribs = data["user"]["contributionsCollection"]["commitContributionsByRepository"]
            user_id = data["user"]["id"]

            total_added = 0
            total_deleted = 0
            commit_count = 0

            for repo_contrib in repo_contribs:
                repo_name = repo_contrib["repository"]["name"]
                owner_login = repo_contrib["repository"]["owner"]["login"]

                repo_commits = await self._fetch_repo_commits(client, owner_login, repo_name, user_id, year_range)

                for commit in repo_commits:
                    total_added += commit.additions
                    total_deleted += commit.deletions
                    commit_count += 1

            return LineStats(
                lines_added=total_added,
                lines_deleted=total_deleted,
                calculation_method="commits",
                commit_count=commit_count,
            )

        except Exception as e:
            logger.warning(f"Failed to calculate lines from commits: {e}")
            return LineStats(
                lines_added=0,
                lines_deleted=0,
                calculation_method="error",
                commit_count=0,
            )

    async def commits(self, username: str, year: int) -> list[Commit]:
        async with self._client as client:
            year_range = YearRange(year)

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

                repo_contribs = data["user"]["contributionsCollection"]["commitContributionsByRepository"]
                user_id = data["user"]["id"]
                all_commits = []
                for repo_contrib in repo_contribs:
                    repo_name = repo_contrib["repository"]["name"]
                    owner_login = repo_contrib["repository"]["owner"]["login"]

                    repo_commits = await self._fetch_repo_commits(client, owner_login, repo_name, user_id, year_range)
                    all_commits.extend(repo_commits)
            except Exception as e:
                logger.exception(f"Error fetching commits for {username} ({year})")
                raise GitHubAPIError(f"Failed to fetch commits: {e}") from e
            else:
                return all_commits

    async def pull_requests(self, username: str) -> list[PullRequest]:
        async with self._client as client:
            pr_query = """
            query($login: String!, $cursor: String) {
              user(login: $login) {
                pullRequests(
                  first: 100,
                  states: [OPEN, MERGED, CLOSED],
                  after: $cursor
                ) {
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

            all_prs: list[PullRequest] = []
            cursor = None

            try:
                while True:
                    data = await client.query(pr_query, {"login": username, "cursor": cursor})
                    pr_result = data["user"]["pullRequests"]

                    all_prs.extend(
                        PullRequest(
                            created_at=pr_node["createdAt"],
                            additions=pr_node["additions"] or 0,
                            deletions=pr_node["deletions"] or 0,
                        )
                        for pr_node in pr_result["nodes"]
                    )

                    if not pr_result["pageInfo"]["hasNextPage"]:
                        break
                    cursor = pr_result["pageInfo"]["endCursor"]
            except Exception as e:
                logger.exception(f"Error fetching PRs for {username}")
                raise GitHubAPIError(f"Failed to fetch pull requests: {e}") from e
            else:
                return all_prs

    async def _fetch_repo_commits(
        self,
        client: GraphQLClient,
        owner: str,
        repo: str,
        user_id: str,
        year_range: YearRange,
    ) -> list[Commit]:
        repo_commits_query = """
        query(
          $owner: String!,
          $repo: String!,
          $user_id: ID!,
          $since: GitTimestamp!,
          $until: GitTimestamp!,
          $cursor: String
        ) {
          repository(owner: $owner, name: $repo) {
            object(expression: "HEAD") {
              ... on Commit {
                history(
                  first: 100,
                  since: $since,
                  until: $until,
                  author: {id: $user_id},
                  after: $cursor
                ) {
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

        commits: list[Commit] = []
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

                commits.extend(
                    Commit(
                        oid=commit["oid"],
                        committed_date=commit["committedDate"],
                        additions=commit["additions"] or 0,
                        deletions=commit["deletions"] or 0,
                        author_login=commit["author"]["user"]["login"] if commit["author"]["user"] else "",
                    )
                    for commit in repo_commits
                )

                if not history["pageInfo"]["hasNextPage"]:
                    break
                cursor = history["pageInfo"]["endCursor"]

        except Exception as e:
            logger.warning(f"Error fetching commits from {owner}/{repo}: {e}")

        return commits


class GitHubAPIError(Exception):
    pass
