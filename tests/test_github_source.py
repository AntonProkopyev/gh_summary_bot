"""Tests for GitHub source line calculation accuracy."""

import pytest
from unittest.mock import AsyncMock
from gh_summary_bot.github_source import (
    GitHubContributionSource,
    GraphQLClient,
    RequestConfig,
    ProgressiveGitHubSource,
    LineStats,
)
from gh_summary_bot.models import ContributionStats, PullRequest


class MockProgressReporter:
    """Mock progress reporter for testing."""

    def __init__(self):
        self.messages = []

    async def report(self, message: str) -> None:
        """Store progress messages for verification."""
        self.messages.append(message)


class TestGitHubSourceLineCalculation:
    """Test suite for line calculation accuracy using new architecture."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked GraphQL client."""
        config = RequestConfig(base_url="https://test.api", token="test_token")
        client = GraphQLClient(config)
        client.query = AsyncMock()
        return client

    @pytest.fixture
    def github_source(self, mock_client):
        """Create a GitHubContributionSource with mocked client."""
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
    async def test_basic_contributions_fetch(
        self, github_source, mock_contributions_data
    ):
        """Test basic contribution fetching."""
        # Mock the async context manager
        github_source._client.__aenter__ = AsyncMock(return_value=github_source._client)
        github_source._client.__aexit__ = AsyncMock()
        github_source._client.query.return_value = mock_contributions_data

        result = await github_source.contributions("testuser", 2024)

        assert isinstance(result, ContributionStats)
        assert result.username == "testuser"
        assert result.year == 2024
        assert result.total_commits == 150
        assert result.total_prs == 30
        assert result.total_issues == 25
        assert result.languages == {"Python": 100}

    @pytest.mark.asyncio
    async def test_progressive_source_with_prs(
        self, github_source, mock_contributions_data
    ):
        """Test progressive source that fetches both contributions and PR line stats."""
        progress_reporter = MockProgressReporter()
        progressive_source = ProgressiveGitHubSource(github_source, progress_reporter)

        # Mock the async context manager
        github_source._client.__aenter__ = AsyncMock(return_value=github_source._client)
        github_source._client.__aexit__ = AsyncMock()

        # Mock contributions call
        github_source._client.query.return_value = mock_contributions_data

        # Mock calculate_line_stats method
        async def mock_calculate_line_stats(username: str, year: int):
            del username, year  # Unused parameters
            return LineStats(
                lines_added=115,
                lines_deleted=23,
                pr_count=2,
            )

        github_source.calculate_line_stats = mock_calculate_line_stats

        result = await progressive_source.contributions("testuser", 2024)

        # Verify line calculations from PRs
        assert result.lines_added == 115
        assert result.lines_deleted == 23

        # Verify progress messages were sent
        assert len(progress_reporter.messages) >= 2
        assert "Fetching contribution data" in progress_reporter.messages[0]
        assert (
            "Calculating lines using pull requests method"
            in progress_reporter.messages[1]
        )

    @pytest.mark.asyncio
    async def test_progressive_source_fallback(
        self, github_source, mock_contributions_data
    ):
        """Test progressive source fallback when PR line calculation fails."""
        progress_reporter = MockProgressReporter()
        progressive_source = ProgressiveGitHubSource(github_source, progress_reporter)

        # Mock the async context manager
        github_source._client.__aenter__ = AsyncMock(return_value=github_source._client)
        github_source._client.__aexit__ = AsyncMock()

        # Mock contributions call
        github_source._client.query.return_value = mock_contributions_data

        # Mock calculate_line_stats method to fail
        async def mock_calculate_line_stats_fail(username: str, year: int):
            del username, year  # Unused parameters
            raise Exception("API Error")

        github_source.calculate_line_stats = mock_calculate_line_stats_fail

        result = await progressive_source.contributions("testuser", 2024)

        # Should fallback to base stats with zero lines
        assert result.lines_added == 0
        assert result.lines_deleted == 0
        assert result.total_commits == 150  # Other stats should still be present

        # Verify progress messages were sent
        assert len(progress_reporter.messages) >= 2
        assert "Fetching contribution data" in progress_reporter.messages[0]
        assert (
            "Calculating lines using pull requests method"
            in progress_reporter.messages[1]
        )

    @pytest.mark.asyncio
    async def test_calculate_line_stats_method(self, github_source):
        """Test the calculate_line_stats method directly."""
        # Mock the async context manager
        github_source._client.__aenter__ = AsyncMock(return_value=github_source._client)
        github_source._client.__aexit__ = AsyncMock()

        # Mock PR query response with merged PRs
        pr_response = {
            "user": {
                "pullRequests": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "createdAt": "2024-01-10T08:00:00Z",
                            "mergedAt": "2024-01-15T10:00:00Z",
                            "additions": 75,
                            "deletions": 15,
                            "baseRepository": {"owner": {"login": "owner1"}},
                        },
                        {
                            "createdAt": "2024-02-20T12:00:00Z",
                            "mergedAt": "2024-02-25T14:00:00Z",
                            "additions": 40,
                            "deletions": 8,
                            "baseRepository": {"owner": {"login": "owner2"}},
                        },
                    ],
                }
            }
        }
        github_source._client.query.return_value = pr_response

        result = await github_source.calculate_line_stats("testuser", 2024)

        # Should calculate lines from PRs in 2024
        assert result.lines_added == 115  # 75 + 40
        assert result.lines_deleted == 23  # 15 + 8
        assert result.pr_count == 2

    @pytest.mark.asyncio
    async def test_pr_line_stats_with_none_values(self, github_source):
        """Test handling of PRs with None additions/deletions."""
        # Mock the async context manager
        github_source._client.__aenter__ = AsyncMock(return_value=github_source._client)
        github_source._client.__aexit__ = AsyncMock()

        # Mock PR response with None values
        pr_response = {
            "user": {
                "pullRequests": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "createdAt": "2024-01-10T08:00:00Z",
                            "mergedAt": "2024-01-15T10:00:00Z",
                            "additions": None,  # None value
                            "deletions": 15,
                            "baseRepository": {"owner": {"login": "owner1"}},
                        },
                        {
                            "createdAt": "2024-02-20T12:00:00Z",
                            "mergedAt": "2024-02-25T14:00:00Z",
                            "additions": 40,
                            "deletions": None,  # None value
                            "baseRepository": {"owner": {"login": "owner2"}},
                        },
                    ],
                }
            }
        }
        github_source._client.query.return_value = pr_response

        result = await github_source.calculate_line_stats("testuser", 2024)

        # Should handle None values by treating them as 0
        assert result.lines_added == 40  # Only the non-None value
        assert result.lines_deleted == 15  # Only the non-None value
        assert result.pr_count == 2

    @pytest.mark.asyncio
    async def test_pull_requests_fetch(self, github_source, mock_pr_data):
        """Test pull requests fetching."""
        # Mock the async context manager
        github_source._client.__aenter__ = AsyncMock(return_value=github_source._client)
        github_source._client.__aexit__ = AsyncMock()

        # Mock PR query response
        pr_response = {
            "user": {
                "pullRequests": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": mock_pr_data,
                }
            }
        }
        github_source._client.query.return_value = pr_response

        result = await github_source.pull_requests("testuser")

        assert len(result) == 2
        assert isinstance(result[0], PullRequest)
        assert result[0].additions == 75
        assert result[1].deletions == 8


if __name__ == "__main__":
    pytest.main([__file__])
