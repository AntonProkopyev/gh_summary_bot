"""Data models for GitHub contribution analysis."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict


@dataclass(frozen=True)
class ContributionStats:
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
    created_at: datetime = field(default_factory=datetime.now)


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
    first_year: int
    last_year: int
    repositories_contributed: int
    starred_repos: int
    followers: int
    following: int
    public_repos: int
    languages: Dict[str, int]
    last_updated: datetime


@dataclass(frozen=True)
class CachedReport:
    id: int
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
    created_at: datetime


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
    """Container for line statistics from pull requests."""

    lines_added: int
    lines_deleted: int
    pr_count: int = 0
