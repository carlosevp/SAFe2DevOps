from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from statistics import median

from app.integrations.http import sanitize_remote_text
from app.integrations.jira.types import JiraIssue, JiraNormalizedEvidence


def normalize_jira_issues(
    issues: list[JiraIssue],
    *,
    lookback_days: int,
    connection_ok: bool = True,
) -> JiraNormalizedEvidence:
    if not connection_ok:
        return JiraNormalizedEvidence(
            completed_items=0,
            issue_type_distribution={},
            bugs_created=0,
            bugs_resolved=0,
            approximate_cycle_time_days=None,
            issue_aging_days_p50=None,
            reopened_work=0,
            approximate_wip=0,
            release_version_usage=0,
            acceptance_criteria_presence_rate=None,
            limitations=[
                {
                    "code": "connection_failure",
                    "message": "Jira connection failed; no issues retrieved.",
                }
            ],
            quality="connection_failure",
            metrics=[],
            raw_issue_count=0,
        )

    # Sanitize untrusted remote fields before aggregation.
    for issue in issues:
        issue.summary = sanitize_remote_text(issue.summary)
        if issue.acceptance_criteria:
            issue.acceptance_criteria = sanitize_remote_text(issue.acceptance_criteria)

    if not issues:
        return JiraNormalizedEvidence(
            completed_items=0,
            issue_type_distribution={},
            bugs_created=0,
            bugs_resolved=0,
            approximate_cycle_time_days=None,
            issue_aging_days_p50=None,
            reopened_work=0,
            approximate_wip=0,
            release_version_usage=0,
            acceptance_criteria_presence_rate=None,
            limitations=[
                {"code": "no_activity", "message": "No Jira issues found in the lookback window."}
            ],
            quality="no_activity",
            metrics=_metric_rows(0, {}, 0, 0, None, None, 0, 0, 0, None),
            raw_issue_count=0,
        )

    completed = [i for i in issues if i.resolved is not None]
    bugs_created = [i for i in issues if i.issue_type.lower() == "bug"]
    bugs_resolved = [i for i in bugs_created if i.resolved is not None]
    type_dist = dict(Counter(i.issue_type for i in issues))
    cycle_samples = [
        (i.resolved - i.created).total_seconds() / 86400.0
        for i in completed
        if i.resolved is not None
    ]
    now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    aging = [(now - i.created).total_seconds() / 86400.0 for i in issues if i.resolved is None]
    wip = sum(
        1
        for i in issues
        if i.status.lower() in {"in progress", "in review", "selected for development"}
    )
    with_ac = sum(1 for i in issues if i.acceptance_criteria)
    ac_rate = with_ac / len(issues) if issues else None
    reopened = sum(1 for i in issues if i.reopened)
    release_usage = sum(
        1 for i in issues if any(c.get("field") == "Fix Version" for c in i.changelog)
    )

    limitations: list[dict[str, str]] = []
    quality = "reliable"
    if len(issues) < 5:
        limitations.append(
            {
                "code": "incomplete_tool_adoption",
                "message": "Very few issues in period; tooling may be underused.",
            }
        )
        quality = "incomplete_adoption"
    if lookback_days < 45 and len(completed) < 10:
        limitations.append(
            {
                "code": "unrepresentative_selection",
                "message": "Short lookback with limited completions may not represent normal delivery.",
            }
        )
        quality = "unrepresentative"
    if cycle_samples and median(cycle_samples) > 14:
        limitations.append(
            {
                "code": "reliable_immature_signal",
                "message": "Cycle time is elevated; evidence may indicate immature flow practices.",
            }
        )
        if quality == "reliable":
            quality = "reliable_immature"

    cycle = round(median(cycle_samples), 1) if cycle_samples else None
    aging_p50 = round(median(aging), 1) if aging else None

    return JiraNormalizedEvidence(
        completed_items=len(completed),
        issue_type_distribution=type_dist,
        bugs_created=len(bugs_created),
        bugs_resolved=len(bugs_resolved),
        approximate_cycle_time_days=cycle,
        issue_aging_days_p50=aging_p50,
        reopened_work=reopened,
        approximate_wip=wip,
        release_version_usage=release_usage,
        acceptance_criteria_presence_rate=round(ac_rate, 2) if ac_rate is not None else None,
        limitations=limitations,
        quality=quality,
        metrics=_metric_rows(
            len(completed),
            type_dist,
            len(bugs_created),
            len(bugs_resolved),
            cycle,
            aging_p50,
            reopened,
            wip,
            release_usage,
            ac_rate,
        ),
        raw_issue_count=len(issues),
    )


def _metric_rows(
    completed: int,
    type_dist: dict[str, int],
    bugs_created: int,
    bugs_resolved: int,
    cycle: float | None,
    aging: float | None,
    reopened: int,
    wip: int,
    release_usage: int,
    ac_rate: float | None,
) -> list[dict]:
    return [
        _m("jira_completed_items", "Jira items completed", str(completed), float(completed), "up"),
        _m("jira_bugs_created", "Bugs created", str(bugs_created), float(bugs_created), "neutral"),
        _m("jira_bugs_resolved", "Bugs resolved", str(bugs_resolved), float(bugs_resolved), "up"),
        _m(
            "jira_cycle_time_days",
            "Median cycle time",
            f"{cycle} days" if cycle is not None else "n/a",
            cycle,
            "down" if cycle and cycle > 7 else "neutral",
        ),
        _m(
            "jira_issue_aging_p50",
            "Open issue aging (p50)",
            f"{aging} days" if aging is not None else "n/a",
            aging,
            "neutral",
        ),
        _m("jira_reopened_work", "Reopened work", str(reopened), float(reopened), "down"),
        _m("jira_wip", "Work in progress", f"{wip} items", float(wip), "neutral"),
        _m(
            "jira_release_usage",
            "Release/version usage",
            str(release_usage),
            float(release_usage),
            "up",
        ),
        _m(
            "jira_ac_presence_rate",
            "Acceptance criteria presence",
            f"{int((ac_rate or 0) * 100)}%" if ac_rate is not None else "n/a",
            (ac_rate or 0) * 100 if ac_rate is not None else None,
            "up",
        ),
        _m(
            "jira_issue_type_mix",
            "Issue-type mix",
            ", ".join(f"{k}:{v}" for k, v in sorted(type_dist.items())[:4]) or "n/a",
            None,
            "neutral",
        ),
    ]


def _m(key: str, label: str, value_text: str, value_numeric: float | None, trend: str) -> dict:
    return {
        "key": key,
        "label": label,
        "value_text": value_text,
        "value_numeric": value_numeric,
        "source_system": "jira",
        "provenance": f"jira:normalized:{key}",
        "trend": trend,
        "freshness_label": "snapshot",
    }
