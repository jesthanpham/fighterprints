"""Build src.fighter_identity from the loaded src tables."""

import csv
from collections import Counter
from datetime import date, datetime
from importlib.resources import files

import psycopg

from ufc.identity.resolve import Appearance, FighterRecord, resolve

MISSING = {"", "--", "---"}


def _id_from_url(url: str) -> str:
    return url.strip().rstrip("/").rsplit("/", 1)[-1]


def _date(text: str | None, fmt: str) -> date | None:
    text = (text or "").strip()
    if text in MISSING:
        return None
    try:
        return datetime.strptime(text, fmt).date()
    except ValueError:
        return None


def _lbs(text: str | None) -> int | None:
    digits = "".join(ch for ch in (text or "") if ch.isdigit())
    return int(digits) if digits else None


def load_aliases() -> dict[str, str]:
    text = files("ufc.identity").joinpath("aliases.csv").read_text()
    return {row["name_as_written"].strip(): row["fighter_id"].strip() for row in csv.DictReader(text.splitlines())}


def build_identity(conn: psycopg.Connection) -> dict[str, int]:
    event_dates = {
        name.strip(): _date(when, "%B %d, %Y")
        for name, when in conn.execute("select event, date from src.ufc_event_details").fetchall()
    }
    appearances, seen = [], set()
    for event, bout, weight_class, url in conn.execute(
        "select event, bout, weightclass, url from src.ufc_fight_results order by _row_num"
    ).fetchall():
        fight_id = _id_from_url(url)
        if fight_id in seen:
            continue
        seen.add(fight_id)
        for name in bout.split(" vs. "):
            appearances.append(Appearance(fight_id, name.strip(), weight_class.strip(), event_dates.get(event.strip())))

    fighters = [
        FighterRecord(_id_from_url(url), name.strip(), _lbs(weight), _date(dob, "%b %d, %Y"))
        for name, weight, dob, url in conn.execute("select fighter, weight, dob, url from src.ufc_fighter_tott").fetchall()
    ]
    results = resolve(appearances, fighters, load_aliases())

    try:
        conn.execute("delete from src.fighter_identity")
        with conn.cursor().copy(
            "copy src.fighter_identity (fight_id, name_as_written, fighter_id, method) from stdin"
        ) as copy:
            for r in {(r.fight_id, r.name_as_written): r for r in results}.values():
                copy.write_row([r.fight_id, r.name_as_written, r.fighter_id, r.method])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return dict(Counter(r.method for r in results))
