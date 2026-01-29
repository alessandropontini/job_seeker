"""Source registry for job postings."""

from job_scout.sources.dummy import fetch_dummy

AVAILABLE_SOURCES = {
    "dummy": fetch_dummy,
}
