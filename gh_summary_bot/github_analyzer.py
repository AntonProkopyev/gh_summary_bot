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

    async def get_user_contributions(
        self, username: str, year: int
    ) -> ContributionStats:
        """Fetch comprehensive user contribution data"""

        # Main user query
        user_query = """
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
            pullRequests(first: 100, states: [OPEN, MERGED, CLOSED]) {
              nodes {
                additions
                deletions
              }
            }
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

        variables = {"login": username, "from": from_date, "to": to_date}

        try:
            async with self.client as client:
                data = await client.query(user_query, variables)
                user_data = data["user"]
                contributions = user_data["contributionsCollection"]

            # Calculate language statistics
            languages = {}
            for repo_contrib in contributions["commitContributionsByRepository"]:
                if repo_contrib["repository"]["primaryLanguage"]:
                    lang = repo_contrib["repository"]["primaryLanguage"]["name"]
                    count = repo_contrib["contributions"]["totalCount"]
                    languages[lang] = languages.get(lang, 0) + count

            # Calculate lines of code
            lines_added = 0
            lines_deleted = 0
            for pr in user_data["pullRequests"]["nodes"]:
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