"""Tests for GitHub source line calculation accuracy."""

import pytest
from unittest.mock import AsyncMock
from gh_summary_bot.github_source import (
    GitHubContributionSource,
    GraphQLClient,
    RequestConfig,
    ProgressiveGitHubSource,
)
from gh_summary_bot.models import Commit, ContributionStats, PullRequest


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
    async def test_progressive_source_with_commits(
        self, github_source, mock_contributions_data, mock_commit_data
    ):
        """Test progressive source that fetches both contributions and commits."""
        progress_reporter = MockProgressReporter()
        progressive_source = ProgressiveGitHubSource(github_source, progress_reporter)

        # Mock the async context manager
        github_source._client.__aenter__ = AsyncMock(return_value=github_source._client)
        github_source._client.__aexit__ = AsyncMock()

        # Mock contributions call
        github_source._client.query.return_value = mock_contributions_data

        # Mock commits method - convert to Commit objects
        async def mock_commits(username: str, year: int):
            del username, year  # Unused parameters
            return [
                Commit(
                    oid=commit["oid"],
                    committed_date=commit["committedDate"],
                    additions=commit["additions"],
                    deletions=commit["deletions"],
                    author_login=commit["author"]["user"]["login"],
                )
                for commit in mock_commit_data
            ]

        github_source.commits = mock_commits

        result = await progressive_source.contributions("testuser", 2024)

        # Verify line calculations from commits
        expected_lines_added = 50 + 25 + 100  # Sum of all commit additions
        expected_lines_deleted = 10 + 5 + 30  # Sum of all commit deletions

        assert result.lines_added == expected_lines_added
        assert result.lines_deleted == expected_lines_deleted

        # Verify progress messages were sent
        assert len(progress_reporter.messages) >= 2
        assert "Fetching contribution data" in progress_reporter.messages[0]
        assert "Fetching commit data" in progress_reporter.messages[1]

    @pytest.mark.asyncio
    async def test_progressive_source_fallback(
        self, github_source, mock_contributions_data
    ):
        """Test progressive source fallback when commit fetching fails."""
        progress_reporter = MockProgressReporter()
        progressive_source = ProgressiveGitHubSource(github_source, progress_reporter)

        # Mock the async context manager
        github_source._client.__aenter__ = AsyncMock(return_value=github_source._client)
        github_source._client.__aexit__ = AsyncMock()

        # Mock contributions call
        github_source._client.query.return_value = mock_contributions_data

        # Mock commits method to fail
        async def mock_commits_fail(username: str, year: int):
            del username, year  # Unused parameters
            raise Exception("API Error")

        github_source.commits = mock_commits_fail

        result = await progressive_source.contributions("testuser", 2024)

        # Should fallback to base stats with zero lines
        assert result.lines_added == 0
        assert result.lines_deleted == 0
        assert result.total_commits == 150  # Other stats should still be present

        # Verify progress messages were sent (failure is logged, not reported)
        assert len(progress_reporter.messages) >= 2
        assert "Fetching contribution data" in progress_reporter.messages[0]
        assert "Fetching commit data" in progress_reporter.messages[1]

    @pytest.mark.asyncio
    async def test_commit_data_with_none_values(
        self, github_source, mock_contributions_data
    ):
        """Test handling of commits with None additions/deletions."""
        progress_reporter = MockProgressReporter()
        progressive_source = ProgressiveGitHubSource(github_source, progress_reporter)

        commit_data_with_nones = [
            {
                "oid": "abc123",
                "committedDate": "2024-01-15T10:30:00Z",
                "additions": None,  # None value
                "deletions": 10,
                "author": {"user": {"login": "testuser"}},
            },
            {
                "oid": "def456",
                "committedDate": "2024-02-20T14:20:00Z",
                "additions": 25,
                "deletions": None,  # None value
                "author": {"user": {"login": "testuser"}},
            },
        ]

        # Mock the async context manager
        github_source._client.__aenter__ = AsyncMock(return_value=github_source._client)
        github_source._client.__aexit__ = AsyncMock()
        github_source._client.query.return_value = mock_contributions_data

        # Mock commits method - convert to Commit objects
        async def mock_commits_with_nones(username: str, year: int):
            del username, year  # Unused parameters
            return [
                Commit(
                    oid=commit["oid"],
                    committed_date=commit["committedDate"],
                    additions=commit["additions"] or 0,
                    deletions=commit["deletions"] or 0,
                    author_login=commit["author"]["user"]["login"],
                )
                for commit in commit_data_with_nones
            ]

        github_source.commits = mock_commits_with_nones

        result = await progressive_source.contributions("testuser", 2024)

        # Should handle None values by treating them as 0
        assert result.lines_added == 25  # Only the non-None value
        assert result.lines_deleted == 10  # Only the non-None value

    @pytest.mark.asyncio
    async def test_empty_commit_data_handling(
        self, github_source, mock_contributions_data
    ):
        """Test handling of empty commit data."""
        progress_reporter = MockProgressReporter()
        progressive_source = ProgressiveGitHubSource(github_source, progress_reporter)

        # Mock the async context manager
        github_source._client.__aenter__ = AsyncMock(return_value=github_source._client)
        github_source._client.__aexit__ = AsyncMock()
        github_source._client.query.return_value = mock_contributions_data

        # Mock empty commits
        async def mock_empty_commits(username: str, year: int):
            del username, year  # Unused parameters
            return []

        github_source.commits = mock_empty_commits

        result = await progressive_source.contributions("testuser", 2024)

        # Should handle empty data gracefully
        assert result.lines_added == 0
        assert result.lines_deleted == 0
        assert result.total_commits == 150  # Other stats should still be present

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
