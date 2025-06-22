from typing import Dict, List, Optional, Protocol, runtime_checkable

from .models import AllTimeStats, CachedReport, Commit, ContributionStats, PullRequest


@runtime_checkable
class GitHubSource(Protocol):
    """Protocol for GitHub data sources."""

    async def contributions(self, username: str, year: int) -> ContributionStats:
        """Fetch user contribution statistics for a specific year."""
        ...

    async def commits(self, username: str, year: int) -> List[Commit]:
        """Fetch all commits for a user in a specific year."""
        ...

    async def pull_requests(self, username: str) -> List[PullRequest]:
        """Fetch all pull requests for a user."""
        ...


@runtime_checkable
class ReportStorage(Protocol):
    """Protocol for storing and retrieving contribution reports."""

    async def store(self, stats: ContributionStats) -> int:
        """Store contribution statistics."""
        ...

    async def retrieve(self, username: str, year: int) -> Optional[CachedReport]:
        """Retrieve stored contribution report."""
        ...

    async def aggregated(self, username: str) -> Optional[AllTimeStats]:
        """Retrieve aggregated all-time statistics."""
        ...

    async def years(self, username: str) -> List[int]:
        """Get years with existing reports for a user."""
        ...


@runtime_checkable
class UserStorage(Protocol):
    """Protocol for storing user data."""

    async def store_user(
        self, telegram_id: int, github_username: Optional[str] = None
    ) -> None:
        """Store telegram user association."""
        ...


@runtime_checkable
class PRCache(Protocol):
    """Protocol for caching pull request data."""

    async def cached_prs(self, username: str) -> List[PullRequest]:
        """Get cached pull requests for a user."""
        ...

    async def cache_prs(self, username: str, prs: List[PullRequest]) -> None:
        """Cache pull requests for a user."""
        ...

    async def has_cache(self, username: str) -> bool:
        """Check if user has cached PR data."""
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

    def languages(self, username: str, year: int, languages: Dict[str, int]) -> str:
        """Generate language statistics."""
        ...


@runtime_checkable
class ProgressReporter(Protocol):
    """Protocol for reporting progress during operations."""

    async def report(self, message: str) -> None:
        """Report progress message."""
        ...
