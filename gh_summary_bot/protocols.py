from typing import Protocol
from typing import runtime_checkable

from .models import AllTimeStats
from .models import CachedReport
from .models import ContributionStats
from .models import DateRange


@runtime_checkable
class GitHubSource(Protocol):
    """Protocol for GitHub data sources."""

    async def contributions(self, username: str, date_range: DateRange) -> ContributionStats:
        """Fetch user contribution statistics for a date range."""
        ...

    def with_progress_reporter(self, progress: "ProgressReporter") -> "GitHubSource":
        """Create new instance with progress reporter."""
        ...


@runtime_checkable
class ReportStorage(Protocol):
    """Protocol for storing and retrieving contribution reports."""

    async def store(self, stats: ContributionStats) -> int:
        """Store contribution statistics."""
        ...

    async def retrieve(self, username: str, year: int) -> CachedReport | None:
        """Retrieve stored contribution report."""
        ...

    async def aggregated(self, username: str) -> AllTimeStats | None:
        """Retrieve aggregated all-time statistics."""
        ...

    async def years(self, username: str) -> list[int]:
        """Get years with existing reports for a user."""
        ...


@runtime_checkable
class UserStorage(Protocol):
    """Protocol for storing user data."""

    async def store_user(self, telegram_id: int, github_username: str | None = None) -> None:
        """Store telegram user association."""
        ...


@runtime_checkable
class BotInterface(Protocol):
    """Protocol for bot command handling."""

    async def start_command(self, user_id: int) -> str:
        """Handle start command and return welcome message."""
        ...

    async def analyze_command(self, username: str, year: int, user_id: int) -> str:
        """Handle analyze command and return formatted report."""
        ...

    async def cached_command(self, username: str, year: int) -> str:
        """Handle cached command and return cached report."""
        ...

    async def alltime_command(self, username: str, user_id: int) -> str:
        """Handle alltime command and return aggregated report."""
        ...


@runtime_checkable
class ReportTemplate(Protocol):
    """Protocol for generating reports."""

    def yearly(self, stats: ContributionStats) -> str:
        """Generate yearly contribution statistics."""
        ...

    def alltime(self, stats: AllTimeStats) -> str:
        """Generate all-time aggregated statistics."""
        ...

    def languages(self, username: str, year: int, languages: dict[str, int]) -> str:
        """Generate language statistics."""
        ...


@runtime_checkable
class ProgressReporter(Protocol):
    """Protocol for reporting progress during operations."""

    async def report(self, message: str) -> None:
        """Report progress message."""
        ...
