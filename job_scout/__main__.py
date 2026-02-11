"""Command line entry point for Job Scout."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import List

from job_scout.config import load_config
from job_scout.feedback import (
    apply_feedback_items,
    fetch_feedback,
    load_previous_run,
    record_feedback_in_last_run,
    write_feedback_summary,
)
from job_scout.notifications import maybe_notify
from job_scout.pipeline import run_pipeline
from job_scout.preferences import (
    apply_telegram_feedback,
    load_profile,
    resolve_profile_path,
    save_profile,
)
from job_scout.sources import AVAILABLE_SOURCES


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="job_scout")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the job pipeline")
    run_parser.add_argument("--since-days", type=int, default=1)
    run_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/config.yaml"),
    )
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("out"),
    )
    run_parser.add_argument(
        "--state-suffix",
        help="Suffix to isolate state files (last_run/last_notified/preferences).",
    )
    run_parser.add_argument(
        "--state-dir",
        type=Path,
        help="Alternate base directory for state files.",
    )
    run_parser.add_argument(
        "--strict",
        action="store_true",
        help="Reject postings with missing mandatory data.",
    )
    run_parser.add_argument(
        "--allow-missing-salary",
        action="store_true",
        default=None,
        help="Override config to allow missing salary postings.",
    )
    run_parser.add_argument(
        "--source",
        action="append",
        help="Source name(s), repeatable or comma-separated (legacy-compatible).",
    )
    run_parser.add_argument(
        "--sources",
        help="Multi-source selector (comma-separated or 'all').",
    )
    run_parser.add_argument(
        "--fixture-file",
        type=Path,
        help=(
            "Path to a dummy-source fixture JSON file. "
            "When provided, the dummy source uses this file."
        ),
    )
    run_parser.add_argument(
        "--telegram-real",
        action="store_true",
        help=(
            "Enable real Telegram sends for this run only. "
            "Requires JOB_SCOUT_E2E_REAL_TELEGRAM=1."
        ),
    )
    run_parser.add_argument(
        "--run-mode",
        choices=("manual", "scheduled"),
        help="Execution mode controlling notification semantics.",
    )
    run_parser.add_argument(
        "--force-send",
        action="store_true",
        help="Send Telegram diagnostics even when there are zero matches.",
    )
    run_parser.add_argument(
        "--feedback-smoke-check",
        action="store_true",
        help="Validate feedback button callback_data payloads in telegram_payload.json.",
    )

    sources_parser = subparsers.add_parser(
        "sources", help="Inspect available sources"
    )
    sources_parser.add_argument("--list", action="store_true")
    sources_parser.add_argument(
        "--test",
        nargs="?",
        const="dummy",
        help="Test a source by name (default: dummy).",
    )
    sources_parser.add_argument("--since-days", type=int, default=1)

    return parser


def _resolve_cli_sources(args: argparse.Namespace) -> list[str] | None:
    selected: list[str] = []
    if args.source:
        selected.extend(args.source)
    if args.sources:
        selected.append(args.sources)

    resolved: list[str] = []
    for entry in selected:
        for name in entry.split(","):
            cleaned = name.strip().lower()
            if not cleaned:
                continue
            if cleaned == "all":
                return ["all"]
            if cleaned not in resolved:
                resolved.append(cleaned)
    return resolved or None


def _resolve_run_mode(args: argparse.Namespace, config: dict[str, object]) -> str:
    runtime = config.get("runtime")
    config_mode = None
    if isinstance(runtime, dict):
        raw_mode = runtime.get("run_mode")
        if isinstance(raw_mode, str):
            config_mode = raw_mode.strip().lower()
    env_mode = os.getenv("JOB_SCOUT_RUN_MODE", "").strip().lower()
    arg_mode = (args.run_mode or "").strip().lower()
    for candidate in (arg_mode, env_mode, config_mode):
        if candidate in {"manual", "scheduled"}:
            return candidate
    return "scheduled"


def _write_run_summary(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _run_feedback_smoke_check(output_dir: Path) -> dict[str, object]:
    payload_path = output_dir / "telegram_payload.json"
    if not payload_path.exists():
        return {"ok": False, "reason": "missing_telegram_payload"}
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    callbacks: list[str] = []
    for message in payload.get("messages", []):
        reply_markup = message.get("reply_markup") or {}
        keyboard = reply_markup.get("inline_keyboard") or []
        for row in keyboard:
            for button in row:
                callback_data = button.get("callback_data")
                if isinstance(callback_data, str):
                    callbacks.append(callback_data)
    if not callbacks:
        return {"ok": False, "reason": "no_callback_data"}
    too_long = [item for item in callbacks if len(item.encode("utf-8")) > 64]
    if too_long:
        return {
            "ok": False,
            "reason": "callback_data_too_long",
            "count": len(too_long),
        }
    return {"ok": True, "reason": "ok", "count": len(callbacks)}




def main(argv: List[str] | None = None) -> int:
    _configure_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "sources":
        if args.list:
            for name in AVAILABLE_SOURCES:
                print(name)
            return 0
        if args.test:
            fetcher = AVAILABLE_SOURCES.get(args.test)
            if not fetcher:
                parser.error(f"unknown source: {args.test}")
            postings = fetcher(args.since_days)
            print(f"{args.test}: {len(postings)} postings")
            return 0
        parser.error("sources requires --list or --test")

    if args.command == "run":
        if args.telegram_real:
            os.environ["JOB_SCOUT_TELEGRAM_MODE"] = "real"
        if args.fixture_file:
            os.environ["JOB_SCOUT_DUMMY_FIXTURE_FILE"] = str(
                args.fixture_file
            )
        config = load_config(args.config)
        state_config = config.get("state")
        if not isinstance(state_config, dict):
            state_config = {}
        if args.state_suffix:
            state_config["suffix"] = args.state_suffix
        if args.state_dir:
            state_config["dir"] = str(args.state_dir)
        if state_config:
            config["state"] = state_config
        run_mode = _resolve_run_mode(args, config)
        force_send = bool(args.force_send or run_mode == "manual")
        feedback_fetch_reason = "not_requested"
        feedback_items_count = 0
        feedback_endpoint = "/feedback"
        preference_profile = None
        preference_path = None
        personalization = config.get("personalization", {})
        if isinstance(personalization, dict) and personalization.get(
            "enabled", False
        ):
            state_suffix = None
            state_dir = None
            state_config = config.get("state")
            if isinstance(state_config, dict):
                state_suffix = state_config.get("suffix")
                state_dir = state_config.get("dir")
            preference_path = resolve_profile_path(
                config,
                args.output_dir,
                state_dir=state_dir,
                state_suffix=state_suffix,
            )
            preference_profile = load_profile(preference_path)
            feedback_config = config.get("feedback", {})
            feedback_use_updates = False
            if isinstance(feedback_config, dict):
                feedback_use_updates = bool(
                    feedback_config.get("use_telegram_updates", False)
                )
            if feedback_use_updates:
                preference_profile = apply_telegram_feedback(
                    preference_profile, config
                )
            previous_run_id, job_lookup = load_previous_run(
                args.output_dir, config
            )
            if previous_run_id:
                feedback_items, reason = fetch_feedback(
                    run_id=previous_run_id, config=config
                )
                feedback_items_count = len(feedback_items)
                feedback_fetch_reason = reason or "ok"
                if reason:
                    logging.getLogger(__name__).info(
                        "Feedback fetch skipped: %s.", reason
                    )
                else:
                    result = apply_feedback_items(
                        preference_profile,
                        feedback_items,
                        job_lookup,
                        config,
                    )
                    preference_profile = result.updated_profile
                    write_feedback_summary(
                        args.output_dir, config, result.counts
                    )
                    record_feedback_in_last_run(
                        args.output_dir, config, result.counts
                    )
                    logging.getLogger(__name__).info(
                        "Feedback applied: %s.",
                        ", ".join(
                            f"{key}={value}"
                            for key, value in result.counts.items()
                        ),
                    )
            save_profile(preference_path, preference_profile)
        salary_rules = config.get("salary_rules", {})
        allow_missing_salary = salary_rules.get("allow_missing_salary")
        if allow_missing_salary is None:
            allow_missing_salary = salary_rules.get("flag_missing_salary", True)
        if args.allow_missing_salary is not None:
            allow_missing_salary = True
        selected_sources = _resolve_cli_sources(args)
        rows, summary = run_pipeline(
            since_days=args.since_days,
            output_dir=args.output_dir,
            config=config,
            strict=args.strict,
            allow_missing_salary=bool(allow_missing_salary),
            sources=selected_sources,
            preference_profile=preference_profile,
        )
        notification = maybe_notify(
            rows,
            args.output_dir,
            config,
            preference_profile=preference_profile,
            preference_path=preference_path,
            run_mode=run_mode,
            force_send=force_send,
        )
        feedback_smoke = {"ok": False, "reason": "not_enabled"}
        if args.feedback_smoke_check or run_mode == "manual":
            feedback_smoke = _run_feedback_smoke_check(args.output_dir)

        logger = logging.getLogger(__name__)
        logger.info(
            "Run diagnostics: run_mode=%s force_send=%s window_start=%s window_end=%s timezone=%s",
            run_mode,
            force_send,
            notification.window_start,
            notification.window_end,
            (notification.diagnostics or {}).get("timezone", "Europe/Rome"),
        )
        logger.info(
            "Run summary: fetched_count=%s normalized_count=%s candidates_count=%s matches_count=%s notified_count=%s notification_mode=%s reason=%s source_counts=%s",
            summary.fetched_count,
            summary.normalized_count,
            summary.candidates_count,
            summary.matches_count,
            notification.notified_count,
            notification.notification_mode,
            notification.skipped_reason or "sent",
            summary.source_counts,
        )
        reason = notification.skipped_reason or "sent"
        if reason in {"duplicate_digest", "already_notified_today"}:
            reason = "deduped"
        run_summary = {
            "run_mode": run_mode,
            "force_send": force_send,
            "source": selected_sources or config.get("sources", {}).get("enabled", []),
            "since_days": args.since_days,
            "window_start": notification.window_start,
            "window_end": notification.window_end,
            "timezone": (notification.diagnostics or {}).get("timezone", "Europe/Rome"),
            "local_date": notification.digest_date_local,
            "fetched_count": summary.fetched_count,
            "normalized_count": summary.normalized_count,
            "candidates_count": summary.candidates_count,
            "matches_count": summary.matches_count,
            "notified": "yes" if notification.notified else "no",
            "reason": reason,
            "notification_mode": notification.notification_mode,
            "source_counts": summary.source_counts,
            "telegram_attempted": notification.telegram_attempted,
            "telegram_ok": notification.telegram_ok,
            "telegram_message_id": notification.telegram_message_id,
            "telegram_chat_id_fingerprint": notification.telegram_chat_id_fingerprint,
            "telegram_thread_id": notification.telegram_thread_id,
            "telegram_error_code": notification.telegram_error_code,
            "telegram_description": notification.telegram_description,
            "feedback_enabled": bool(config.get("feedback", {}).get("enabled", False)) if isinstance(config.get("feedback"), dict) else False,
            "feedback_endpoint": "/window/open, /feedback",
            "fetch_feedback": {
                "items_count": feedback_items_count,
                "reason": feedback_fetch_reason,
            },
            "feedback_smoke_check": feedback_smoke,
        }
        chat_check = (notification.diagnostics or {}).get("chat_check")
        if isinstance(chat_check, dict):
            run_summary["telegram_chat_check"] = chat_check
            if run_mode == "manual" and chat_check.get("is_forum") and notification.telegram_thread_id is None:
                run_summary["warning_missing_thread_id"] = True
        _write_run_summary(args.output_dir / "run_summary.json", run_summary)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
