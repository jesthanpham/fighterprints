from datetime import date

from ufc.identity.resolve import Appearance, FighterRecord, normalize_name, resolve, weight_class_lbs

SILVA_125 = FighterRecord("294aa73dbf37d281", "Bruno Silva", 125, date(1990, 3, 16))
SILVA_185 = FighterRecord("12ebd7d157e91701", "Bruno Silva", 185, date(1989, 7, 13))


def one(name, weight_class, fighters, aliases=None, event_date=date(2024, 4, 13)):
    [r] = resolve([Appearance("f1", name, weight_class, event_date)], fighters, aliases or {})
    return r


def test_normalize_name():
    assert normalize_name("Kai Kamaka III") == "kai kamaka"
    assert normalize_name("Waldo Cortes-Acosta") == "waldo cortes acosta"
    assert normalize_name("José Aldo") == "jose aldo"
    assert normalize_name("  Levi Rodrigues Jr. ") == "levi rodrigues"


def test_weight_class_lbs():
    assert weight_class_lbs("UFC Lightweight Title Bout") == 155
    assert weight_class_lbs("Women's Flyweight Bout") == 125
    assert weight_class_lbs("Light Heavyweight Bout") == 205
    assert weight_class_lbs("Heavyweight Bout") == 265
    assert weight_class_lbs("Catch Weight Bout") is None


def test_single_exact_name():
    r = one("Alan Alpha", "Lightweight Bout", [FighterRecord("aa01", "Alan Alpha", 155, None)])
    assert (r.fighter_id, r.method) == ("aa01", "exact")


def test_duplicate_name_resolved_by_weight():
    fighters = [SILVA_125, SILVA_185]
    r = one("Bruno Silva", "Flyweight Bout", fighters)
    assert (r.fighter_id, r.method) == ("294aa73dbf37d281", "exact_weight")
    r = one("Bruno Silva", "Middleweight Bout", fighters)
    assert (r.fighter_id, r.method) == ("12ebd7d157e91701", "exact_weight")


def test_duplicate_name_resolved_by_age():
    old = FighterRecord("old1", "Michael McDonald", 155, date(1965, 2, 6))
    young = FighterRecord("young1", "Michael McDonald", 155, date(1991, 1, 15))
    r = one("Michael McDonald", "Lightweight Bout", [old, young])
    assert (r.fighter_id, r.method) == ("young1", "exact_age")


def test_misspelling_resolved_fuzzy():
    r = one("Rafael Cerquiera", "Flyweight Bout", [FighterRecord("rc01", "Rafael Cerqueira", 125, None)])
    assert (r.fighter_id, r.method) == ("rc01", "fuzzy")


def test_fuzzy_needs_same_weight():
    r = one("Rafael Cerquiera", "Heavyweight Bout", [FighterRecord("rc01", "Rafael Cerqueira", 125, None)])
    assert (r.fighter_id, r.method) == (None, "unresolved")


def test_suffix_resolved_normalized():
    r = one("Kai Kamaka III", "Featherweight Bout", [FighterRecord("kk01", "Kai Kamaka", 145, None)])
    assert (r.fighter_id, r.method) == ("kk01", "normalized")


def test_alias_wins_over_fuzzy():
    fighters = [FighterRecord("pf01", "Patricio Freire", 145, None)]
    r = one("Patricio Pitbull", "Featherweight Bout", fighters, aliases={"Patricio Pitbull": "pf01"})
    assert (r.fighter_id, r.method) == ("pf01", "alias")


def test_unresolvable_is_recorded():
    r = one("Nobody Known", "Lightweight Bout", [FighterRecord("aa01", "Alan Alpha", 155, None)])
    assert (r.fighter_id, r.method) == (None, "unresolved")
    assert r.name_as_written == "Nobody Known"
