import hashlib
from datetime import UTC, datetime

import httpx
import pytest

from ufc.ingest import fetch
from ufc.ingest.fetch import FetchedFile, FetchError, fetch_file, latest_commit, save_snapshot


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr(fetch, "RETRY_WAIT_SECONDS", (0, 0))


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_computes_sha_and_rows():
    body = b'A,B\n1,"x,y"\n2,z\n'
    f = fetch_file(client_for(lambda req: httpx.Response(200, content=body)), "ufc_fight_details", "abc")
    assert f.row_count == 2
    assert f.sha256 == hashlib.sha256(body).hexdigest()
    assert f.source_commit == "abc"
    assert f.content == body


def test_fetch_requests_the_raw_github_url():
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(200, content=b"A\n1\n")

    fetch_file(client_for(handler), "ufc_fighter_tott", None)
    assert seen == ["https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main/ufc_fighter_tott.csv"]


def test_fetch_retries_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, content=b"A\n1\n")

    f = fetch_file(client_for(handler), "ufc_fight_details", None)
    assert len(calls) == 3
    assert f.row_count == 1


def test_fetch_404_raises():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(FetchError):
        fetch_file(client_for(handler), "ufc_fight_details", None)
    assert len(calls) == 1


def test_fetch_gives_up_after_three_failures():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500)

    with pytest.raises(FetchError):
        fetch_file(client_for(handler), "ufc_fight_details", None)
    assert len(calls) == 3


def test_latest_commit_parses_github_response():
    payload = [{"sha": "abc", "commit": {"committer": {"date": "2026-11-22T18:02:59Z"}}}]
    sha, when = latest_commit(client_for(lambda req: httpx.Response(200, json=payload)))
    assert sha == "abc"
    assert when == datetime(2026, 11, 22, 18, 2, 59, tzinfo=UTC)


def _file(content: bytes) -> FetchedFile:
    return FetchedFile(
        name="test_file", content=content, sha256=hashlib.sha256(content).hexdigest(), row_count=1,
        source_commit="abc", fetched_at=datetime.now(UTC),
    )


def test_save_snapshot_is_idempotent(db):
    first = _file(b"A\n1\n")
    assert save_snapshot(db, first) is True
    assert save_snapshot(db, first) is False
    assert save_snapshot(db, _file(b"A\n2\n")) is True
    count = db.execute("select count(*) from raw.file_snapshots where file_name = 'test_file'").fetchone()[0]
    assert count == 2
