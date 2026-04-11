"""Source registry for job postings and their public attribution metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from job_scout.normalize import SourceJob
from job_scout.sources.arbeitnow import fetch_arbeitnow
from job_scout.sources.dummy import fetch_dummy
from job_scout.sources.greenhouse import (
    GREENHOUSE_BOARD_API_TEMPLATE,
    GREENHOUSE_DEFAULT_BOARDS,
    fetch_greenhouse,
)
from job_scout.sources.lever import (
    LEVER_DEFAULT_COMPANIES,
    LEVER_POSTINGS_API_TEMPLATE,
    fetch_lever,
)
from job_scout.sources.remotive import REMOTIVE_API_URL, fetch_remotive
from job_scout.sources.wwr import WWR_RSS_URL, fetch_wwr


@dataclass(frozen=True)
class SourceCatalogEntry:
    """Public metadata describing a source and how Job Scout accesses it."""

    name: str
    site_url: str
    access_url: str
    transport: str
    attribution: str
    fetcher: Callable[[int], list[SourceJob]]


SOURCE_CATALOG = {
    "dummy": SourceCatalogEntry(
        name="dummy",
        site_url="https://example.com",
        access_url="local fixture / synthetic dataset",
        transport="fixture",
        attribution="Local offline fixture source for tests and smoke runs.",
        fetcher=fetch_dummy,
    ),
    "remotive": SourceCatalogEntry(
        name="remotive",
        site_url="https://remotive.com/remote-jobs",
        access_url=REMOTIVE_API_URL,
        transport="api",
        attribution="Remotive public API",
        fetcher=fetch_remotive,
    ),
    "wwr": SourceCatalogEntry(
        name="wwr",
        site_url="https://weworkremotely.com/remote-jobs",
        access_url=WWR_RSS_URL,
        transport="rss",
        attribution="We Work Remotely public RSS",
        fetcher=fetch_wwr,
    ),
    "arbeitnow": SourceCatalogEntry(
        name="arbeitnow",
        site_url="https://www.arbeitnow.com/jobs",
        access_url="https://www.arbeitnow.com/api/job-board-api",
        transport="api",
        attribution="Arbeitnow free public Job Board API",
        fetcher=fetch_arbeitnow,
    ),
    "greenhouse": SourceCatalogEntry(
        name="greenhouse",
        site_url="https://www.greenhouse.io/",
        access_url=GREENHOUSE_BOARD_API_TEMPLATE.format(board="{board_token}"),
        transport="api",
        attribution=(
            "Greenhouse Job Board API over curated public company boards: "
            + ", ".join(GREENHOUSE_DEFAULT_BOARDS)
        ),
        fetcher=fetch_greenhouse,
    ),
    "lever": SourceCatalogEntry(
        name="lever",
        site_url="https://www.lever.co/",
        access_url=LEVER_POSTINGS_API_TEMPLATE.format(company="{company}"),
        transport="api",
        attribution=(
            "Lever Postings API (public). "
            + (
                "Default companies: " + ", ".join(LEVER_DEFAULT_COMPANIES)
                if LEVER_DEFAULT_COMPANIES
                else "Requires configured company slugs or test fixtures."
            )
        ),
        fetcher=fetch_lever,
    ),
}

AVAILABLE_SOURCES = {
    name: entry.fetcher for name, entry in SOURCE_CATALOG.items()
}
