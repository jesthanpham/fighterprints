"""The marts built from the fixture CSVs: career stats, archetypes and the renderer contract."""

ARCHETYPES = {"Striker", "Wrestler", "Grappler", "Brawler", "Balanced"}


def one(conn, sql, *params):
    return conn.execute(sql, params).fetchone()


def test_record_and_finish_rate(built_marts):
    wins, losses, draws, finish = one(
        built_marts, "select wins, losses, draws, finish_rate from marts.fighter_print_params where fighter_id = 'aa01'"
    )
    assert (wins, losses, draws, finish) == (1, 0, 1, 1.0)


def test_timeline_is_chronological(built_marts):
    rows = built_marts.execute(
        "select fight_seq, fight_id, result from marts.fighter_fight_timeline where fighter_id = 'aa01' order by fight_seq"
    ).fetchall()
    assert rows == [(1, "f1", "W"), (2, "f4", "D")]


def test_zero_wins_has_zero_finish_rate(built_marts):
    ko_losses, finish = one(
        built_marts, "select ko_losses, finish_rate from marts.fighter_print_params where fighter_id = 'bb01'"
    )
    assert (ko_losses, finish) == (1, 0.0)


def test_same_name_fighters_keep_their_own_fights(built_marts):
    def fights(fid):
        return [r[0] for r in built_marts.execute(
            "select fight_id from marts.fighter_fight_timeline where fighter_id = %s", (fid,)
        ).fetchall()]

    assert fights("12ebd7d157e91701") == ["f3"]
    assert fights("294aa73dbf37d281") == ["f2"]


def test_missing_reach_and_stance_stay_null(built_marts):
    assert one(
        built_marts, "select reach_in, stance from marts.fighter_print_params where fighter_id = 'cg01'"
    ) == (None, None)


def test_rates_from_round_stats(built_marts):
    # Alan Alpha: f1 (150s) + f4 (900s) = 1050s = 17.5 min; landed 11 + 18 + 15 + 21 = 65
    minutes, pace = one(
        built_marts, "select minutes, sig_landed_per_min from marts.fighter_career_stats where fighter_id = 'aa01'"
    )
    assert float(minutes) == 17.5
    assert round(float(pace), 4) == round(65 / 17.5, 4)


def test_every_fighter_has_an_archetype_and_small_sample(built_marts):
    rows = built_marts.execute("select archetype, small_sample from marts.fighter_print_params").fetchall()
    assert len(rows) == 7
    assert {a for a, _ in rows} <= ARCHETYPES
    assert all(small for _, small in rows)
