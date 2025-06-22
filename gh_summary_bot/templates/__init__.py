import pathlib

from jinja2 import Environment
from jinja2 import FileSystemLoader

from gh_summary_bot.models import AllTimeStats
from gh_summary_bot.models import ContributionStats


class TelegramReportTemplate:
    def __init__(self) -> None:
        template_dir = pathlib.Path(__file__).parent
        self._env = Environment(
            loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True, autoescape=True
        )
        self._env.filters["format_number"] = lambda x: f"{x:,}"
        self._yearly_template = self._env.get_template("yearly_template.j2")
        self._alltime_template = self._env.get_template("alltime_template.j2")
        self._languages_template = self._env.get_template("languages_template.j2")

    def yearly(self, stats: ContributionStats) -> str:
        """Generate yearly contribution statistics report."""
        total_contributions = stats.total_commits + stats.total_prs + stats.total_issues + stats.total_discussions

        languages = []
        if stats.languages:
            languages = sorted(stats.languages.items(), key=lambda x: x[1], reverse=True)

        context = {
            "username": stats.username,
            "year": stats.year,
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

    def alltime(self, stats: AllTimeStats) -> str:
        """Generate all-time aggregated statistics report."""
        total_contributions = stats.total_commits + stats.total_prs + stats.total_issues + stats.total_discussions

        languages = []
        if stats.languages:
            languages = sorted(stats.languages.items(), key=lambda x: x[1], reverse=True)

        context = {
            "username": stats.username,
            "first_year": stats.first_year,
            "last_year": stats.last_year,
            "total_years": stats.total_years,
            "total_contributions": total_contributions,
            "total_commits": stats.total_commits,
            "total_prs": stats.total_prs,
            "total_issues": stats.total_issues,
            "total_discussions": stats.total_discussions,
            "total_reviews": stats.total_reviews,
            "lines_added": stats.lines_added,
            "lines_deleted": stats.lines_deleted,
            "net_lines": stats.lines_added - stats.lines_deleted,
            "lines_calculation_methods": stats.lines_calculation_methods,
            "repositories_contributed": stats.repositories_contributed,
            "public_repos": stats.public_repos,
            "private_contributions": stats.private_contributions,
            "starred_repos": stats.starred_repos,
            "followers": stats.followers,
            "following": stats.following,
            "languages": languages,
            "last_updated": stats.last_updated.strftime("%Y-%m-%d %H:%M UTC"),
        }

        return self._alltime_template.render(**context)

    def languages(self, username: str, year: int, languages: dict[str, int]) -> str:
        """Generate language statistics report."""
        if not languages:
            context = {"username": username, "year": year, "languages": []}
            return self._languages_template.render(**context)

        sorted_langs = sorted(languages.items(), key=lambda x: x[1], reverse=True)
        total_commits = sum(languages.values())

        formatted_languages = []
        for lang, count in sorted_langs:
            percentage = (count / total_commits) * 100
            bar = "█" * int(percentage / 5)
            formatted_languages.append((lang, count, f"{percentage:.1f}", bar))

        context = {"username": username, "year": year, "languages": formatted_languages}

        return self._languages_template.render(**context)


class ProgressMessage:
    def __init__(self, base_message: str) -> None:
        self._base_message = base_message

    def __str__(self) -> str:
        """Return the base message."""
        return self._base_message

    def with_detail(self, detail: str) -> str:
        """Create progress message with detail."""
        return f"{self._base_message}: {detail}"

    def with_progress(self, current: int, total: int) -> str:
        """Create progress message with progress indicator."""
        return f"{self._base_message} - Progress: {current}/{total}"
