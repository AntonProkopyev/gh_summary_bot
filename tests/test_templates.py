import pytest
from datetime import datetime

from gh_summary_bot.templates import TelegramReportTemplate, ProgressMessage
from gh_summary_bot.models import AllTimeStats, ContributionStats


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
            year=2024,
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
            created_at=datetime(2024, 1, 15, 10, 30, 0),
        )

    @pytest.fixture
    def sample_alltime_stats(self):
        """Create sample AllTimeStats for testing."""
        return AllTimeStats(
            username="testuser",
            total_years=3,
            total_commits=450,
            total_prs=75,
            total_issues=30,
            total_discussions=15,
            total_reviews=90,
            private_contributions=15,
            lines_added=15000,
            lines_deleted=4500,
            first_year=2022,
            last_year=2024,
            repositories_contributed=25,
            starred_repos=500,
            followers=120,
            following=200,
            public_repos=35,
            languages={"Python": 300, "JavaScript": 120, "TypeScript": 30},
            last_updated=datetime(2024, 6, 19, 18, 45, 0),
        )

    def test_yearly_report_basic_structure(self, template, sample_contribution_stats):
        """Test that yearly report contains expected sections."""
        result = template.yearly(sample_contribution_stats)

        # Check main sections are present
        assert "*GitHub Contributions Report*" in result
        assert "👤 User: `testuser`" in result
        assert "📅 Year: 2024" in result
        assert "*📊 Contribution Summary*" in result
        assert "*💻 Code Statistics*" in result
        assert "*📈 Activity Metrics*" in result
        assert "*🌟 Social Stats*" in result
        assert "*🔥 Top Languages*" in result

    def test_yearly_report_contribution_calculations(
        self, template, sample_contribution_stats
    ):
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
            year=2024,
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
        )

        result = template.yearly(stats)
        assert "No language data available" in result

    def test_alltime_report_basic_structure(self, template, sample_alltime_stats):
        """Test that alltime report contains expected sections."""
        result = template.alltime(sample_alltime_stats)

        assert "*🌟 All-Time GitHub Statistics*" in result
        assert "👤 User: `testuser`" in result
        assert "📅 Period: 2022 - 2024 (3 years)" in result
        assert "*📊 Total Contributions*" in result
        assert "*💻 Code Statistics*" in result
        assert "*📈 Activity Metrics*" in result
        assert "*🌟 Social Stats*" in result
        assert "*🔥 Top Languages (All Time)*" in result

    def test_alltime_report_calculations(self, template, sample_alltime_stats):
        """Test that alltime report calculates totals correctly."""
        result = template.alltime(sample_alltime_stats)

        # Total contributions = 450 + 75 + 30 + 15 = 570
        assert "• All Contributions: *570*" in result
        assert "• Commits: *450*" in result
        assert "• Pull Requests: *75*" in result

    def test_alltime_report_formatting(self, template, sample_alltime_stats):
        """Test that alltime report formats numbers correctly."""
        result = template.alltime(sample_alltime_stats)

        # Check comma formatting for large numbers
        assert "• Lines Added: *15,000*" in result
        assert "• Lines Deleted: *4,500*" in result
        assert "• Net Lines: *10,500*" in result

    def test_alltime_report_languages_limit(self, template, sample_alltime_stats):
        """Test that alltime report shows up to 10 languages."""
        # Create stats with many languages
        many_languages = {f"Lang{i}": 100 - i for i in range(15)}
        stats = AllTimeStats(
            username="testuser",
            total_years=3,
            total_commits=450,
            total_prs=75,
            total_issues=30,
            total_discussions=15,
            total_reviews=90,
            private_contributions=15,
            lines_added=15000,
            lines_deleted=4500,
            first_year=2022,
            last_year=2024,
            repositories_contributed=25,
            starred_repos=500,
            followers=120,
            following=200,
            public_repos=35,
            languages=many_languages,
            last_updated=datetime(2024, 6, 19, 18, 45, 0),
        )

        result = template.alltime(stats)

        # Should show top 10 languages
        assert "1. Lang0: 100 commits" in result
        assert "10. Lang9: 91 commits" in result
        # Should not show 11th language
        assert "11. Lang10:" not in result

    def test_alltime_report_timestamp(self, template, sample_alltime_stats):
        """Test that alltime report includes last updated timestamp."""
        result = template.alltime(sample_alltime_stats)

        assert "_📅 Last updated: 2024-06-19 18:45 UTC_" in result

    def test_languages_report_basic(self, template):
        """Test basic language statistics report."""
        languages = {"Python": 100, "JavaScript": 50, "Go": 25}

        result = template.languages("testuser", 2024, languages)

        assert "*Language Statistics for testuser (2024)*" in result
        assert "Python" in result
        assert "JavaScript" in result
        assert "Go" in result

    def test_languages_report_percentages(self, template):
        """Test that language report calculates percentages correctly."""
        languages = {"Python": 75, "JavaScript": 25}  # Total: 100

        result = template.languages("testuser", 2024, languages)

        assert "75.0%" in result  # Python should be 75%
        assert "25.0%" in result  # JavaScript should be 25%

    def test_languages_report_progress_bars(self, template):
        """Test that language report includes progress bars."""
        languages = {"Python": 100, "JavaScript": 50}  # Total: 150

        result = template.languages("testuser", 2024, languages)

        # Python: 66.7% -> 13 bars, JavaScript: 33.3% -> 6 bars
        assert "█" in result  # Should contain progress bars

    def test_languages_report_empty(self, template):
        """Test language report with no languages."""
        result = template.languages("testuser", 2024, {})

        assert "No language data available for testuser (2024)" == result

    def test_languages_report_limit_10(self, template):
        """Test that language report limits to 10 languages."""
        languages = {f"Lang{i}": 100 - i for i in range(15)}

        result = template.languages("testuser", 2024, languages)

        # Count number of language lines (should be max 10)
        lines = result.split("\n")
        language_lines = [line for line in lines if "`" in line and "█" in line]
        assert len(language_lines) <= 10

    def test_languages_report_sorting(self, template):
        """Test that languages are sorted by commit count."""
        languages = {"JavaScript": 50, "Python": 100, "Go": 75}

        result = template.languages("testuser", 2024, languages)

        # Should be sorted: Python (100), Go (75), JavaScript (50)
        python_pos = result.find("Python")
        go_pos = result.find("Go")
        js_pos = result.find("JavaScript")

        assert python_pos < go_pos < js_pos


class TestProgressMessage:
    """Test suite for ProgressMessage."""

    @pytest.fixture
    def progress_message(self):
        """Create a ProgressMessage instance."""
        return ProgressMessage("Processing data")

    def test_with_detail(self, progress_message):
        """Test creating progress message with detail."""
        result = progress_message.with_detail("fetching commits")

        assert result == "Processing data: fetching commits"

    def test_with_progress(self, progress_message):
        """Test creating progress message with progress indicator."""
        result = progress_message.with_progress(5, 10)

        assert result == "Processing data - Progress: 5/10"

    def test_empty_base_message(self):
        """Test ProgressMessage with empty base message."""
        progress = ProgressMessage("")

        result = progress.with_detail("detail")
        assert result == ": detail"

        result = progress.with_progress(1, 2)
        assert result == " - Progress: 1/2"


class TestTemplateImmutability:
    """Test suite for template immutability principles."""

    def test_template_has_no_state(self):
        """Test that template doesn't maintain mutable state."""
        template1 = TelegramReportTemplate()
        template2 = TelegramReportTemplate()

        # Templates should be stateless - no instance variables
        assert not hasattr(template1, "__dict__") or not template1.__dict__
        assert not hasattr(template2, "__dict__") or not template2.__dict__

    def test_template_methods_are_pure(self):
        """Test that template methods are pure functions."""
        template = TelegramReportTemplate()

        stats = ContributionStats(
            username="testuser",
            year=2024,
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

    def test_progress_message_immutability(self):
        """Test that ProgressMessage follows immutability principles."""
        progress = ProgressMessage("test")

        # Methods should return new strings, not modify state
        detail_result = progress.with_detail("detail")
        progress_result = progress.with_progress(1, 5)

        # Original message should be unchanged
        assert progress._base_message == "test"

        # Results should be different strings
        assert detail_result != progress_result
        assert "detail" in detail_result
        assert "Progress:" in progress_result


if __name__ == "__main__":
    pytest.main([__file__])
