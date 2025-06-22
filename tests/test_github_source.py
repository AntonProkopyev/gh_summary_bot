"""Tests for GitHub source line calculation accuracy."""

from unittest.mock import AsyncMock

import pytest

from gh_summary_bot.github_source import GitHubContributionSource
from gh_summary_bot.github_source import GraphQLClient
from gh_summary_bot.models import ContributionStats
from gh_summary_bot.models import DateRange
from gh_summary_bot.models import PullRequest


class TestGitHubSourceLineCalculation:
    """Test suite for line calculation accuracy using new architecture."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked GraphQL client."""
        mock_client = AsyncMock(spec=GraphQLClient)
        mock_client.query = AsyncMock()
        return mock_client

    @pytest.fixture
    def github_source(self, mock_client):
        """Create a GitHubContributionSource with mocked client."""
        # Set up the async context manager behavior
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        return GitHubContributionSource(mock_client)

    @pytest.fixture
    def mock_commit_data(self):
        """Mock commit data for testing."""
        return [
            {
                "oid": "abc123",
                "committedDate": "2024-01-15T10:30:00Z",
                "additions": 50,
                "deletions": 10,
                "author": {"user": {"login": "testuser"}},
            },
            {
                "oid": "def456",
                "committedDate": "2024-02-20T14:20:00Z",
                "additions": 25,
                "deletions": 5,
                "author": {"user": {"login": "testuser"}},
            },
            {
                "oid": "ghi789",
                "committedDate": "2024-03-10T09:15:00Z",
                "additions": 100,
                "deletions": 30,
                "author": {"user": {"login": "testuser"}},
            },
        ]

    @pytest.fixture
    def mock_pr_data(self):
        """Mock PR data for comparison testing."""
        return [
            {"createdAt": "2024-01-10T08:00:00Z", "additions": 75, "deletions": 15},
            {"createdAt": "2024-02-25T12:00:00Z", "additions": 40, "deletions": 8},
        ]

    @pytest.fixture
    def mock_contributions_data(self):
        """Mock GitHub contributions collection data."""
        return {
            "user": {
                "contributionsCollection": {
                    "totalCommitContributions": 150,
                    "totalIssueContributions": 25,
                    "totalPullRequestContributions": 30,
                    "totalPullRequestReviewContributions": 45,
                    "totalRepositoriesWithContributedCommits": 5,
                    "totalRepositoriesWithContributedPullRequests": 3,
                    "totalRepositoriesWithContributedIssues": 2,
                    "restrictedContributionsCount": 10,
                    "commitContributionsByRepository": [
                        {
                            "repository": {
                                "name": "test-repo",
                                "primaryLanguage": {"name": "Python"},
                            },
                            "contributions": {"totalCount": 100},
                        }
                    ],
                },
                "repositories": {"totalCount": 15},
                "starredRepositories": {"totalCount": 250},
                "followers": {"totalCount": 50},
                "following": {"totalCount": 75},
                "issues": {"totalCount": 100},
                "repositoryDiscussions": {"totalCount": 20},
            }
        }

    @pytest.mark.asyncio
    async def test_basic_contributions_fetch(self, github_source, mock_contributions_data, mock_client):
        """Test basic contribution fetching."""
        # Set up the mock response
        mock_client.query.return_value = mock_contributions_data

        result = await github_source.contributions("testuser", DateRange.calendar_year(2024))

        assert isinstance(result, ContributionStats)
        assert result.username == "testuser"
        assert result.year == 2024
        assert result.total_commits == 150
        assert result.total_prs == 30
        assert result.total_issues == 25
        assert result.languages == {"Python": 100}

    @pytest.mark.asyncio
    async def test_pull_requests_fetch(self, github_source, mock_pr_data, mock_client):
        """Test pull requests fetching."""
        # Mock PR query response
        pr_response = {
            "user": {
                "pullRequests": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": mock_pr_data,
                }
            }
        }
        mock_client.query.return_value = pr_response

        result = await github_source.pull_requests("testuser")

        assert len(result) == 2
        assert isinstance(result[0], PullRequest)
        assert result[0].additions == 75
        assert result[1].deletions == 8


if __name__ == "__main__":
    pytest.main([__file__])
