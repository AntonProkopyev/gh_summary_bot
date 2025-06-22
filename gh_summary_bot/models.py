"""Data models for GitHub contribution analysis."""

from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from datetime import timedelta


@dataclass(frozen=True)
class DateRange:
    """Represents a date range for analysis."""

    start_date: datetime
    end_date: datetime

    @classmethod
    def last_12_months(cls) -> "DateRange":
        """Create a date range for the last 12 months."""
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=365)
        return cls(start_date=start_date, end_date=end_date)

    @classmethod
    def calendar_year(cls, year: int) -> "DateRange":
        """Create a date range for a specific calendar year."""
        start_date = datetime(year, 1, 1, tzinfo=UTC)
        end_date = datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC)
        return cls(start_date=start_date, end_date=end_date)

    @classmethod
    def from_strings(cls, start_str: str, end_str: str) -> "DateRange":
        """Create date range from ISO date strings (YYYY-MM-DD)."""
        start_date = datetime.fromisoformat(start_str)
        end_date = datetime.fromisoformat(end_str)
        if end_date < start_date:
            raise ValueError("End date must be after start date")
        return cls(start_date=start_date, end_date=end_date)

    def to_github_format(self) -> tuple[str, str]:
        """Convert to GitHub API timestamp format."""
        start_str = self.start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = self.end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        return start_str, end_str

    def description(self) -> str:
        """Human-readable description of the date range."""
        if self.is_calendar_year():
            return str(self.start_date.year)
        if self.is_last_12_months():
            return "Last 12 months"
        start_str = self.start_date.strftime("%Y-%m-%d")
        end_str = self.end_date.strftime("%Y-%m-%d")
        return f"{start_str} to {end_str}"

    def is_calendar_year(self) -> bool:
        """Check if this represents a full calendar year."""
        return (
            self.start_date.month == 1
            and self.start_date.day == 1
            and self.end_date.month == 12
            and self.end_date.day == 31
            and self.start_date.year == self.end_date.year
        )

    def is_last_12_months(self) -> bool:
        """Check if this approximately represents the last 12 months."""
        now = datetime.now(UTC)
        twelve_months_ago = now - timedelta(days=365)
        # Allow some tolerance (within 7 days)
        return abs((self.end_date - now).days) <= 7 and abs((self.start_date - twelve_months_ago).days) <= 7


@dataclass(frozen=True)
class ContributionStats:
    username: str
    date_range: DateRange
    total_commits: int
    total_prs: int
    total_issues: int
    total_discussions: int
    total_reviews: int
    repositories_contributed: int
    languages: dict[str, int]
    starred_repos: int
    followers: int
    following: int
    public_repos: int
    private_contributions: int
    lines_added: int
    lines_deleted: int
    lines_calculation_method: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    # Backward compatibility property
    @property
    def year(self) -> int:
        """Get year for backward compatibility. Uses start year of date range."""
        return self.date_range.start_date.year


@dataclass(frozen=True)
class AllTimeStats:
    username: str
    total_years: int
    total_commits: int
    total_prs: int
    total_issues: int
    total_discussions: int
    total_reviews: int
    private_contributions: int
    lines_added: int
    lines_deleted: int
    lines_calculation_methods: list[str]
    first_year: int
    last_year: int
    repositories_contributed: int
    starred_repos: int
    followers: int
    following: int
    public_repos: int
    languages: dict[str, int]
    last_updated: datetime


@dataclass(frozen=True)
class CachedReport:
    id: int
    username: str
    year: int  # Keep for backward compatibility with existing database
    start_date: datetime
    end_date: datetime
    total_commits: int
    total_prs: int
    total_issues: int
    total_discussions: int
    total_reviews: int
    repositories_contributed: int
    languages: dict[str, int]
    starred_repos: int
    followers: int
    following: int
    public_repos: int
    private_contributions: int
    lines_added: int
    lines_deleted: int
    lines_calculation_method: str
    created_at: datetime

    @property
    def date_range(self) -> DateRange:
        """Get the date range for this cached report."""
        return DateRange(start_date=self.start_date, end_date=self.end_date)


@dataclass(frozen=True)
class Commit:
    oid: str
    committed_date: str
    additions: int
    deletions: int
    author_login: str


@dataclass(frozen=True)
class PullRequest:
    created_at: str
    additions: int
    deletions: int


@dataclass(frozen=True)
class LineStats:
    """Container for line statistics with calculation method tracking."""

    lines_added: int
    lines_deleted: int
    calculation_method: str
    pr_count: int = 0
    commit_count: int = 0
