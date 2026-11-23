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


# (label, column, format, which side is better: "high", "low" or None for not comparable)
STATS = [
    ("Record", None, None, None),
    ("Sig. strikes landed / min", "sig_landed_per_min", "{:.2f}", "high"),
    ("Sig. strikes absorbed / min", "sig_absorbed_per_min", "{:.2f}", "low"),
    ("Striking accuracy", "sig_acc", "{:.0%}", "high"),
    ("Striking defense", "sig_def", "{:.0%}", "high"),
    ("Takedowns / 15 min", "td_per15", "{:.2f}", "high"),
    ("Takedown defense", "td_def", "{:.0%}", "high"),
    ("Control time share", "ctrl_share", "{:.0%}", "high"),
    ("Finish rate", "finish_rate", "{:.0%}", "high"),
    ("Reach", "reach_in", '{:.0f}"', "high"),
    ("Stance", "stance", "{}", None),
]


def _fighter_stats(conn: psycopg.Connection, fighter_id: str) -> dict:
    cols = [c for _, c, _, _ in STATS if c] + ["wins", "losses", "draws"]
    row = conn.execute(
        f"select {', '.join('p.' + c if c in ('reach_in', 'stance') else 'c.' + c for c in cols)} "
        "from marts.fighter_career_stats c join marts.fighter_print_params p using (fighter_id) "
        "where fighter_id = %s",
        (fighter_id,),
    ).fetchone()
    return dict(zip(cols, row, strict=True))


def stat_rows(conn: psycopg.Connection, a_id: str, b_id: str) -> list[dict]:
    a, b = _fighter_stats(conn, a_id), _fighter_stats(conn, b_id)
    rows = []
    for label, col, fmt, better in STATS:
        if col is None:
            rows.append({"label": label, "a": f"{a['wins']}-{a['losses']}-{a['draws']}",
                         "b": f"{b['wins']}-{b['losses']}-{b['draws']}", "edge": "even"})
            continue
        va, vb = a[col], b[col]
        edge = "even"
        if better and va is not None and vb is not None and va != vb:
            edge = "a" if (va > vb) == (better == "high") else "b"
        rows.append({
            "label": label,
            "a": fmt.format(va) if va is not None else "–",
            "b": fmt.format(vb) if vb is not None else "–",
            "edge": edge,
        })
    return rows
