"""Data models for GitHub contribution analysis."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass
class ContributionStats:
    """Data class for GitHub contribution statistics"""

    username: str
    year: int
    total_commits: int
    total_prs: int
    total_issues: int
    total_discussions: int
    total_reviews: int
    repositories_contributed: int
    languages: Dict[str, int]
    starred_repos: int
    followers: int
    following: int
    public_repos: int
    private_contributions: int
    lines_added: int
    lines_deleted: int
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
