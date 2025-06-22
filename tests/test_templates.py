from datetime import UTC
from datetime import datetime

import pytest

from gh_summary_bot.models import ContributionStats
from gh_summary_bot.models import DateRange
from gh_summary_bot.templates import TelegramReportTemplate


class TestTelegramReportTemplate:
    """Test suite for TelegramReportTemplate."""

    @pytest.fixture
    def template(self):
        """Create a TelegramReportTemplate instance."""
        return TelegramReportTemplate()

    @pytest.fixture
    def sample_contribution_stats(self):
        """Create sample ContributionStats for testing."""
        return ContributionStats(
            username="testuser",
            date_range=DateRange.calendar_year(2024),
            total_commits=150,
            total_prs=25,
            total_issues=10,
            total_discussions=5,
            total_reviews=30,
            repositories_contributed=8,
            languages={"Python": 100, "JavaScript": 40, "TypeScript": 10},
            starred_repos=250,
            followers=50,
            following=75,
            public_repos=15,
            private_contributions=5,
            lines_added=5000,
            lines_deleted=1500,
            lines_calculation_method="pull_requests",
            created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        )

    def test_yearly_report_basic_structure(self, template, sample_contribution_stats):
        """Test that yearly report contains expected sections."""
        result = template.yearly(sample_contribution_stats)

        # Check main sections are present
        assert "*GitHub Contributions Report*" in result
        assert "👤 User: `testuser`" in result
        assert "📅 Period: 2024" in result
        assert "*📊 Contribution Summary*" in result
        assert "*💻 Code Statistics*" in result
        assert "*📈 Activity Metrics*" in result
        assert "*🌟 Social Stats*" in result
        assert "*🔥 Top Languages*" in result

    def test_yearly_report_contribution_calculations(self, template, sample_contribution_stats):
        """Test that yearly report calculates totals correctly."""
        result = template.yearly(sample_contribution_stats)

        # Total contributions = 150 + 25 + 10 + 5 = 190
        assert "• Total Contributions: *190*" in result
        assert "• Commits: *150*" in result
        assert "• Pull Requests: *25*" in result
        assert "• Issues: *10*" in result
        assert "• Discussions: *5*" in result
        assert "• Code Reviews: *30*" in result

    def test_yearly_report_code_statistics(self, template, sample_contribution_stats):
        """Test that yearly report shows code statistics correctly."""
        result = template.yearly(sample_contribution_stats)

        assert "• Lines Added: *5,000*" in result
        assert "• Lines Deleted: *1,500*" in result
        # Net lines = 5000 - 1500 = 3500
        assert "• Net Lines: *3,500*" in result

    def test_yearly_report_languages(self, template, sample_contribution_stats):
        """Test that yearly report shows top languages correctly."""
        result = template.yearly(sample_contribution_stats)

        # Should show top 5 languages (we have 3)
        assert "1. Python: 100 commits" in result
        assert "2. JavaScript: 40 commits" in result
        assert "3. TypeScript: 10 commits" in result

    def test_yearly_report_no_languages(self, template):
        """Test yearly report when no language data is available."""
        stats = ContributionStats(
            username="testuser",
            date_range=DateRange.calendar_year(2024),
            total_commits=10,
            total_prs=2,
            total_issues=1,
            total_discussions=0,
            total_reviews=3,
            repositories_contributed=2,
            languages={},  # Empty languages
            starred_repos=50,
            followers=10,
            following=15,
            public_repos=3,
            private_contributions=1,
            lines_added=500,
            lines_deleted=100,
            lines_calculation_method="pull_requests",
        )

        result = template.yearly(stats)
        assert "No language data available" in result


class TestTemplateImmutability:
    """Test suite for template immutability principles."""

    def test_template_methods_are_pure(self):
        """Test that template methods are pure functions."""
        template = TelegramReportTemplate()

        stats = ContributionStats(
            username="testuser",
            date_range=DateRange.calendar_year(2024),
            total_commits=10,
            total_prs=2,
            total_issues=1,
            total_discussions=0,
            total_reviews=3,
            repositories_contributed=2,
            languages={"Python": 10},
            starred_repos=50,
            followers=10,
            following=15,
            public_repos=3,
            private_contributions=1,
            lines_added=500,
            lines_deleted=100,
        )

        # Multiple calls should return identical results
        result1 = template.yearly(stats)
        result2 = template.yearly(stats)

        assert result1 == result2


if __name__ == "__main__":
    pytest.main([__file__])
