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

    async def fetch_all_pull_requests(self, username: str, progress_callback=None) -> list:
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
                            await progress_callback(f"Fetching pull requests for {username}...")
                        else:
                            await progress_callback(f"Fetching PR page {page_count} for {username}...")
                    
                    pr_data = await client.query(pr_query, {"login": username, "cursor": cursor})
                    pr_result = pr_data["user"]["pullRequests"]
                    all_prs.extend(pr_result["nodes"])
                    
                    if not pr_result["pageInfo"]["hasNextPage"]:
                        break
                    cursor = pr_result["pageInfo"]["endCursor"]

                if progress_callback:
                    await progress_callback(f"Collected {len(all_prs)} pull requests for {username}")

                return all_prs

        except Exception as e:
            logger.error(f"Error fetching PRs for {username}: {e}")
            raise

    async def fetch_year_contributions(self, username: str, year: int, progress_callback=None) -> dict:
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
                await progress_callback(f"Fetching contribution data for {username} ({year})...")

            async with self.client as client:
                contrib_data = await client.query(
                    contributions_query, 
                    {"login": username, "from": from_date, "to": to_date}
                )
                return contrib_data["user"]

        except Exception as e:
            logger.error(f"Error fetching contributions for {username} ({year}): {e}")
            raise

    async def get_user_contributions(
        self, username: str, year: int, progress_callback=None, db_manager=None
    ) -> ContributionStats:
        """Fetch comprehensive user contribution data with caching"""
        try:
            # Task 1: Get year-specific contribution data
            user_data = await self.fetch_year_contributions(username, year, progress_callback)
            contributions = user_data["contributionsCollection"]

            # Task 2: Get pull requests (cached or fresh)
            all_prs = []
            if db_manager and await db_manager.has_pr_cache(username):
                if progress_callback:
                    await progress_callback(f"Using cached pull requests for {username}...")
                all_prs = await db_manager.get_cached_prs(username)
            else:
                if progress_callback:
                    await progress_callback(f"Fetching fresh pull request data for {username}...")
                all_prs = await self.fetch_all_pull_requests(username, progress_callback)
                
                # Cache the PR data for future use
                if db_manager:
                    if progress_callback:
                        await progress_callback(f"Caching pull request data for {username}...")
                    await db_manager.cache_prs(username, all_prs)

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

            # Calculate lines of code for the specific year from all PRs
            lines_added = 0
            lines_deleted = 0
            for pr in all_prs:
                # Parse the PR creation date and check if it's in the target year
                pr_year = int(pr["createdAt"][:4])  # Extract year from ISO date string
                if pr_year == year:
                    lines_added += pr["additions"]
                    lines_deleted += pr["deletions"]

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