# UFC Style Fingerprints: Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working, public-ready repo by the resume deadline (~2026-11-30). One command starts Postgres, Dagster and a Streamlit page; the pipeline loads the community UFC CSVs, resolves fighter identities, builds tested dbt marts, and the page draws two real fighters' generated fingerprints side by side.

**Architecture:** Python downloads 6 CSVs into immutable snapshots in Postgres (`raw`), loads changed files into all-text tables (`src`) behind a header contract and shrink guard, and resolves "name in a fight" → `fighter_id`. dbt cleans (`staging`), joins (`intermediate`) and publishes marts. The marts `fighter_print_params` + `fighter_fight_timeline` are the contract with the app, which draws prints in the browser with the spike's JS. Dagster orchestrates it all on a weekly schedule.

**Tech Stack:** Python 3.12 (uv), Postgres 16, psycopg 3, httpx, tenacity, rapidfuzz, dbt-core + dbt-postgres (≥ 1.8, for unit tests), Dagster + dagster-dbt + dagster-webserver, Streamlit, Node ≥ 20 (only for `node --test` on the renderer), Docker Compose (OrbStack or Docker Desktop).

**Spec:** `docs/superpowers/specs/2026-11-23-style-fingerprints-design.md` (Phase 1 of section 10). Reference renderer: `spike/fingerprint-spike.html`.

## Prerequisites (the candidate does these, not the agent)

- Install OrbStack (https://orbstack.dev) or Docker Desktop; confirm `docker compose version` works.
- Phase 2 gets its own plan after this one ships.

## Global Constraints

- Source base URL: `https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main/`; repo `Greco1899/scrape_ufc_stats`. Never request ufcstats.com.
- Files (exact): `ufc_event_details`, `ufc_fight_details`, `ufc_fight_results`, `ufc_fight_stats`, `ufc_fighter_details`, `ufc_fighter_tott` (each `.csv`).
- Expected headers (exact, in order):
  - event_details: `EVENT,URL,DATE,LOCATION`
  - fight_details: `EVENT,BOUT,URL`
  - fight_results: `EVENT,BOUT,OUTCOME,WEIGHTCLASS,METHOD,ROUND,TIME,TIME FORMAT,REFEREE,DETAILS,URL`
  - fight_stats: `EVENT,BOUT,ROUND,FIGHTER,KD,SIG.STR.,SIG.STR. %,TOTAL STR.,TD,TD %,SUB.ATT,REV.,CTRL,HEAD,BODY,LEG,DISTANCE,CLINCH,GROUND`
  - fighter_details: `FIRST,LAST,NICKNAME,URL`
  - fighter_tott: `FIGHTER,HEIGHT,WEIGHT,REACH,STANCE,DOB,URL`
- IDs are the last path segment of UFCStats URLs (e.g. `http://ufcstats.com/fighter-details/93fe7332d16c6ad9` → `93fe7332d16c6ad9`).
- `---`, `--` and empty (after trim) all mean NULL. Trim every text field.
- Shrink guard: refuse a load whose row count is < 90% of the previous load of that file.
- Identity fuzzy threshold: rapidfuzz `token_sort_ratio` ≥ 92, same weight class only. Age window for duplicate names: 18–45 on the event date.
- Freshness: warn if the upstream repo's latest commit is > 7 days old.
- Schedule: cron `0 10 * * 0`, timezone `America/Toronto`.
- Postgres in Docker on host port **5433**; app DB `ufc`, test DB `ufc_test`, user/password `ufc`/`ufc`. Python env vars: `UFC_DATABASE_URL`, `UFC_TEST_DATABASE_URL`. dbt env vars (`profiles.yml`): `UFC_DB_HOST` (default `localhost`), `UFC_DB_PORT` (`5433`), `UFC_DB_USER` (`ufc`), `UFC_DB_PASSWORD` (`ufc`); target `dev` uses dbname `ufc`, target `test` uses `ufc_test`. Inside Compose, host is `postgres` and port `5432`.
- No downloaded data committed to git. README credits Greco1899/scrape_ufc_stats (GPL-3.0) and UFCStats.
- Print defaults when data is missing: reach 72", stance Orthodox, pace 3.5/min, absorbed 3.0/min. Each default sets a flag; a print must never fail or show NaN.

## Review Focus

1. **Fighter with missing reach and/or stance** (2,140 / 1,023 real cases): the print draws with defaults and the flags are listed. Test in Task 7.
2. **Fighter with zero wins, or only early fights with no stats:** `finish_rate` = 0 and per-minute stats NULL, never a division error or NaN; the print uses defaults. Tests in Tasks 6 and 7.
3. **Upstream publishes a truncated or broken file:** the load is refused, the previous `src` table is untouched, and the Dagster run fails visibly. Test in Task 3.
4. **The same fight listed under two event names** ("Noche UFC" vs "UFC Fight Night"): counted once everywhere. Test in Task 4.
5. **Re-running with no upstream change:** no new snapshot, no reload, identical marts. Tests in Tasks 2 and 3.

---

### Task 1: Project skeleton + Postgres

**Files:**
- Create: `pyproject.toml`, `.python-version` (`3.12`), `.gitignore`, `docker-compose.yml` (only the `postgres` service for now), `docker/postgres-init.sql`, `src/ufc/__init__.py`, `src/ufc/config.py`, `src/ufc/db.py`, `src/ufc/sql/bootstrap.sql`, `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `ufc.config`: `SOURCE_BASE_URL: str`, `SOURCE_REPO: str`, `FILES: tuple[str, ...]` (the 6 names without `.csv`), `EXPECTED_COLUMNS: dict[str, list[str]]` (Global Constraints), `database_url() -> str` (env `UFC_DATABASE_URL`, default `postgresql://ufc:ufc@localhost:5433/ufc`).
  - `ufc.db`: `connect(url: str | None = None) -> psycopg.Connection` (autocommit off), `ensure_schemas(conn) -> None` (runs `bootstrap.sql`; idempotent).
  - `bootstrap.sql` creates schemas `raw`, `src` and tables:
    - `raw.file_snapshots(file_name text, sha256 text, source_commit text null, fetched_at timestamptz, row_count int, content bytea, primary key (file_name, sha256))`
    - `src.load_log(id bigserial pk, file_name text, sha256 text, loaded_at timestamptz, row_count int, previous_row_count int null)`
    - `src.fighter_identity(fight_id text, name_as_written text, fighter_id text null, method text, primary key (fight_id, name_as_written))`
  - `tests/conftest.py` fixture `db` (session-scoped): connects to `UFC_TEST_DATABASE_URL` (default `postgresql://ufc:ufc@localhost:5433/ufc_test`), drops schemas `raw`, `src`, `staging`, `intermediate`, `marts` cascade, then `ensure_schemas`. Yields the connection.
- `docker/postgres-init.sql` creates database `ufc_test` (the image creates `ufc`).
- `.gitignore`: `.venv/`, `__pycache__/`, `data/`, `dbt/target/`, `dbt/logs/`, `.env`, `.dagster_home/`.

- [ ] **Step 1:** `git init`; `uv init --package --name ufc` adjusted to `src/ufc`; add deps: `psycopg[binary]`, `httpx`, `tenacity`, `rapidfuzz`, `dbt-core`, `dbt-postgres`, `dagster`, `dagster-dbt`, `dagster-webserver`, `streamlit`; dev deps `pytest`, `ruff`. Commit `uv.lock`.
- [ ] **Step 2: Write the failing test** `tests/test_db.py::test_bootstrap_is_idempotent`: call `ensure_schemas(db)` twice; assert the three tables exist (query `information_schema.tables`) and no error.
- [ ] **Step 3:** `docker compose up -d postgres` (image `postgres:16`, port `5433:5432`, env `POSTGRES_USER/PASSWORD/DB=ufc`, init script mounted, named volume). Run `uv run pytest tests/test_db.py -v`. Expected: FAIL (module missing).
- [ ] **Step 4:** Implement `config.py`, `db.py`, `bootstrap.sql`, `conftest.py`.
- [ ] **Step 5:** `uv run pytest tests/test_db.py -v`. Expected: PASS.
- [ ] **Step 6:** Commit: `feat: project skeleton with postgres and bootstrap schema`.

---

### Task 2: Downloader + immutable snapshots

**Files:**
- Create: `src/ufc/ingest/__init__.py`, `src/ufc/ingest/fetch.py`
- Test: `tests/ingest/test_fetch.py`

**Interfaces:**
- Consumes: `ufc.config.SOURCE_BASE_URL`, `SOURCE_REPO`; `ufc.db`.
- Produces:
  - `class FetchError(Exception)`
  - `@dataclass(frozen=True) FetchedFile(name: str, content: bytes, sha256: str, row_count: int, source_commit: str | None, fetched_at: datetime)`; `row_count` = data lines excluding the header (count with the `csv` module, not newlines, since fields contain quoted newlines/commas).
  - `latest_commit(client: httpx.Client) -> tuple[str, datetime]`: GET `https://api.github.com/repos/{SOURCE_REPO}/commits?per_page=1` → (sha, committer date).
  - `fetch_file(client: httpx.Client, name: str, source_commit: str | None) -> FetchedFile`: GET `{SOURCE_BASE_URL}{name}.csv`, timeout 60s; tenacity: 3 attempts, exponential wait 1s→4s, retry on `httpx.TransportError` and 5xx; 4xx or exhausted retries → `FetchError`.
  - `save_snapshot(conn, f: FetchedFile) -> bool`: insert into `raw.file_snapshots`; `ON CONFLICT (file_name, sha256) DO NOTHING`; return True if inserted.
- Tests use `httpx.Client(transport=httpx.MockTransport(handler))`; patch tenacity's wait to zero in tests.

- [ ] **Step 1: Write failing tests:**
  - `test_fetch_computes_sha_and_rows`: body `b'A,B\n1,"x,y"\n2,z\n'` → `row_count == 2`, `sha256 == hashlib.sha256(body).hexdigest()`.
  - `test_fetch_retries_then_succeeds`: handler returns 503, 503, then 200 → succeeds, handler called 3 times.
  - `test_fetch_404_raises`: 404 → `FetchError`, handler called once.
  - `test_save_snapshot_is_idempotent` (uses `db`): saving the same `FetchedFile` twice → first `True`, second `False`, one row in table; a different content → second row.
  - `test_latest_commit_parses_github_response`: mock JSON `[{"sha":"abc","commit":{"committer":{"date":"2026-11-22T18:02:59Z"}}}]` → `("abc", datetime(2026,11,22,18,2,59,tzinfo=UTC))`.
- [ ] **Step 2:** `uv run pytest tests/ingest/test_fetch.py -v`. Expected: FAIL (import error).
- [ ] **Step 3:** Implement `fetch.py`.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: csv downloader with retries and immutable snapshots`.

---

### Task 3: Header contract, shrink guard, load into `src` + fixture CSVs

**Files:**
- Create: `src/ufc/ingest/load.py`, `tests/fixtures/csv/` (6 files, below)
- Test: `tests/ingest/test_load.py`

**Interfaces:**
- Consumes: `raw.file_snapshots`, `EXPECTED_COLUMNS`.
- Produces:
  - `class SchemaDriftError(Exception)` (message lists missing and unexpected columns), `class ShrinkGuardError(Exception)`.
  - `column_name(header: str) -> str`: lowercase; `%` → `pct`; runs of non-alphanumerics → `_`; strip `_`. Examples: `SIG.STR.`→`sig_str`, `SIG.STR. %`→`sig_str_pct`, `TOTAL STR.`→`total_str`, `SUB.ATT`→`sub_att`, `REV.`→`rev`, `TIME FORMAT`→`time_format`, `TD %`→`td_pct`.
  - `validate_header(name: str, header: list[str]) -> None`.
  - `@dataclass LoadResult(file_name: str, sha256: str, row_count: int, previous_row_count: int | None, skipped: bool)`
  - `load_latest(conn, name: str) -> LoadResult`: take the newest snapshot of `name` (by `fetched_at`); if its sha equals the last `src.load_log` sha for that file → `skipped=True`, no writes. Else validate header, apply the shrink guard against the last logged `row_count`, then in **one transaction**: drop/create `src.<name>` with all columns `text` (via `column_name`) plus `_row_num int` and `_snapshot_sha text`, `COPY` the rows in, insert `src.load_log`. Any error → rollback, previous table intact.
- **Fixture CSVs** (`tests/fixtures/csv/`, exact headers; fake fighters except the two Bruno Silva IDs, which are real). They must contain:
  - Events: `UFC 300: Alpha vs. Beta` (URL id `e300`, `April 13, 2024`) and `UFC Fight Night: Gamma vs. Delta` (id `efn1`, `January 10, 2025`).
  - Fighters (tott + details agree): Alan Alpha (`aa01`, 155 lbs., Orthodox, `72"`, DOB `Jan 01, 1995`); Ben Beta (`bb01`, 155, Southpaw, `74"`); Bruno Silva (`294aa73dbf37d281`, 125 lbs., DOB `Mar 16, 1990`); Bruno Silva (`12ebd7d157e91701`, 185 lbs., DOB `Jul 13, 1989`); Carl Gamma (`cg01`, 185, stance empty, reach `--`); Dan Delta (`dd01`, 155, Switch, `76"`); Rafael Cerqueira (`rc01`, 125).
  - Fights (results + details): `f1` E300 `Alan Alpha vs. Ben Beta`, `W/L`, `Lightweight Bout`, `KO/TKO ` (trailing space), round 1, `2:30`, `3 Rnd (5-5-5)`. `f2` E300 `Bruno Silva vs. Rafael Cerquiera` (misspelled), `L/W`, `Flyweight Bout`, `Submission `, round 2, `1:10`. `f3` EFN1 `Bruno Silva vs. Carl Gamma`, `W/L`, `Middleweight Bout`, `Decision - Unanimous `, round 3, `5:00`. `f4` EFN1 `Dan Delta vs. Alan Alpha`, `D/D`, `Lightweight Bout`, `Decision - Split `, round 3, `5:00`. In `fight_details`, `f4` appears twice: once under `UFC Fight Night: Gamma vs. Delta` and once under `Noche UFC: Gamma vs. Delta`.
  - Stats: one row per fighter per round fought. `f1` round 1 Alan Alpha: `KD 1, SIG.STR. 11 of 25, SIG.STR. % 44%, TOTAL STR. 11 of 25, TD 0 of 0, TD % ---, SUB.ATT 0, REV. 0, CTRL 0:18, HEAD 4 of 16, BODY 0 of 0, LEG 7 of 9, DISTANCE 11 of 25, CLINCH 0 of 0, GROUND 0 of 0`. Plus one fully blank row (all 19 fields empty). Other rows: any values where landed ≤ attempted, HEAD+BODY+LEG landed = SIG.STR. landed, DISTANCE+CLINCH+GROUND landed = SIG.STR. landed, and CTRL ≤ 5:00. `f4` stats use the event name `Noche UFC: Gamma vs. Delta`.

- [ ] **Step 1: Write failing tests:**
  - `test_column_name_examples`: the 7 examples above.
  - `test_header_drift_lists_columns`: `validate_header("ufc_fighter_tott", ["FIGHTER","HEIGHT","WEIGHT","REACH_IN","STANCE","DOB","URL"])` raises `SchemaDriftError` whose message contains `REACH` and `REACH_IN`.
  - `test_load_creates_text_table` (db): snapshot the fixture `ufc_fight_stats.csv`, `load_latest` → `src.ufc_fight_stats` has a `sig_str_pct` column and `row_count` equal to the fixture's data rows; trailing spaces preserved (cleaning is dbt's job).
  - `test_unchanged_snapshot_is_skipped` (db): second `load_latest` with no new snapshot → `skipped is True`, `src.load_log` count unchanged.
  - `test_shrink_guard_keeps_previous_table` (db): load full fixture; then snapshot a version with < 90% of rows → `ShrinkGuardError`; `src.<name>` still has the original row count.
- [ ] **Step 2:** Run `uv run pytest tests/ingest/test_load.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `load.py` and write the fixture CSVs.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: header contract, shrink guard and src loading`.

---

### Task 4: Fighter identity resolution

**Files:**
- Create: `src/ufc/identity/__init__.py`, `src/ufc/identity/resolve.py`, `src/ufc/identity/job.py`, `src/ufc/identity/aliases.csv` (header `name_as_written,fighter_id`; fill from a real run in Task 9)
- Test: `tests/identity/test_resolve.py`, `tests/identity/test_job.py`

**Interfaces:**
- Consumes: `src.ufc_fight_results`, `src.ufc_event_details`, `src.ufc_fighter_tott`.
- Produces:
  - `@dataclass(frozen=True) Appearance(fight_id: str, name: str, weight_class: str, event_date: date | None)`
  - `@dataclass(frozen=True) FighterRecord(fighter_id: str, name: str, weight_lbs: int | None, dob: date | None)`
  - `@dataclass(frozen=True) Resolution(fight_id: str, name_as_written: str, fighter_id: str | None, method: str)`; `method` ∈ `exact, exact_weight, exact_age, alias, normalized, fuzzy, unresolved`.
  - `normalize_name(name: str) -> str`: NFKD + drop combining marks, lowercase, `-`/`.`/`'` → space, drop trailing tokens `jr`, `sr`, `ii`, `iii`, `iv`, collapse spaces.
  - `weight_class_lbs(weight_class: str) -> int | None`: match the longest of these names contained in the string (case-insensitive): Strawweight 115, Flyweight 125, Bantamweight 135, Featherweight 145, Lightweight 155, Welterweight 170, Middleweight 185, Light Heavyweight 205, Heavyweight 265. Women's divisions map by the same names. Catch Weight / Open Weight / unknown → None.
  - `resolve(appearances: list[Appearance], fighters: list[FighterRecord], aliases: dict[str, str]) -> list[Resolution]`: the order from spec §6.2b. Step 2 weight match: candidate `weight_lbs == weight_class_lbs(...)`. Age step: exactly one candidate aged 18–45 on `event_date`. Fuzzy only among fighters whose `weight_lbs` equals the bout's lbs.
  - `build_identity(conn) -> dict[str, int]`: appearances = both names from each distinct fight URL in `src.ufc_fight_results` (split `BOUT` on ` vs. `, trim), weight class from that row, event date from `src.ufc_event_details` joined on trimmed event name (parse `%B %d, %Y`). Fighters from tott (`weight` `"155 lbs."` → 155; DOB `%b %d, %Y`; `--` → None). Replace `src.fighter_identity` contents in one transaction. Return counts per method.

- [ ] **Step 1: Write failing tests** (`test_resolve.py`, pure, no DB):
  - `test_normalize_name`: `"Kai Kamaka III"` → `"kai kamaka"`; `"Waldo Cortes-Acosta"` → `"waldo cortes acosta"`; `"José Aldo"` → `"jose aldo"`.
  - `test_weight_class_lbs`: `"UFC Lightweight Title Bout"` → 155; `"Women's Flyweight Bout"` → 125; `"Light Heavyweight Bout"` → 205 (not 265); `"Catch Weight Bout"` → None.
  - `test_duplicate_name_resolved_by_weight`: two Bruno Silvas (125 / 185); a Flyweight appearance → `294aa73dbf37d281` / `exact_weight`; a Middleweight one → `12ebd7d157e91701` / `exact_weight`.
  - `test_duplicate_name_resolved_by_age`: same names, same weight, one born 1965 and one 1991, event 2024 → the 1991 one, `exact_age`.
  - `test_misspelling_resolved_fuzzy`: `"Rafael Cerquiera"` vs record `"Rafael Cerqueira"` (same weight) → `fuzzy`.
  - `test_alias_wins_over_fuzzy`: alias `{"Patricio Pitbull": "pf01"}` → `alias`.
  - `test_unresolvable_is_recorded`: `"Nobody Known"` → `fighter_id None`, `unresolved`.
- [ ] **Step 2:** `test_job.py::test_build_identity_on_fixtures` (db): load all fixture CSVs (Tasks 2–3 functions; a helper `tests/helpers.py::load_fixture_csvs(conn)` that snapshots and loads every fixture file), run `build_identity` → no `unresolved`; `(f2, "Bruno Silva")` → `294aa73dbf37d281`; `(f3, "Bruno Silva")` → `12ebd7d157e91701`; `(f2, "Rafael Cerquiera")` → `rc01`; `f4` appears exactly twice (once per fighter) despite the duplicate in fight_details.
- [ ] **Step 3:** Run `uv run pytest tests/identity -v`. Expected: FAIL.
- [ ] **Step 4:** Implement `resolve.py`, `job.py`, empty `aliases.csv`, `tests/helpers.py`.
- [ ] **Step 5:** Run tests. Expected: PASS.
- [ ] **Step 6:** Commit: `feat: fighter identity resolution`.

---

### Task 5: dbt project + staging models

**Files:**
- Create: `dbt/dbt_project.yml` (name `ufc`; `staging`, `intermediate`, `marts` folders materialized as `view`, `view`, `table` in schemas of the same names), `dbt/profiles.yml` (profile `ufc`, targets `dev` and `test`, env vars per Global Constraints), `dbt/macros/clean.sql`, `dbt/macros/generate_schema_name.sql` (use the custom schema name as-is), `dbt/models/sources.yml`, `dbt/models/staging/{stg_events,stg_fights,stg_fight_round_stats,stg_fighters,stg_fighter_identity}.sql`, `dbt/models/staging/staging.yml` (tests + unit tests)
- Test: `tests/test_dbt_build.py` (started here, extended in Task 6)

**Interfaces:**
- Consumes: `src.*` tables (Task 3 column names), `src.fighter_identity`.
- Produces macros in `clean.sql`: `clean(col)` (trim; `---`/`--`/'' → NULL), `of_landed(col)`, `of_attempted(col)` (`"11 of 25"` → 11 / 25), `mmss_to_seconds(col)` (`"2:30"` → 150), `elapsed_seconds(end_round, end_time_s, time_format)`: sum of the first `end_round - 1` round lengths from the parenthesized list in `time_format` (minutes × 60) + `end_time_s`; when there's no list (e.g. `No Time Limit`), assume 300-second rounds.
- Models (columns other tasks rely on):
  - `stg_events`: `event_id, event_name, event_date, location`.
  - `stg_fights`: one row per `fight_id` (dedupe by URL id): `fight_id, event_id, event_name, event_date, fighter_a_name, fighter_b_name, outcome_a, outcome_b` (from `W/L` etc.), `weight_class, method_raw, method_group` (`KO_TKO` for `KO/TKO` and `TKO - Doctor's Stoppage`; `SUB` for `Submission`; `DEC` for `Decision - *`; else `OTHER`), `end_round, end_time_s, time_format, elapsed_s`.
  - `stg_fight_round_stats`: `fight_id, round_num, fighter_name, fighter_id, kd, sig_landed, sig_att, total_landed, total_att, td_landed, td_att, sub_att, rev, ctrl_s, head_landed, head_att, body_landed, body_att, leg_landed, leg_att, distance_landed, clinch_landed, ground_landed`. Map (event, bout) → `fight_id` through **all** `src.ufc_fight_details` rows (so either event name works), then dedupe on `(fight_id, round_num, fighter_id)`. Drop rows with blank `ROUND` or `FIGHTER`.
  - `stg_fighters`: `fighter_id, fighter_name, nickname, height_in, weight_lbs, reach_in, stance` (`Orthodox`/`Southpaw`/`Switch`; `Open Stance`/`Sideways` → `Other`; blank → NULL), `dob`.
  - `stg_fighter_identity`: passthrough with `fight_id, name_as_written, fighter_id, method`.

- [ ] **Step 1: Write the dbt unit tests** in `staging.yml` (`unit_tests:` block):
  - `stg_fights`: `KO/TKO ` → `KO_TKO`; `TKO - Doctor's Stoppage` → `KO_TKO`; `Decision - Split ` → `DEC`; `Overturned` → `OTHER`. Elapsed: round 3, `5:00`, `3 Rnd (5-5-5)` → 900; round 1, `2:30` → 150; round 2, `1:00`, `1 Rnd + OT (12-3)` → 780; round 1, `12:00`, `No Time Limit` → 720.
  - `stg_fight_round_stats`: `"11 of 25"` → 11/25; `CTRL "0:18"` → 18; a blank row is dropped; the same fight under two event names yields one row.
  - `stg_fighters`: `"--"` reach → NULL; `"72\""` → 72; `"5' 11\""` → 71; empty stance → NULL; `"Sideways"` → `Other`.
- [ ] **Step 2:** Add generic tests in `staging.yml`: unique + not_null on `stg_events.event_id`, `stg_fights.fight_id`, `stg_fighters.fighter_id`; accepted_values on `method_group` and `stance`.
- [ ] **Step 3: Write the failing pytest** `tests/test_dbt_build.py::test_staging_on_fixtures`: `load_fixture_csvs(db)` + `build_identity(db)`, then `dbtRunner().invoke(["build", "--select", "staging", "--target", "test", "--project-dir", "dbt", "--profiles-dir", "dbt"])` succeeds; `staging.stg_fights` has 4 rows; `f1` has `method_group = 'KO_TKO'`, `elapsed_s = 150`.
- [ ] **Step 4:** Run `uv run pytest tests/test_dbt_build.py -v`. Expected: FAIL.
- [ ] **Step 5:** Implement the dbt project, macros and staging models.
- [ ] **Step 6:** Run the pytest. Expected: PASS (it also runs the dbt unit and generic tests).
- [ ] **Step 7:** Commit: `feat: dbt staging models with unit tests`.

---

### Task 6: Intermediate + marts (career stats, archetypes, print contract)

**Files:**
- Create: `dbt/models/intermediate/int_fighter_fight.sql`, `dbt/models/marts/{fighter_career_stats,fighter_fingerprint,fighter_print_params,fighter_fight_timeline}.sql`, `dbt/models/marts/marts.yml`, `dbt/tests/{assert_landed_le_attempted,assert_two_fighters_per_fight,assert_identity_unresolved_any,assert_identity_unresolved_rate,assert_timeline_count_matches_record,assert_strike_mix_sums,assert_round_and_ctrl_in_range,assert_recent_event}.sql`
- Modify: `tests/conftest.py`: add session fixture `built_marts(db)` = `load_fixture_csvs` + `build_identity` + full `dbt build --target test`; Task 6 and Task 8 tests use it instead of relying on test order.
- Test: extend `tests/test_dbt_build.py`

**Interfaces:**
- Consumes: Task 5 staging columns.
- Produces:
  - `int_fighter_fight`: one row per (fighter_id, fight_id) for resolved fighters: `fighter_id, opponent_id, opponent_name, fight_id, event_name, event_date, fight_seq` (1 = debut; order by `event_date`, then `fight_id`), `result` (`W/L/D/NC`), `method_group, end_round, end_time_s, elapsed_s, has_stats`, own sums (`sig_landed, sig_att, td_landed, td_att, sub_att, kd, ctrl_s, head_landed, body_landed, leg_landed`) and opponent sums (`opp_sig_landed, opp_sig_att, opp_td_landed, opp_td_att`).
  - `fighter_career_stats` (per fighter; minutes = Σ`elapsed_s`/60 over `has_stats` fights): `fights, wins, losses, draws, no_contests, fights_with_stats, minutes, sig_landed_per_min, sig_absorbed_per_min, sig_acc, sig_def, td_per15, td_acc, td_def, ctrl_share, sub_att_per15, kd_per15, head_pct, body_pct, leg_pct, ko_wins, sub_wins, ko_losses, finish_rate` (= (ko_wins+sub_wins)/wins, 0 when wins = 0). Rates are NULL when minutes = 0.
  - `fighter_fingerprint`: career stats + `small_sample` (fights_with_stats < 3 or minutes < 15) + `archetype`. Thresholds are percentiles over non-small-sample fighters; the first matching rule wins:
    1. `Grappler`: `sub_att_per15 ≥ p80` OR (wins ≥ 3 AND sub_wins/wins ≥ 0.5)
    2. `Wrestler`: `td_per15 ≥ p75` AND `ctrl_share ≥ p60`
    3. `Brawler`: `sig_landed_per_min ≥ p60` AND `sig_absorbed_per_min ≥ p75`
    4. `Striker`: `sig_landed_per_min ≥ p60` OR (wins ≥ 3 AND ko_wins/wins ≥ 0.5)
    5. `Balanced`
  - `fighter_print_params` (**the renderer contract**): `fighter_id, fighter_name, archetype, sig_landed_per_min, sig_absorbed_per_min, head_pct, reach_in, stance, finish_rate, ko_losses, wins, losses, draws, no_contests, small_sample, input_hash` (md5 of the other columns as text).
  - `fighter_fight_timeline`: `fighter_id, fight_seq, fight_id, event_name, event_date, opponent_name, result, method_group, end_round, end_time_s`.
- Singular tests: landed ≤ attempted (sig, total, td, head, body, leg); exactly 2 resolved fighters per fight in `int_fighter_fight` (excluding fights with an unresolved fighter); unresolved any → `severity: warn`; unresolved > 1% of appearances → error; timeline rows per fighter = wins + losses + draws + no_contests; head+body+leg landed = sig landed and distance+clinch+ground landed = sig landed per round row (`warn`, since real upstream data may have tiny inconsistencies); `round_num` between 1 and 5 and `ctrl_s` ≤ 300 (`warn`); latest `event_date` within 30 days of today (`warn`).
- `marts.yml` generic tests on `fighter_print_params`: `fighter_id` unique + not_null; not_null on `archetype`, `finish_rate`, `ko_losses`, `wins`, `losses`, `input_hash`; accepted_values on `archetype` (5 labels) and `stance` (`Orthodox`, `Southpaw`, `Switch`, `Other`; NULL allowed, since the renderer applies defaults).

- [ ] **Step 1: Write failing assertions** in `tests/test_dbt_build.py::test_marts_on_fixtures` (after `dbt build` of everything):
  - Alan Alpha (`aa01`): `wins 1, losses 0, draws 1`, timeline has 2 rows with `fight_seq` 1 → `f1`, 2 → `f4`; `finish_rate = 1.0`.
  - Ben Beta (`bb01`): `ko_losses = 1`, `finish_rate = 0` (zero wins, no error).
  - Bruno Silva 185 (`12ebd7d157e91701`) has `f3` only; Bruno Silva 125 has `f2` only.
  - Carl Gamma (`cg01`): `fighter_print_params.reach_in IS NULL` and `stance IS NULL` (defaults are the renderer's job).
  - Every fixture fighter's `archetype` is one of the 5 labels; every fixture fighter has `small_sample = true`.
- [ ] **Step 2:** Run `uv run pytest tests/test_dbt_build.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement the models and singular tests.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: fighter marts, archetypes and print contract`.

---

### Task 7: Renderer module (from the spike)

**Files:**
- Create: `app/components/fingerprint/fingerprint.js` (ES module), `app/components/fingerprint/fingerprint.test.mjs`, `app/components/fingerprint/demo.html` (loads the module with two hard-coded payloads, for eyeballing)
- Reference: `spike/fingerprint-spike.html` (`grow`, `drawPrint`, noise/RNG helpers). Keep the algorithm and constants **unchanged**; only the inputs change.

**Interfaces:**
- Consumes: payload shape `{ params: <fighter_print_params row as JSON>, fights: <fighter_fight_timeline rows, ordered by fight_seq> }`.
- Produces:
  - `export function printPlan(params, fights)` → `{ pattern, spacing, pressure, wear, size, mirror, tilt, coreShift, creaseCount, markCount, seed, flags }`:
    - `pattern` from archetype: Striker→`whorl`, Wrestler→`loop`, Grappler→`double_loop`, Brawler→`tented_arch`, Balanced→`plain_arch`.
    - `spacing = lerp(7.4, 5.0, clamp((pace-1)/7))`, `pressure = clamp(finish_rate)`, `wear = clamp((absorbed-1)/6)`, `size = lerp(0.84, 1.04, clamp((reach-64)/20))`, `mirror = stance==='Southpaw'`, `tilt = stance==='Switch' ? 0 : -0.14`, `coreShift = lerp(16, -16, clamp((head_pct*100-30)/60))`, `creaseCount = ko_losses`, `markCount = fights.length`, `seed = params.fighter_id`.
    - Defaults + flags: reach NULL → 72 + `reach_missing`; stance NULL/Other → Orthodox + `stance_missing`; pace or absorbed NULL → 3.5 / 3.0 + `no_stats`; head_pct NULL → 0.6 (no flag).
  - `export function drawPrint(canvas, svg, params, fights)`: the spike's `grow` + inking, driven by `printPlan` (seed = `hashStr(fighter_id)`; minutiae from `fights`; creases from `creaseCount`). The svg overlay is drawn but hidden (the Forensic view toggle is Phase 2).
- [ ] **Step 1: Write failing tests** (`node --test app/components/fingerprint/`):
  - `pattern mapping`: each of the 5 archetypes → its pattern.
  - `missing reach and stance use defaults`: `reach_in null, stance null` → `size === lerp(0.84,1.04,0.4)`, `mirror false`, flags include `reach_missing` and `stance_missing`.
  - `no stats does not produce NaN`: pace/absorbed/head null, `finish_rate 0`, `fights []` → every numeric field `Number.isFinite`, flags include `no_stats`, `markCount 0`.
  - `southpaw mirrors, switch is upright`.
  - `same input, same plan` (deep-equal twice).
- [ ] **Step 2:** Run `node --test app/components/fingerprint/`. Expected: FAIL.
- [ ] **Step 3:** Implement `fingerprint.js` by moving the spike code into the module, plus `demo.html`.
- [ ] **Step 4:** Run tests. Expected: PASS. Open `demo.html` in a browser and confirm the two prints look like the spike's (black ink, real ridge flow).
- [ ] **Step 5:** Commit: `feat: fingerprint renderer module from spike`.

---

### Task 8: Streamlit compare page

**Files:**
- Create: `app/streamlit_app.py`, `app/data.py`, `app/render.py`
- Test: `tests/app/test_data.py`, `tests/app/test_render.py`, `tests/app/test_page.py`

**Interfaces:**
- Consumes: marts `fighter_print_params`, `fighter_fight_timeline`, `fighter_career_stats`; `fingerprint.js`.
- Produces:
  - `app.data.list_fighters(conn) -> list[tuple[str, str]]`: `(fighter_id, "Name (W-L-D)")` for every fighter in `fighter_print_params`, sorted by name; duplicate names get the weight appended, e.g. `"Bruno Silva (185 lbs) (…)"`.
  - `app.data.print_payload(conn, fighter_id: str) -> dict`: `{"params": {...}, "fights": [...]}` with JSON-safe types (dates → ISO strings, numerics → float or None).
  - `app.data.stat_rows(conn, a_id: str, b_id: str) -> list[dict]`: one dict per stat (`label`, `a`, `b`, `edge` ∈ `a/b/even`) for: sig. strikes landed/min, absorbed/min (lower is better), accuracy, defense, takedowns/15, TD defense, control share, finish rate, record, reach, stance.
  - `app.render.prints_html(a: dict, b: dict) -> str`: a self-contained HTML document that inlines `fingerprint.js` and the two payloads as JSON inside `<script type="application/json">`, escaping `</` so a fighter name can't break out of the script tag.
  - Page: two selectboxes (defaults: the two fighters with the most fights), the prints via `st.components.v1.html(prints_html(...), height=520)`, a small "what drove this print" list per fighter from the flags and inputs, and the stat table.
- [ ] **Step 1: Write failing tests:**
  - `test_print_payload_shape` (uses `built_marts`): keys `params`, `fights`; `fights` ordered by `fight_seq`; `json.dumps` succeeds.
  - `test_duplicate_names_are_distinguishable`: the two Bruno Silva labels differ (`"Bruno Silva (125 lbs) (0-1-0)"` vs `"Bruno Silva (185 lbs) (1-0-0)"`).
  - `test_stat_rows_edges`: lower absorbed/min wins the `edge`.
  - `test_prints_html_escapes_script_close`: a fighter name `"</script><b>x"` doesn't appear raw in the output.
  - `test_page_renders` using `streamlit.testing.v1.AppTest.from_file("app/streamlit_app.py")` with the test DB env → no exception, two selectboxes.
- [ ] **Step 2:** Run `uv run pytest tests/app -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `data.py`, `render.py`, `streamlit_app.py`.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: streamlit compare page with live prints`.

---

### Task 9: Dagster orchestration, full Docker Compose, real run

**Files:**
- Create: `src/ufc/orchestration/__init__.py`, `src/ufc/orchestration/definitions.py`, `src/ufc/cli.py`, `Dockerfile`, `workspace.yaml`
- Modify: `docker-compose.yml` (add `dagster` and `app` services), `dbt/models/sources.yml` (dagster asset-key meta), `src/ufc/identity/aliases.csv`
- Test: `tests/test_orchestration.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - Resource `GitHubSource(ConfigurableResource)` with `client() -> httpx.Client` (tests swap in a MockTransport client).
  - Assets: `raw_snapshots` (fetch all 6 + latest commit; metadata: new-snapshot count, commit sha) → `src_tables` (`load_latest` per file; metadata: rows, skipped) → `fighter_identity` (`build_identity`; metadata: counts per method) → `@dbt_assets` over the dbt manifest. In `sources.yml`, `meta: {dagster: {asset_key: ["src_tables"]}}` on the src tables and `["fighter_identity"]` on the identity source.
  - Asset check `source_freshness` on `raw_snapshots`: WARN if the latest upstream commit is > 7 days old.
  - Schedule `weekly_refresh`: all assets, cron `0 10 * * 0`, `America/Toronto`.
  - `defs = Definitions(...)` in `definitions.py`.
  - `ufc.cli` (`python -m ufc.cli {fetch,load,identity,all}`) for running without Dagster.
  - Compose: `postgres` (Task 1); `dagster` (Dockerfile image, `dagster dev -h 0.0.0.0 -p 3000 -m ufc.orchestration.definitions`, port 3000, `DAGSTER_HOME` volume); `app` (`streamlit run app/streamlit_app.py`, port 8501). The Dockerfile installs with `uv sync --frozen` and runs `dbt parse` at build time.
- [ ] **Step 1: Write failing tests:**
  - `test_definitions_load`: `defs.get_all_asset_specs()` includes `raw_snapshots`, `src_tables`, `fighter_identity` and the mart `fighter_print_params`; the schedule's cron and timezone match.
  - `test_ingest_assets_with_mock_source` (db): `materialize([raw_snapshots, src_tables, fighter_identity], resources={"source": <mock serving the fixture CSVs + a commit JSON>})` succeeds; running it again reports 0 new snapshots and every file `skipped`.
  - `test_freshness_warns_when_stale`: a commit date 10 days old → check severity WARN, `passed False`.
- [ ] **Step 2:** Run `uv run pytest tests/test_orchestration.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement the definitions, CLI, Dockerfile and compose services.
- [ ] **Step 4:** Run the full suite: `uv run pytest -v && node --test app/components/fingerprint/`. Expected: all PASS.
- [ ] **Step 5: Real run.** `docker compose up -d --build`; in the Dagster UI (http://localhost:3000) materialize all assets. Expected: success, with the `fighter_identity` metadata showing unresolved = 0 or a small number.
- [ ] **Step 6:** For each unresolved name (`select * from src.fighter_identity where method = 'unresolved'`), look up the right fighter in `src.ufc_fighter_tott` and add it to `aliases.csv`; re-materialize until unresolved = 0 (or every remaining case is noted as genuinely missing from tott). Record the final counts per method for INTERVIEW.md later.
- [ ] **Step 7:** Open http://localhost:8501, compare two well-known fighters, and confirm the prints draw and the stats look plausible.
- [ ] **Step 8:** Commit: `feat: dagster orchestration, weekly schedule and full compose stack`.

---

### Task 10: README for the resume

**Files:**
- Create: `README.md`, `docs/img/compare.png` (screenshot of two real prints from Task 9)

- [ ] **Step 1:** Write the README: a one-line pitch; the screenshot; an architecture diagram (spec §6, updated for the CSV source); "Run it" (`docker compose up -d --build`, then materialize in Dagster, then open the app); "What the pipeline does" (snapshots, contract, shrink guard, identity resolution with the real counts per method, dbt layers and tests, schedule, freshness); "How to read a print" (the mapping table); data credits (Greco1899/scrape_ufc_stats, GPL-3.0; UFCStats); and why it doesn't scrape UFCStats directly.
- [ ] **Step 2:** Verify from a clean clone: `git clone . /tmp/ufc-check && cd /tmp/ufc-check && docker compose up -d --build` reaches healthy services (then `docker compose down` there).
- [ ] **Step 3:** Commit: `docs: readme with architecture, run steps and print guide`.
- [ ] **Step 4 (candidate):** Create a public GitHub repo and push `main`. The agent doesn't do this (it's the candidate's account).
