import pathlib

from jinja2 import Environment
from jinja2 import FileSystemLoader

from gh_summary_bot.models import ContributionStats


class TelegramReportTemplate:
    def __init__(self) -> None:
        template_dir = pathlib.Path(__file__).parent
        self._env = Environment(
            loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True, autoescape=True
        )
        self._env.filters["format_number"] = lambda x: f"{x:,}"
        self._yearly_template = self._env.get_template("yearly_template.j2")

    def yearly(self, stats: ContributionStats) -> str:
        """Generate yearly contribution statistics report."""
        total_contributions = stats.total_commits + stats.total_prs + stats.total_issues + stats.total_discussions

        languages = []
        if stats.languages:
            languages = sorted(stats.languages.items(), key=lambda x: x[1], reverse=True)

        context = {
            "username": stats.username,
            "year": stats.year,  # Keep for backward compatibility
            "date_range": stats.date_range.description(),
            "total_contributions": total_contributions,
            "total_commits": stats.total_commits,
            "total_prs": stats.total_prs,
            "total_issues": stats.total_issues,
            "total_discussions": stats.total_discussions,
            "total_reviews": stats.total_reviews,
            "lines_added": stats.lines_added,
            "lines_deleted": stats.lines_deleted,
            "net_lines": stats.lines_added - stats.lines_deleted,
            "lines_calculation_method": stats.lines_calculation_method,
            "repositories_contributed": stats.repositories_contributed,
            "public_repos": stats.public_repos,
            "private_contributions": stats.private_contributions,
            "starred_repos": stats.starred_repos,
            "followers": stats.followers,
            "following": stats.following,
            "languages": languages,
        }

        return self._yearly_template.render(**context)
