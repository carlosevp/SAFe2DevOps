from __future__ import annotations

from statistics import median

from app.integrations.ado.types import AdoCommit, AdoNormalizedEvidence, AdoPipelineRun, AdoPullRequest
from app.integrations.http import sanitize_remote_text


def normalize_ado_evidence(
    *,
    commits: list[AdoCommit],
    pull_requests: list[AdoPullRequest],
    runs: list[AdoPipelineRun],
    connection_ok: bool = True,
) -> AdoNormalizedEvidence:
    if not connection_ok:
        return _empty("connection_failure", "Azure DevOps connection failed; no data retrieved.")

    for commit in commits:
        commit.comment = sanitize_remote_text(commit.comment)
        commit.author = sanitize_remote_text(commit.author)
    for pr in pull_requests:
        pr.title = sanitize_remote_text(pr.title)

    if not commits and not pull_requests and not runs:
        return _empty("no_activity", "No Azure DevOps activity found in the lookback window.")

    completed = [pr for pr in pull_requests if pr.status == "completed"]
    abandoned = [pr for pr in pull_requests if pr.status == "abandoned"]
    pr_durations = [
        (pr.closed - pr.created).total_seconds() / 86400.0
        for pr in completed
        if pr.closed is not None
    ]
    reviews = [len(pr.reviewers) for pr in completed]
    linked = sum(1 for pr in completed if pr.jira_keys)
    linkage = (linked / len(completed)) if completed else None
    active_days = len({c.date.date() for c in commits})
    direct = sum(1 for c in commits if c.to_default_branch)
    succeeded = [r for r in runs if r.result == "succeeded"]
    failed = [r for r in runs if r.result == "failed"]
    success_rate = (len(succeeded) / len(runs) * 100.0) if runs else None
    durations = [r.duration_seconds for r in runs if r.duration_seconds is not None]
    deploy_count = sum(1 for r in runs if r.is_deployment)

    recovery_hours: list[float] = []
    ordered = sorted(runs, key=lambda r: r.started)
    for idx, run in enumerate(ordered):
        if run.result != "failed":
            continue
        for nxt in ordered[idx + 1 :]:
            if nxt.pipeline_name == run.pipeline_name and nxt.result == "succeeded":
                recovery_hours.append((nxt.started - run.started).total_seconds() / 3600.0)
                break

    limitations: list[dict[str, str]] = []
    quality = "reliable"
    if len(commits) < 10:
        limitations.append(
            {"code": "incomplete_tool_adoption", "message": "Low commit volume may indicate incomplete ADO adoption."}
        )
        quality = "incomplete_adoption"
    if linkage is not None and linkage < 0.5:
        limitations.append(
            {
                "code": "reliable_immature_signal",
                "message": "Jira-key linkage is weak; work tracking and code changes are loosely coupled.",
            }
        )
        if quality == "reliable":
            quality = "reliable_immature"
    if success_rate is not None and success_rate < 80:
        limitations.append(
            {
                "code": "reliable_immature_signal",
                "message": "Pipeline success rate is below 80%, indicating delivery instability.",
            }
        )
        if quality == "reliable":
            quality = "reliable_immature"

    median_pr = round(median(pr_durations), 1) if pr_durations else None
    review_avg = round(median(reviews), 1) if reviews else None
    median_build = round(median(durations), 1) if durations else None
    recovery = round(median(recovery_hours), 1) if recovery_hours else None

    metrics = [
        _m("ado_commits", "Commit activity", f"{len(commits)} commits", float(len(commits)), "up"),
        _m("ado_active_commit_days", "Active commit days", str(active_days), float(active_days), "up"),
        _m("ado_prs_completed", "Pull requests completed", str(len(completed)), float(len(completed)), "up"),
        _m("ado_prs_abandoned", "Abandoned PRs", str(len(abandoned)), float(len(abandoned)), "down"),
        _m(
            "ado_median_pr_days",
            "Median PR completion",
            f"{median_pr} days" if median_pr is not None else "n/a",
            median_pr,
            "down",
        ),
        _m(
            "ado_avg_reviews",
            "Avg PR reviews",
            str(review_avg) if review_avg is not None else "n/a",
            review_avg,
            "up",
        ),
        _m("ado_direct_default_commits", "Direct commits to default branch", str(direct), float(direct), "down"),
        _m(
            "ado_jira_linkage",
            "Jira-key linkage",
            f"{int((linkage or 0) * 100)}%" if linkage is not None else "n/a",
            (linkage or 0) * 100 if linkage is not None else None,
            "up",
        ),
        _m("ado_pipeline_runs", "Pipeline runs", str(len(runs)), float(len(runs)), "up"),
        _m(
            "ado_pipeline_success",
            "Pipeline success rate",
            f"{int(success_rate)}%" if success_rate is not None else "n/a",
            success_rate,
            "neutral",
        ),
        _m("ado_failed_runs", "Failed-run frequency", str(len(failed)), float(len(failed)), "down"),
        _m(
            "ado_build_duration",
            "Median build duration",
            f"{median_build}s" if median_build is not None else "n/a",
            median_build,
            "neutral",
        ),
        _m(
            "ado_recovery_hours",
            "Time to next success after failure",
            f"{recovery}h" if recovery is not None else "n/a",
            recovery,
            "down",
        ),
        _m("ado_deployments", "Deployment activity", str(deploy_count), float(deploy_count), "up"),
    ]

    return AdoNormalizedEvidence(
        commits_in_period=len(commits),
        active_commit_days=active_days,
        completed_pr_count=len(completed),
        abandoned_pr_count=len(abandoned),
        median_pr_completion_days=median_pr,
        review_participation_avg=review_avg,
        direct_commits_to_default_branch=direct,
        jira_key_linkage_rate=round(linkage, 2) if linkage is not None else None,
        pipeline_run_frequency=len(runs),
        pipeline_success_rate=round(success_rate, 1) if success_rate is not None else None,
        failed_run_frequency=len(failed),
        median_build_duration_seconds=median_build,
        time_to_next_success_after_failure_hours=recovery,
        deployment_activity=deploy_count,
        limitations=limitations,
        quality=quality,
        metrics=metrics,
    )


def apply_exclusions(
    *,
    commits: list[AdoCommit],
    pull_requests: list[AdoPullRequest],
    runs: list[AdoPipelineRun],
    exclusions: set[str],
) -> tuple[list[AdoCommit], list[AdoPullRequest], list[AdoPipelineRun]]:
    filtered_commits = commits
    filtered_prs = pull_requests
    filtered_runs = runs
    if "Bot commits" in exclusions:
        filtered_commits = [c for c in filtered_commits if "bot@" not in c.author.lower() and "dependabot" not in c.comment.lower()]
    if "Emergency hotfix issues" in exclusions:
        filtered_prs = [pr for pr in filtered_prs if "hotfix" not in pr.title.lower()]
    if "Experimental pipelines" in exclusions:
        filtered_runs = [r for r in filtered_runs if "experimental" not in r.pipeline_name.lower()]
    if "Data migration work" in exclusions:
        filtered_prs = [pr for pr in filtered_prs if "migration" not in pr.title.lower()]
        filtered_commits = [c for c in filtered_commits if "migration" not in c.comment.lower()]
    if "Dormant branches" in exclusions:
        # No direct branch list here; treat as PR filter noop for mock.
        pass
    if "One-time setup tasks" in exclusions:
        filtered_prs = [pr for pr in filtered_prs if "setup" not in pr.title.lower()]
    return filtered_commits, filtered_prs, filtered_runs


def _empty(code: str, message: str) -> AdoNormalizedEvidence:
    return AdoNormalizedEvidence(
        commits_in_period=0,
        active_commit_days=0,
        completed_pr_count=0,
        abandoned_pr_count=0,
        median_pr_completion_days=None,
        review_participation_avg=None,
        direct_commits_to_default_branch=0,
        jira_key_linkage_rate=None,
        pipeline_run_frequency=0,
        pipeline_success_rate=None,
        failed_run_frequency=0,
        median_build_duration_seconds=None,
        time_to_next_success_after_failure_hours=None,
        deployment_activity=0,
        limitations=[{"code": code, "message": message}],
        quality=code,
        metrics=[],
    )


def _m(key: str, label: str, value_text: str, value_numeric: float | None, trend: str) -> dict:
    return {
        "key": key,
        "label": label,
        "value_text": value_text,
        "value_numeric": value_numeric,
        "source_system": "azdo",
        "provenance": f"azdo:normalized:{key}",
        "trend": trend,
        "freshness_label": "snapshot",
    }

