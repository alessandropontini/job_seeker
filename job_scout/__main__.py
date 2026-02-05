"""Command line entry point for Job Scout."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List

from job_scout.config import load_config
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
        help="Source name(s), repeatable or comma-separated.",
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
        config = load_config(args.config)
        preference_profile = None
        preference_path = None
        personalization = config.get("personalization", {})
        if isinstance(personalization, dict) and personalization.get(
            "enabled", False
        ):
            preference_path = resolve_profile_path(
                config, args.output_dir
            )
            preference_profile = load_profile(preference_path)
            preference_profile = apply_telegram_feedback(
                preference_profile, config
            )
            save_profile(preference_path, preference_profile)
        salary_rules = config.get("salary_rules", {})
        allow_missing_salary = salary_rules.get("allow_missing_salary")
        if allow_missing_salary is None:
            allow_missing_salary = salary_rules.get("flag_missing_salary", True)
        if args.allow_missing_salary is not None:
            allow_missing_salary = True
        rows, summary = run_pipeline(
            since_days=args.since_days,
            output_dir=args.output_dir,
            config=config,
            strict=args.strict,
            allow_missing_salary=bool(allow_missing_salary),
            sources=args.source,
            preference_profile=preference_profile,
        )
        notification = maybe_notify(
            rows,
            args.output_dir,
            config,
            preference_profile=preference_profile,
            preference_path=preference_path,
        )
        logger = logging.getLogger(__name__)
        logger.info(
            "Run summary: fetched_count=%s normalized_count=%s "
            "candidates_count=%s matches_count=%s notified_count=%s "
            "notification_mode=%s source_counts=%s",
            summary.fetched_count,
            summary.normalized_count,
            summary.candidates_count,
            summary.matches_count,
            notification.notified_count,
            notification.notification_mode,
            summary.source_counts,
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
