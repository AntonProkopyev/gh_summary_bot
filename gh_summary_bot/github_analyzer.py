"""GitHub GraphQL API analyzer for fetching user contribution data."""

import logging

from .gh_gql_client import GitHubGraphQLClient, GitHubGraphQLError
from .models import ContributionStats

logger = logging.getLogger(__name__)


class GitHubAnalyzer:
    """Handles GitHub GraphQL API interactions"""

    def __init__(self, token: str):
        self.token = token
        self.client = GitHubGraphQLClient(token)

    async def fetch_all_commits_for_year(
        self, username: str, year: int, progress_callback=None
    ) -> list:
        """Fetch all commits for a user in a specific year"""
        from_date = f"{year}-01-01T00:00:00Z"
        to_date = f"{year}-12-31T23:59:59Z"

        commits_query = """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
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

        all_commits = []

        try:
            async with self.client as client:
                if progress_callback:
                    await progress_callback(
                        f"Fetching commits for {username} ({year})..."
                    )

                # First, get the repository contributions
                contrib_data = await client.query(
                    commits_query,
                    {
                        "login": username,
                        "from": from_date,
                        "to": to_date,
                    },
                )

                repo_contribs = contrib_data["user"]["contributionsCollection"][
                    "commitContributionsByRepository"
                ]
                total_repos = len(repo_contribs)

                # For each repository, fetch detailed commit information
                repo_count = 0
                for repo_contrib in repo_contribs:
                    repo_count += 1
                    repo_name = repo_contrib["repository"]["name"]
                    owner_login = repo_contrib["repository"]["owner"]["login"]

                    if progress_callback:
                        await progress_callback(
                            f"Analyzing commits in {owner_login}/{repo_name} ({repo_count}/{total_repos})..."
                        )

                    # Fetch commits from this repository for the year
                    repo_commits = await self._fetch_repo_commits_for_year(
                        client, owner_login, repo_name, username, year
                    )
                    all_commits.extend(repo_commits)

                if progress_callback:
                    await progress_callback(
                        f"Collected {len(all_commits)} commits for {username} ({year})"
                    )

                return all_commits

        except Exception as e:
            logger.error(f"Error fetching commits for {username} ({year}): {e}")
            raise

    async def _fetch_repo_commits_for_year(
        self, client, owner: str, repo: str, author: str, year: int
    ) -> list:
        """Fetch commits from a specific repository for a given author and year"""
        from_date = f"{year}-01-01T00:00:00Z"
        to_date = f"{year}-12-31T23:59:59Z"

        repo_commits_query = """
        query($owner: String!, $repo: String!, $author: String!, $since: GitTimestamp!, $until: GitTimestamp!, $cursor: String) {
          repository(owner: $owner, name: $repo) {
            object(expression: "HEAD") {
              ... on Commit {
                history(first: 100, since: $since, until: $until, author: {emails: [$author]}, after: $cursor) {
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
                commit_data = await client.query(
                    repo_commits_query,
                    {
                        "owner": owner,
                        "repo": repo,
                        "author": author,
                        "since": from_date,
                        "until": to_date,
                        "cursor": cursor,
                    },
                )

                if (
                    not commit_data["repository"]
                    or not commit_data["repository"]["object"]
                ):
                    break

                history = commit_data["repository"]["object"]["history"]
                repo_commits = history["nodes"]

                # Filter commits by author username to ensure accuracy
                filtered_commits = []
                for commit in repo_commits:
                    if (
                        commit["author"]
                        and commit["author"]["user"]
                        and commit["author"]["user"]["login"] == author
                    ):
                        filtered_commits.append(commit)

                commits.extend(filtered_commits)

                if not history["pageInfo"]["hasNextPage"]:
                    break
                cursor = history["pageInfo"]["endCursor"]

        except Exception as e:
            logger.warning(f"Error fetching commits from {owner}/{repo}: {e}")
            # Continue with other repositories even if one fails

        return commits

    async def fetch_all_pull_requests(
        self, username: str, progress_callback=None
    ) -> list:
        """Fetch all pull requests for a user (cached independently)"""
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
        page_count = 0

        try:
            async with self.client as client:
                while True:
                    page_count += 1
                    if progress_callback:
                        if page_count == 1:
                            await progress_callback(
                                f"Fetching pull requests for {username}..."
                            )
                        else:
                            await progress_callback(
                                f"Fetching PR page {page_count} for {username}..."
                            )

                    pr_data = await client.query(
                        pr_query, {"login": username, "cursor": cursor}
                    )
                    pr_result = pr_data["user"]["pullRequests"]
                    all_prs.extend(pr_result["nodes"])

                    if not pr_result["pageInfo"]["hasNextPage"]:
                        break
                    cursor = pr_result["pageInfo"]["endCursor"]

                if progress_callback:
                    await progress_callback(
                        f"Collected {len(all_prs)} pull requests for {username}"
                    )

                return all_prs

        except Exception as e:
            logger.error(f"Error fetching PRs for {username}: {e}")
            raise

    async def fetch_year_contributions(
        self, username: str, year: int, progress_callback=None
    ) -> dict:
        """Fetch contribution data for a specific year"""
        contributions_query = """
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

        from_date = f"{year}-01-01T00:00:00Z"
        to_date = f"{year}-12-31T23:59:59Z"

        try:
            if progress_callback:
                await progress_callback(
                    f"Fetching contribution data for {username} ({year})..."
                )

            async with self.client as client:
                contrib_data = await client.query(
                    contributions_query,
                    {"login": username, "from": from_date, "to": to_date},
                )
                return contrib_data["user"]

        except Exception as e:
            logger.error(f"Error fetching contributions for {username} ({year}): {e}")
            raise

    async def get_user_contributions(
        self, username: str, year: int, progress_callback=None, db_manager=None
    ) -> ContributionStats:
        """Fetch comprehensive user contribution data with commit-based line calculation"""
        try:
            # Task 1: Get year-specific contribution data
            user_data = await self.fetch_year_contributions(
                username, year, progress_callback
            )
            contributions = user_data["contributionsCollection"]

            # Task 2: Get commits for accurate line calculation
            # This is the new commit-based approach for accurate line counting
            if progress_callback:
                await progress_callback(
                    "Fetching commit data for accurate line calculations..."
                )

            try:
                all_commits = await self.fetch_all_commits_for_year(
                    username, year, progress_callback
                )
                use_commit_data = True
            except Exception as e:
                logger.warning(
                    f"Failed to fetch commit data for {username} ({year}): {e}"
                )
                if progress_callback:
                    await progress_callback(
                        "Falling back to pull request data for line calculations..."
                    )
                # Fallback to the old PR-based method for backward compatibility
                all_commits = []
                use_commit_data = False

            # Process the data
            if progress_callback:
                await progress_callback(f"Processing data for {username} ({year})...")

            # Calculate language statistics
            languages = {}
            for repo_contrib in contributions["commitContributionsByRepository"]:
                if repo_contrib["repository"]["primaryLanguage"]:
                    lang = repo_contrib["repository"]["primaryLanguage"]["name"]
                    count = repo_contrib["contributions"]["totalCount"]
                    languages[lang] = languages.get(lang, 0) + count

            # Calculate lines of code based on available data
            lines_added = 0
            lines_deleted = 0

            if use_commit_data and all_commits:
                # New commit-based calculation (more accurate)
                for commit in all_commits:
                    lines_added += commit["additions"] or 0
                    lines_deleted += commit["deletions"] or 0

                if progress_callback:
                    await progress_callback(
                        f"Used commit-based calculation: {len(all_commits)} commits analyzed"
                    )
            else:
                # Fallback to PR-based calculation for backward compatibility
                if progress_callback:
                    await progress_callback("Using fallback PR-based calculation...")

                # Get PR data using the existing caching mechanism
                all_prs = []
                if db_manager and await db_manager.has_pr_cache(username):
                    all_prs = await db_manager.get_cached_prs(username)
                else:
                    all_prs = await self.fetch_all_pull_requests(
                        username, progress_callback
                    )
                    if db_manager:
                        await db_manager.cache_prs(username, all_prs)

                # Calculate from PRs (old method)
                for pr in all_prs:
                    pr_year = int(pr["createdAt"][:4])
                    if pr_year == year:
                        lines_added += pr["additions"]
                        lines_deleted += pr["deletions"]

                if progress_callback:
                    await progress_callback(
                        f"Used PR-based fallback: {len([pr for pr in all_prs if int(pr['createdAt'][:4]) == year])} PRs analyzed"
                    )

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
                lines_added=lines_added,
                lines_deleted=lines_deleted,
            )

        except GitHubGraphQLError as e:
            logger.error(f"Error fetching data for {username}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching data for {username}: {e}")
            raise
