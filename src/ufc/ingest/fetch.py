"""Download the upstream CSVs and keep every distinct version as an immutable snapshot."""

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import psycopg
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from ufc.config import SOURCE_BASE_URL, SOURCE_REPO

ATTEMPTS = 3
RETRY_WAIT_SECONDS = (1, 4)  # exponential backoff from 1s, capped at 4s
TIMEOUT_SECONDS = 60


class FetchError(Exception):
    """A file could not be downloaded (client error, or retries exhausted)."""


@dataclass(frozen=True)
class FetchedFile:
    name: str
    content: bytes
    sha256: str
    row_count: int
    source_commit: str | None
    fetched_at: datetime


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


def _get(client: httpx.Client, url: str) -> httpx.Response:
    low, high = RETRY_WAIT_SECONDS
    retrying = Retrying(
        stop=stop_after_attempt(ATTEMPTS),
        wait=wait_exponential(multiplier=low, min=low, max=high),
        retry=retry_if_exception(_retryable),
        reraise=True,
    )
    try:
        for attempt in retrying:
            with attempt:
                response = client.get(url, timeout=TIMEOUT_SECONDS)
                response.raise_for_status()
                return response
    except (httpx.HTTPStatusError, httpx.TransportError) as exc:
        raise FetchError(f"GET {url} failed: {exc}") from exc
    raise FetchError(f"GET {url} failed")  # unreachable: tenacity reraises


def count_rows(content: bytes) -> int:
    """Data rows, excluding the header. Uses the csv module: fields can contain quoted newlines."""
    reader = csv.reader(io.StringIO(content.decode("utf-8")))
    return max(sum(1 for _ in reader) - 1, 0)


def latest_commit(client: httpx.Client) -> tuple[str, datetime]:
    url = f"https://api.github.com/repos/{SOURCE_REPO}/commits?per_page=1"
    data = _get(client, url).json()[0]
    when = datetime.fromisoformat(data["commit"]["committer"]["date"])
    return data["sha"], when


def fetch_file(client: httpx.Client, name: str, source_commit: str | None) -> FetchedFile:
    content = _get(client, f"{SOURCE_BASE_URL}{name}.csv").content
    return FetchedFile(
        name=name,
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        row_count=count_rows(content),
        source_commit=source_commit,
        fetched_at=datetime.now(UTC),
    )


def save_snapshot(conn: psycopg.Connection, f: FetchedFile) -> bool:
    """Store the file if this exact content is new (else just mark it seen). True when a snapshot was added."""
    inserted = conn.execute(
        """
        insert into raw.file_snapshots
            (file_name, sha256, source_commit, fetched_at, row_count, content, last_seen_at)
        values (%s, %s, %s, %s, %s, %s, %s)
        on conflict (file_name, sha256) do update set last_seen_at = excluded.last_seen_at
        returning (xmax = 0)
        """,
        (f.name, f.sha256, f.source_commit, f.fetched_at, f.row_count, f.content, f.fetched_at),
    ).fetchone()[0]
    conn.commit()
    return bool(inserted)
