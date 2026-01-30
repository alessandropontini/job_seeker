"""Command line entry point for Job Scout."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List

from job_scout.config import load_config
from job_scout.pipeline import run_pipeline
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
        salary_rules = config.get("salary_rules", {})
        allow_missing_salary = salary_rules.get("allow_missing_salary")
        if allow_missing_salary is None:
            allow_missing_salary = salary_rules.get("flag_missing_salary", True)
        if args.allow_missing_salary is not None:
            allow_missing_salary = True
        run_pipeline(
            since_days=args.since_days,
            output_dir=args.output_dir,
            config=config,
            strict=args.strict,
            allow_missing_salary=bool(allow_missing_salary),
            sources=args.source,
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
