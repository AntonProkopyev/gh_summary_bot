from .models import AllTimeStats
from .models import ContributionStats


class TelegramReportTemplate:
    def yearly(self, stats: ContributionStats) -> str:
        """Generate yearly contribution statistics report."""
        total_contributions = stats.total_commits + stats.total_prs + stats.total_issues + stats.total_discussions

        report = f"""
*GitHub Contributions Report*
👤 User: `{stats.username}`
📅 Year: {stats.year}

*📊 Contribution Summary*
• Total Contributions: *{total_contributions:,}*
• Commits: *{stats.total_commits:,}*
• Pull Requests: *{stats.total_prs:,}*
• Issues: *{stats.total_issues:,}*
• Discussions: *{stats.total_discussions:,}*
• Code Reviews: *{stats.total_reviews:,}*

*💻 Code Statistics*
• Lines Added: *{stats.lines_added:,}*
• Lines Deleted: *{stats.lines_deleted:,}*
• Net Lines: *{stats.lines_added - stats.lines_deleted:,}*

*📈 Activity Metrics*
• Repositories Contributed: *{stats.repositories_contributed}*
• Public Repositories: *{stats.public_repos}*
• Private Contributions: *{stats.private_contributions}*

*🌟 Social Stats*
• Starred Repos: *{stats.starred_repos:,}*
• Followers: *{stats.followers:,}*
• Following: *{stats.following:,}*

*🔥 Top Languages*
"""

        # Add top 5 languages
        if stats.languages:
            sorted_langs = sorted(stats.languages.items(), key=lambda x: x[1], reverse=True)[:5]
            for i, (lang, count) in enumerate(sorted_langs, 1):
                report += f"{i}. {lang}: {count} commits\n"
        else:
            report += "No language data available\n"

        return report

    def alltime(self, stats: AllTimeStats) -> str:
        """Generate all-time aggregated statistics report."""
        total_contributions = stats.total_commits + stats.total_prs + stats.total_issues + stats.total_discussions

        report = f"""
*🌟 All-Time GitHub Statistics*
👤 User: `{stats.username}`
📅 Period: {stats.first_year} - {stats.last_year} ({stats.total_years} years)

*📊 Total Contributions*
• All Contributions: *{total_contributions:,}*
• Commits: *{stats.total_commits:,}*
• Pull Requests: *{stats.total_prs:,}*
• Issues: *{stats.total_issues:,}*
• Discussions: *{stats.total_discussions:,}*
• Code Reviews: *{stats.total_reviews:,}*

*💻 Code Statistics*
• Lines Added: *{stats.lines_added:,}*
• Lines Deleted: *{stats.lines_deleted:,}*
• Net Lines: *{stats.lines_added - stats.lines_deleted:,}*

*📈 Activity Metrics*
• Repositories Contributed: *{stats.repositories_contributed:,}*
• Public Repositories: *{stats.public_repos:,}*
• Private Contributions: *{stats.private_contributions:,}*

*🌟 Social Stats*
• Starred Repos: *{stats.starred_repos:,}*
• Followers: *{stats.followers:,}*
• Following: *{stats.following:,}*

*🔥 Top Languages (All Time)*
"""

        # Add top 10 languages
        if stats.languages:
            sorted_langs = sorted(stats.languages.items(), key=lambda x: x[1], reverse=True)[:10]
            for i, (lang, count) in enumerate(sorted_langs, 1):
                report += f"{i}. {lang}: {count:,} commits\n"
        else:
            report += "No language data available\n"

        report += f"\n_📅 Last updated: {stats.last_updated.strftime('%Y-%m-%d %H:%M UTC')}_"

        return report

    def languages(self, username: str, year: int, languages: dict[str, int]) -> str:
        """Generate language statistics report."""
        if not languages:
            return f"No language data available for {username} ({year})"

        sorted_langs = sorted(languages.items(), key=lambda x: x[1], reverse=True)

        lang_text = f"*Language Statistics for {username} ({year})*\n\n"
        for lang, count in sorted_langs[:10]:
            percentage = (count / sum(languages.values())) * 100
            bar = "█" * int(percentage / 5)
            lang_text += f"`{lang:<12}` {bar} {percentage:.1f}% ({count} commits)\n"

        return lang_text


class ProgressMessage:
    def __init__(self, base_message: str) -> None:
        self._base_message = base_message

    def with_detail(self, detail: str) -> str:
        """Create progress message with detail."""
        return f"{self._base_message}: {detail}"

    def with_progress(self, current: int, total: int) -> str:
        """Create progress message with progress indicator."""
        return f"{self._base_message} - Progress: {current}/{total}"
