"""Read-only queries the compare page needs. Everything comes from the marts schema."""

from collections import Counter
from datetime import date

import psycopg

PARAM_COLUMNS = [
    "fighter_id", "fighter_name", "weight_lbs", "archetype", "sig_landed_per_min", "sig_absorbed_per_min",
    "head_pct", "reach_in", "stance", "finish_rate", "ko_losses", "wins", "losses", "draws", "no_contests",
    "small_sample",
]
TIMELINE_COLUMNS = [
    "fight_seq", "fight_id", "event_name", "event_date", "opponent_name", "result", "method_group",
    "end_round", "end_time_s",
]


def _jsonable(value):
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "is_finite"):  # Decimal
        return float(value)
    return value


def has_data(conn: psycopg.Connection) -> bool:
    """True once the pipeline has built the marts and there are fighters to show."""
    if conn.execute("select to_regclass('marts.fighter_print_params')").fetchone()[0] is None:
        return False
    return conn.execute("select exists (select 1 from marts.fighter_print_params)").fetchone()[0]


def list_fighters(conn: psycopg.Connection) -> list[tuple[str, str]]:
    """(fighter_id, label) for every fighter. Fighters who share a name get their weight in the label."""
    rows = conn.execute(
        "select fighter_id, fighter_name, weight_lbs, wins, losses, draws "
        "from marts.fighter_print_params order by fighter_name, weight_lbs, fighter_id"
    ).fetchall()
    name_counts = Counter(r[1] for r in rows)
    out = []
    for fighter_id, name, weight, wins, losses, draws in rows:
        weight_part = f" ({weight} lbs)" if name_counts[name] > 1 and weight else ""
        out.append((fighter_id, f"{name}{weight_part} ({wins}-{losses}-{draws})"))
    return out


def default_pair(conn: psycopg.Connection) -> tuple[str, str]:
    """The two fighters with the most UFC fights: a good first comparison."""
    rows = conn.execute(
        "select fighter_id from marts.fighter_print_params "
        "order by wins + losses + draws + no_contests desc, fighter_id limit 2"
    ).fetchall()
    return rows[0][0], rows[1][0]


def print_payload(conn: psycopg.Connection, fighter_id: str) -> dict:
    """Exactly what the renderer needs: the fighter's print inputs and their fights in order."""
    row = conn.execute(
        f"select {', '.join(PARAM_COLUMNS)} from marts.fighter_print_params where fighter_id = %s", (fighter_id,)
    ).fetchone()
    if row is None:
        raise KeyError(fighter_id)
    fights = conn.execute(
        f"select {', '.join(TIMELINE_COLUMNS)} from marts.fighter_fight_timeline "
        "where fighter_id = %s order by fight_seq",
        (fighter_id,),
    ).fetchall()
    return {
        "params": {k: _jsonable(v) for k, v in zip(PARAM_COLUMNS, row, strict=True)},
        "fights": [{k: _jsonable(v) for k, v in zip(TIMELINE_COLUMNS, f, strict=True)} for f in fights],
    }


DIMENSIONS = [
    "pace_pct", "absorbed_pct", "accuracy_pct", "defense_pct",
    "takedown_pct", "control_pct", "submission_pct", "finish_pct",
]
MIN_SHARED_DIMENSIONS = 4
ARCHETYPE_PENALTY = 10


def match_score(a: dict, b: dict) -> int | None:
    """Similarity 0-100: 100 minus the average percentile gap, minus 10 if the style labels differ.

    Only dimensions both fighters have count; with fewer than 4 there's no honest score.
    """
    gaps = [abs(a[d] - b[d]) for d in DIMENSIONS if a.get(d) is not None and b.get(d) is not None]
    if len(gaps) < MIN_SHARED_DIMENSIONS:
        return None
    score = 100 * (1 - sum(gaps) / len(gaps))
    if a.get("archetype") != b.get("archetype"):
        score -= ARCHETYPE_PENALTY
    return round(min(100, max(0, score)))


def style_match(conn: psycopg.Connection, a_id: str, b_id: str) -> int | None:
    columns = ["fighter_id", "archetype", *DIMENSIONS]
    rows = conn.execute(
        f"select {', '.join(columns)} from marts.fighter_style_vector where fighter_id = any(%s)",
        ([a_id, b_id],),
    ).fetchall()
    vectors = {r[0]: dict(zip(columns, r, strict=True)) for r in rows}
    if a_id not in vectors or b_id not in vectors:
        return None
    return match_score(vectors[a_id], vectors[b_id])
