"""Fighter identity resolution: which fighter_id is "<name as written>" in this fight?

Stats and bouts identify fighters by name only; the fighter list has IDs. Rules, in order:
  1. exact name, one candidate                         -> exact
     exact name, several: weight matches the division  -> exact_weight
     exact name, several: only one aged 18-45 that day -> exact_age
  2. manual alias seed                                  -> alias
  3. normalized name (accents, hyphens, Jr./III)        -> normalized
  4. fuzzy match >= 92 within the same weight           -> fuzzy
  5. otherwise                                          -> unresolved
"""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from rapidfuzz import fuzz

FUZZY_THRESHOLD = 92
AGE_WINDOW = (18, 45)
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
# Longest names first so "Light Heavyweight" wins over "Heavyweight" and "Lightweight".
DIVISIONS = sorted(
    {
        "strawweight": 115, "flyweight": 125, "bantamweight": 135, "featherweight": 145,
        "lightweight": 155, "welterweight": 170, "middleweight": 185, "light heavyweight": 205,
        "heavyweight": 265,
    }.items(),
    key=lambda kv: -len(kv[0]),
)


@dataclass(frozen=True)
class Appearance:
    fight_id: str
    name: str
    weight_class: str
    event_date: date | None


@dataclass(frozen=True)
class FighterRecord:
    fighter_id: str
    name: str
    weight_lbs: int | None
    dob: date | None


@dataclass(frozen=True)
class Resolution:
    fight_id: str
    name_as_written: str
    fighter_id: str | None
    method: str


def normalize_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    tokens = re.sub(r"[-.']", " ", plain).split()
    while tokens and tokens[-1] in SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def weight_class_lbs(weight_class: str) -> int | None:
    text = weight_class.lower()
    for division, lbs in DIVISIONS:
        if division in text:
            return lbs
    return None


def _age_on(dob: date | None, when: date | None) -> int | None:
    if dob is None or when is None:
        return None
    return when.year - dob.year - ((when.month, when.day) < (dob.month, dob.day))


def _disambiguate(cands: list[FighterRecord], app: Appearance, lbs: int | None) -> tuple[FighterRecord | None, str]:
    """Pick one of several same-name candidates: by weight first, then by age."""
    if lbs is not None:
        by_weight = [c for c in cands if c.weight_lbs == lbs]
        if len(by_weight) == 1:
            return by_weight[0], "weight"
    low, high = AGE_WINDOW
    by_age = [c for c in cands if (a := _age_on(c.dob, app.event_date)) is not None and low <= a <= high]
    if len(by_age) == 1:
        return by_age[0], "age"
    return None, ""


def _resolve_one(
    app: Appearance,
    fighters: list[FighterRecord],
    by_name: dict[str, list[FighterRecord]],
    by_norm: dict[str, list[FighterRecord]],
    aliases: dict[str, str],
    known_ids: set[str],
) -> tuple[str | None, str]:
    name = app.name.strip()
    lbs = weight_class_lbs(app.weight_class)

    exact = by_name.get(name, [])
    if len(exact) == 1:
        return exact[0].fighter_id, "exact"
    if len(exact) > 1:
        pick, how = _disambiguate(exact, app, lbs)
        if pick:
            return pick.fighter_id, f"exact_{how}"
    if name in aliases and aliases[name] in known_ids:
        return aliases[name], "alias"
    norm = by_norm.get(normalize_name(name), [])
    if len(norm) == 1:
        return norm[0].fighter_id, "normalized"
    if len(norm) > 1:
        pick, _ = _disambiguate(norm, app, lbs)
        if pick:
            return pick.fighter_id, "normalized"
    if lbs is not None:
        target = normalize_name(name)
        scored = sorted(
            ((fuzz.token_sort_ratio(target, normalize_name(f.name)), f.fighter_id)
             for f in fighters if f.weight_lbs == lbs),
            reverse=True,
        )
        # a clear single best match only: a tie for first place stays unresolved
        if scored and scored[0][0] >= FUZZY_THRESHOLD and (len(scored) == 1 or scored[1][0] < scored[0][0]):
            return scored[0][1], "fuzzy"
    return None, "unresolved"


def resolve(
    appearances: list[Appearance], fighters: list[FighterRecord], aliases: dict[str, str]
) -> list[Resolution]:
    by_name: dict[str, list[FighterRecord]] = defaultdict(list)
    by_norm: dict[str, list[FighterRecord]] = defaultdict(list)
    for f in fighters:
        by_name[f.name.strip()].append(f)
        by_norm[normalize_name(f.name)].append(f)
    known_ids = {f.fighter_id for f in fighters}
    out = []
    for app in appearances:
        fighter_id, method = _resolve_one(app, fighters, by_name, by_norm, aliases, known_ids)
        out.append(Resolution(app.fight_id, app.name.strip(), fighter_id, method))
    return out
