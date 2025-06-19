"""Tests for GitHub analyzer line calculation accuracy."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from gh_summary_bot.github_analyzer import GitHubAnalyzer


class TestGitHubAnalyzerLineCalculation:
    """Test suite for line calculation accuracy."""

    @pytest.fixture
    def analyzer(self):
        """Create a GitHubAnalyzer instance with mocked client."""
        analyzer = GitHubAnalyzer("test_token")
        # Mock the client to prevent real API calls
        analyzer.client = MagicMock()
        analyzer.client.__aenter__ = AsyncMock(return_value=analyzer.client)
        analyzer.client.__aexit__ = AsyncMock()
        return analyzer

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

    @pytest.mark.asyncio
    async def test_commit_based_line_calculation(
        self, analyzer, mock_commit_data, mock_contributions_data
    ):
        """Test that commit-based calculation sums lines correctly."""
        # Mock the fetch methods
        analyzer.fetch_year_contributions = AsyncMock(
            return_value=mock_contributions_data
        )
        analyzer.fetch_all_commits_for_year = AsyncMock(return_value=mock_commit_data)

        # Execute the method
        result = await analyzer.get_user_contributions("testuser", 2024)

        # Verify the line calculations
        expected_lines_added = 50 + 25 + 100  # Sum of all commit additions
        expected_lines_deleted = 10 + 5 + 30  # Sum of all commit deletions

        assert result.lines_added == expected_lines_added
        assert result.lines_deleted == expected_lines_deleted

        # Verify other stats are preserved
        assert result.username == "testuser"
        assert result.year == 2024
        assert result.total_commits == 150

    @pytest.mark.asyncio
    async def test_fallback_to_pr_calculation(
        self, analyzer, mock_pr_data, mock_contributions_data
    ):
        """Test that system falls back to PR calculation when commit fetch fails."""
        # Mock the fetch methods - commits fail, PRs succeed
        analyzer.fetch_year_contributions = AsyncMock(
            return_value=mock_contributions_data
        )
        analyzer.fetch_all_commits_for_year = AsyncMock(
            side_effect=Exception("API Error")
        )
        analyzer.fetch_all_pull_requests = AsyncMock(return_value=mock_pr_data)

        # Mock database manager
        mock_db = AsyncMock()
        mock_db.has_pr_cache = AsyncMock(return_value=False)
        mock_db.cache_prs = AsyncMock()

        # Execute the method
        result = await analyzer.get_user_contributions(
            "testuser", 2024, db_manager=mock_db
        )

        # Verify fallback to PR calculation
        expected_lines_added = 75 + 40  # Sum of PR additions for 2024
        expected_lines_deleted = 15 + 8  # Sum of PR deletions for 2024

        assert result.lines_added == expected_lines_added
        assert result.lines_deleted == expected_lines_deleted

    @pytest.mark.asyncio
    async def test_empty_commit_data_handling(self, analyzer, mock_contributions_data):
        """Test handling of empty commit data."""
        # Mock empty commit data
        analyzer.fetch_year_contributions = AsyncMock(
            return_value=mock_contributions_data
        )
        analyzer.fetch_all_commits_for_year = AsyncMock(return_value=[])
        analyzer.fetch_all_pull_requests = AsyncMock(
            return_value=[]
        )  # Mock empty PR data too

        result = await analyzer.get_user_contributions("testuser", 2024)

        # Should handle empty data gracefully
        assert result.lines_added == 0
        assert result.lines_deleted == 0

    @pytest.mark.asyncio
    async def test_commit_data_with_none_values(
        self, analyzer, mock_contributions_data
    ):
        """Test handling of commits with None additions/deletions."""
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

        analyzer.fetch_year_contributions = AsyncMock(
            return_value=mock_contributions_data
        )
        analyzer.fetch_all_commits_for_year = AsyncMock(
            return_value=commit_data_with_nones
        )

        result = await analyzer.get_user_contributions("testuser", 2024)

        # Should handle None values by treating them as 0
        assert result.lines_added == 25  # Only the non-None value
        assert result.lines_deleted == 10  # Only the non-None value

    @pytest.mark.asyncio
    async def test_comparison_commit_vs_pr_calculation(
        self, analyzer, mock_commit_data, mock_pr_data, mock_contributions_data
    ):
        """Test that commit-based calculation can differ from PR-based calculation."""
        # Test commit-based calculation
        analyzer.fetch_year_contributions = AsyncMock(
            return_value=mock_contributions_data
        )
        analyzer.fetch_all_commits_for_year = AsyncMock(return_value=mock_commit_data)

        commit_result = await analyzer.get_user_contributions("testuser", 2024)

        # Test PR-based calculation (simulate commit fetch failure)
        analyzer.fetch_all_commits_for_year = AsyncMock(
            side_effect=Exception("API Error")
        )
        analyzer.fetch_all_pull_requests = AsyncMock(return_value=mock_pr_data)

        mock_db = AsyncMock()
        mock_db.has_pr_cache = AsyncMock(return_value=False)
        mock_db.cache_prs = AsyncMock()

        pr_result = await analyzer.get_user_contributions(
            "testuser", 2024, db_manager=mock_db
        )

        # The results should be different, demonstrating why commit-based is more accurate
        commit_total = commit_result.lines_added + commit_result.lines_deleted
        pr_total = pr_result.lines_added + pr_result.lines_deleted

        # They should be different (commits: 175+45=220, PRs: 115+23=138)
        assert commit_total != pr_total
        assert commit_result.lines_added != pr_result.lines_added
        assert commit_result.lines_deleted != pr_result.lines_deleted


if __name__ == "__main__":
    pytest.main([__file__])
