"""Data models for Job Scout."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional


@dataclass
class JobPosting:
    """Normalized representation of a job posting."""

    id: str
    source: str
    company: str
    title: str
    location_text: str
    location_country: str
    remote_type: str
    url: str
    posted_at: datetime
    salary_text: Optional[str]
    currency: Optional[str]
    tags: List[str] = field(default_factory=list)
    description_snippet: str = ""

    def to_dict(self) -> dict:
        """Serialize the job posting to a JSON-friendly dictionary."""

        return {
            "id": self.id,
            "source": self.source,
            "company": self.company,
            "title": self.title,
            "location_text": self.location_text,
            "location_country": self.location_country,
            "remote_type": self.remote_type,
            "url": self.url,
            "posted_at": self.posted_at.isoformat(),
            "salary_text": self.salary_text,
            "currency": self.currency,
            "tags": list(self.tags),
            "description_snippet": self.description_snippet,
        }

    def with_tags(self, extra_tags: Iterable[str]) -> "JobPosting":
        """Return a copy of this job posting with extra tags appended."""

        merged = list(self.tags)
        for tag in extra_tags:
            if tag not in merged:
                merged.append(tag)
        return JobPosting(
            id=self.id,
            source=self.source,
            company=self.company,
            title=self.title,
            location_text=self.location_text,
            location_country=self.location_country,
            remote_type=self.remote_type,
            url=self.url,
            posted_at=self.posted_at,
            salary_text=self.salary_text,
            currency=self.currency,
            tags=merged,
            description_snippet=self.description_snippet,
        )
