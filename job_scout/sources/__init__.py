"""Source registry for job postings."""

from job_scout.sources.dummy import fetch_dummy
from job_scout.sources.remotive import fetch_remotive
from job_scout.sources.wwr import fetch_wwr

AVAILABLE_SOURCES = {
    "dummy": fetch_dummy,
    "remotive": fetch_remotive,
    "wwr": fetch_wwr,
}
