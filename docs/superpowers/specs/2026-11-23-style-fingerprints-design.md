# UFC Style Fingerprints — Design

**Date:** 2026-11-23
**Status:** Approved 2026-11-23

## 1. Why this exists

A portfolio project for a **Data Engineer interview at Canada's Department of National Defence (DND)**. It has to:

- show a real end-to-end data pipeline (extract → raw storage → clean → model → serve, on a schedule, with tests);
- be fun, so the candidate enjoys talking about it (they follow MMA, LoL, and NFL);
- be fully explainable by the candidate. Every piece must be something they can defend in a follow-up question.

The hiring manager doesn't follow hockey, and probably not MMA either. The demo therefore has to land with someone who knows nothing about the sport: "pick any two fighters, see how their styles match up."

## 2. What it does

Loads every UFC event, fight and fighter (the UFCStats.com data, via a community project that publishes it as CSV files), keeps every version of those files, cleans them into tables, and builds a **style fingerprint** for every fighter. Examples: striker vs. wrestler, how much they absorb, whether they fade in later rounds, where they land strikes. The fingerprint is literal: the pipeline **generates a realistic inked fingerprint image for every fighter**, where every visual feature is driven by their stats and every fight in their career is a mark on the print. A small web app lets you pick two fighters and compare their prints and stats side by side.

## 3. Goals, non-goals, anti-goals

**Goals**
- One command (`docker compose up`) brings up the database, the orchestrator UI, and the app.
- Full historical backfill, followed by cheap weekly incremental updates.
- A layered data model: raw → staging → intermediate → marts.
- Data quality tests that catch real problems (e.g. strikes landed > attempted).
- Failure handling that's easy to explain: retries, a header contract, a shrink guard, a freshness check.
- Written explainer material so the candidate can answer interview questions about every design choice.

**Non-goals**
- Robbery tracker / judges' scorecards. The schema should leave room for it as a later extension, but it isn't built now.
- Fight predictions, betting, or odds.
- Machine learning. Archetypes are rule-based on purpose, so they can be explained.
- Cloud deployment. It runs on a laptop and is demoed by screen share or in person.

**Anti-goals (failure even if it "works")**
- Anything the candidate can't explain in plain words.
- Getting around UFCStats' bot check, or scraping it at all.
- Over-engineering: Kafka, Spark, Kubernetes. The data is small; using big-data tools here would be a red flag to a good interviewer.

## 4. Constraints

- **Machine:** macOS with Homebrew and `uv` installed. **Docker isn't installed yet.** The candidate needs to install Docker Desktop or OrbStack (their own download/install). Python 3.12 is managed by `uv` inside the project; system Python 3.9 isn't used.
- **Source (changed 2026-11-23):** UFCStats.com now puts a JavaScript bot-check ("Checking your browser…") in front of every page, so scraping it directly is off the table; we don't bypass bot checks. Instead the source is the community repo **github.com/Greco1899/scrape_ufc_stats** (GPL-3.0), which publishes UFCStats data as 6 CSV files refreshed every few days (last refresh 2026-11-22). Raw URL base: `https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main/`. Files: `ufc_event_details.csv`, `ufc_fight_details.csv`, `ufc_fight_results.csv`, `ufc_fight_stats.csv`, `ufc_fighter_details.csv`, `ufc_fighter_tott.csv`. Credit the repo and UFCStats in the README.
- **Data size (2026-11-23):** 798 events, 9,040 fights, 42,492 fighter-round stat rows, 4,630 fighters, about 12 MB in total. A full load takes seconds.
- **Known source quirks (profiled 2026-11-23):**
  - Stats identify fighters **by name only**. 7 duplicate names appear in fights (e.g. two Bruno Silvas: 125 lb and 185 lb).
  - 24 names in fights don't exactly match the fighter list (e.g. "Rafael Cerquiera", "Waldo Cortes Acosta", "Kai Kamaka III").
  - One fight appears under two event names (renamed event; 25 duplicate fight URLs in `fight_details`).
  - 42 stat rows are blank (early events with no stats).
  - Trailing spaces in event and method fields; `---`, `--` and empty strings all mean "missing".
  - Reach is missing for 2,140 fighters and stance for 1,023.
  - Outcome is `W/L` / `L/W` / `D/D` / `NC/NC`, in the same order as the "A vs. B" bout name.
  - Methods include `TKO - Doctor's Stoppage`, `Overturned`, `DQ` and `Could Not Continue`.
- **No downloaded data committed to git.** The repo holds code only, so it can go on the candidate's GitHub.

## 5. Approaches considered

| | Stack | Trade-off |
|---|---|---|
| **A (chosen)** | Postgres + Dagster + dbt + Streamlit, Docker Compose | Looks like a real data team's setup; Dagster's UI makes a great visual walkthrough. More pieces to learn. |
| B | DuckDB file + dbt + GitHub Actions cron | Fastest, no servers. Reads as a personal project; less to say about running it in production. |
| C | Airflow + cloud bucket + cloud DB | Big resume names, but massively oversized for this data, and it invites deep Airflow questions. |

**Chosen: A.** The candidate asked me to pick. Timing (resume in 1 week, interview in about 1 month) fits A with the phasing in section 10. The *why*: A is the closest to how a government data engineering team actually works (a scheduled, monitored batch pipeline into a relational database), and it gives the most interview material without being oversized. If the interview date turns out to be very close, fall back to B (same loader and dbt models, swap Postgres → DuckDB and Dagster → a cron script).

## 6. Architecture

```
GitHub: Greco1899/scrape_ufc_stats (6 CSVs, refreshed every few days)
    │  downloader (retries, records upstream commit SHA)
    ▼
raw.file_snapshots   ← every distinct version of every file, never modified (file, sha256, source_commit, fetched_at, bytes)
    │  header contract check + load (only when a file's sha256 changed)
    ▼
src.<file>           ← latest snapshot as all-text columns + src.load_log (row counts per load)
    │  identity resolution (Python): which fighter is "Bruno Silva" in this fight?
    ▼
src.fighter_identity ← (fight, name as written) → fighter_id, how it was matched
    ▼  dbt
staging      → types fixed: "15 of 30" → landed/attempted, "3:45" → seconds, "--" → NULL
intermediate → one row per fighter per fight, with "for" AND "against" stats
marts        → fighter_career_stats, fighter_fingerprint, fighter_round_trend
    │
    ▼
Streamlit app: single-fighter view + two-fighter comparison
```

All of it is orchestrated by **Dagster** as assets (file snapshots → src tables → identity → dbt models), so the UI shows the whole lineage, every run, and any failures.

### 6.1 Extract (downloader)
- Download all 6 files and record the upstream commit SHA from the GitHub API.
- Store a new snapshot **only if the file's sha256 changed**. Re-running with no upstream change is a no-op (idempotent).
- Retries: 3 attempts with exponential backoff; a failed file fails the run, and the previous good data stays in place.
- **Freshness check:** warn if the upstream repo hasn't updated in 7 days.

### 6.2 Load + contract
- **Header contract:** each file has an exact expected column list. A renamed or missing column fails the load loudly (schema drift) instead of loading garbage.
- **Shrink guard:** refuse a snapshot whose row count drops more than 10% below the previous load. That's the "truncated or broken upstream file" alarm.
- Load into `src.<file>` as all-text columns; cleaning is dbt's job. Every load writes a row to `src.load_log`.

### 6.2b Fighter identity resolution
Stats and bouts name fighters; the fighter list has IDs. Resolve every (fight, name) to a `fighter_id`, in this order:
1. Exact name with one candidate.
2. Exact name with several candidates: pick the one whose listed weight matches the bout's weight class. If that's still ambiguous, pick the one aged 18–45 on the event date.
3. Manual alias seed (`fighter_name_aliases.csv`: name as written → fighter_id) for cases rules can't settle.
4. Normalized name: lowercase, strip accents, hyphens → spaces, drop Jr./II/III, collapse spaces.
5. Fuzzy match (similarity ≥ 92) among fighters in the same weight class.
6. Otherwise **unresolved**: recorded, warned about by a test, and excluded from fingerprints.

Each match records how it was made (`exact`, `exact_weight`, `exact_age`, `alias`, `normalized`, `fuzzy`, `unresolved`), so the candidate can say exactly how many of each there were.

### 6.3 Transform (dbt)
- **staging:** trim everything, turn `---` / `--` / empty into NULL, split "X of Y" fields, convert `m:ss` times to seconds, dedupe fights by fight URL, drop blank stat rows, and group methods into `KO_TKO` (incl. doctor's stoppage), `SUB`, `DEC` (unanimous/split/majority) and `OTHER` (DQ, overturned, could not continue, other). Elapsed fight time comes from the round, the time, and the round lengths in the time format (e.g. `5 Rnd (5-5-5-5-5)`).
- **intermediate:** `int_fighter_fight` has, per fighter per fight, their own stats plus their opponent's (= what they absorbed), fight time in seconds, result, and method.
- **marts:**
  - `fighter_career_stats`: per-minute and percentage stats over a fighter's UFC career.
  - `fighter_round_trend`: output by round number (for the "fade" metric).
  - `fighter_fingerprint`: the metrics below plus the archetype label and a `small_sample` flag.

### 6.4 Fingerprint metrics (builder's call where marked)
- **Striking:** significant strikes landed/min, absorbed/min, accuracy %, defense %, knockdowns per 15 min.
- **Grappling:** takedowns per 15 min, takedown accuracy %, takedown defense %, control time share %, submission attempts per 15 min.
- **Target mix:** head / body / leg % of significant strikes landed.
- **Position mix:** distance / clinch / ground % of significant strikes landed.
- **Fade:** round 3 output ÷ round 1 output (fighters with 3+ rounds only).
- **Finishing:** finish rate, split by KO/TKO and submission.
- **Archetype (rule-based):** Striker, Wrestler, Grappler, Pressure/Brawler, Balanced. Thresholds are percentiles across the roster, documented in the model so the candidate can explain them. *Exact thresholds are the builder's call; tune them until well-known fighters land where an MMA fan would expect.*
- **Small sample:** fewer than 3 UFC fights or under 15 minutes of fight time → shown but flagged.
- Early UFC fights with missing detailed stats are excluded from the per-minute metrics but still count for the record.

### 6.5 Data quality tests (dbt)
- Keys: unique / not null on event, fight, fighter, and (fight, fighter, round).
- Logic: landed ≤ attempted; round number 1–5; control time ≤ round length; every fight has exactly 2 fighters; method is in the accepted set; target-mix and position-mix percentages each sum to ~100%.
- Freshness: warn if the latest event is older than 30 days.
- Identity: warn if any fight appearance is unresolved; fail if more than 1% are.

### 6.6 Fingerprint images (the hero feature)

Every fighter gets a generated, realistic black-ink fingerprint. A throwaway prototype with fake fighters proved the look and the mapping: `spike/fingerprint-spike.html`. **That file is the reference implementation** for the algorithm, parameters and mapping. Port it; don't reinvent it.

**How a print is grown:**
1. Build a ridge-direction field from "cores" and "deltas" (the Sherlock-Monro model from fingerprint science). Where the cores and deltas sit decides the pattern type.
2. Start from seeded random noise and apply oriented Gabor filters about 12 times along that field. Ridges grow out of the noise with natural splits and endings.
3. Ink it: a pressure threshold, uneven pressure, wear, pores, rough edges, creases, and edge falloff.

**Stat → print mapping (decided with the candidate):**

| Print feature | Driven by | Source |
|---|---|---|
| Pattern type | Archetype: Striker = whorl, Wrestler = loop, Grappler = double loop, Brawler = tented arch, Balanced = plain arch | `fighter_fingerprint.archetype` |
| Ridge spacing | Pace: sig. strikes landed/min (more = tighter) | career stats |
| Ink pressure (bold ↔ faint) | Finish rate (KO + sub wins ÷ wins) | fight results |
| Worn, broken ridges | Sig. strikes absorbed/min | career stats |
| Creases | One per KO/TKO loss | fight results |
| Minutiae (ridge defects) | One per UFC fight, placed chronologically from the core outward like tree rings | fight timeline |
| Left or right hand | Stance: orthodox = right, southpaw = mirrored left, switch = upright | fighter page |
| Core height | Head-strike % (head hunters high, body/leg low) | sig. strikes by target |
| Print size | Reach | fighter page |
| Fine detail | Seeded from the UFCStats fighter ID, so it's deterministic and unique | fighter ID |

**Forensic view:** an overlay marks every fight on the print. Circle = win, square = loss; red = KO/TKO, blue = submission, grey = decision; numbered in order. Hovering a mark shows the real fight: event, date, opponent, method and round. This is the demo moment: every mark is a real row in the database.

**Where it runs (decided with the candidate):** prints are **drawn live in the browser** by the spike's JavaScript, reused almost as-is as a Streamlit HTML component. It takes about 0.2s per print. The pipeline's job is to publish a clean, tested **data product**: the print inputs (`fighter_print_params`) and the fight list (`fighter_fight_timeline`). The frontend turns those into the image. Interview line: "the pipeline publishes clean, tested data; the app renders it."
- *Why not pre-render in the pipeline:* it needed a numpy port of the renderer, the riskiest task in the resume week, plus an hour-long first backfill. Rejected for now. It's an optional Phase 2 extra (`fighter_prints` asset) if time allows.
- The renderer takes exactly one fighter row plus their fight list as JSON. It doesn't query anything itself.

**Known limitation (from the spike):** a fight's mark points to a spot where the ridges are disturbed, but whether that spot comes out as a split or an ending isn't controlled. Acceptable; stating it honestly is fine in the interview.

**Feeds:**
- mart `fighter_print_params`: one row per fighter with every input in the table above, plus `input_hash`.
- mart `fighter_fight_timeline`: one row per fighter per fight, in order, with result, method, event, date, opponent and round, for the minutiae and overlay.
- **Stance** and **reach** come from `ufc_fighter_tott.csv`; **sig. strikes by target** (HEAD/BODY/LEG) from `ufc_fight_stats.csv`. Missing reach or stance falls back to a default (reach 72", orthodox) and is flagged; it must never break a print.

### 6.7 Serve (Streamlit)
- **Fighter page:** the fingerprint (with a Forensic view toggle), archetype badge, a "how to read this print" list for that fighter (e.g. "21-5 → 26 marks, 81% finish rate → heavy ink"), career stats, and a round-by-round output chart.
- **Compare page:** pick two fighters → both prints side by side, a **style match %** (distance between their normalized stat vectors, with a penalty for different archetypes), a stat-by-stat table with the edge highlighted, and 3–5 plain-English "edges" lines (e.g. "A lands 2.1 more sig. strikes/min; B averages 3.4 takedowns per 15").
- Download any print as a PNG (canvas export in the browser).
- Reads only from the marts schema.

### 6.8 Orchestration (Dagster)
- Assets: `raw_snapshots` → `src_tables` → `fighter_identity` → dbt assets (loaded via `dagster-dbt`). The marts `fighter_print_params` and `fighter_fight_timeline` are the hand-off to the app.
- Schedule: weekly, Sunday 10:00 ET (UFC events are usually Saturday nights).
- A manual "backfill" job for the first full load.

## 7. Repo layout (proposed)

```
ufc-fingerprints/
  docker-compose.yml        # postgres, dagster (webserver + daemon), streamlit
  pyproject.toml            # uv-managed, Python 3.12
  src/ufc/
    ingest/                 # download + snapshot, header contract, load
    identity/               # fighter identity resolution
    orchestration/          # Dagster assets, schedule, checks
  dbt/                      # staging / intermediate / marts + tests
  app/                      # Streamlit
  tests/                    # pytest + small CSV fixtures
  docs/
    ARCHITECTURE.md         # the diagram above, in plain words
    INTERVIEW.md            # likely questions + how to answer them
  README.md
```

## 8. Interview explainer (deliverable)

`docs/INTERVIEW.md` covers, in plain language:
- the 60-second pitch;
- why each tool was chosen and what the alternative was;
- "why not scrape UFCStats directly?" (it bot-blocks scrapers; we respect that and consume a published extract, which is how government teams usually receive data from other systems);
- "what happens if the upstream repo stops updating / renames a column / publishes a broken file?";
- how fighter identity resolution works and how many fights each rule matched;
- "how would you scale this to 1000× the data?" (honest answer: you don't need to here, but here's what would change);
- how this maps to DND-style work: merging records from different systems, scheduled loads, data quality, lineage.

## 9. Decided vs. left to the builder

**Decided:** stack (A), source (the community CSV extract of UFCStats, not direct scraping), layered model, rule-based archetypes, weekly schedule, no committed data, the interview explainer doc, generated fingerprint images with the stat mapping in 6.6 and the black-ink look from the spike.

**Builder's call:** contents of the alias seed, archetype thresholds, chart library inside Streamlit, exact table column names, styling, how the spike's JS is packaged into the Streamlit component (it must visually match the spike).

### Calls made during the builder review (flagged for the candidate to check)
- **Laptop asleep on Sunday:** the schedule only fires while Docker is running. Each run compares file hashes rather than looking at "the last 7 days", so a missed week catches up automatically on the next run. (This is also a good interview answer.)
- **Draws and no contests:** they count as fights (marks on the print) but not as wins or losses.
- **Which fighters:** only fighters with at least one UFC bout on UFCStats get a fingerprint.
- **Weight class:** carried through to the marts and shown on the compare page, so a cross-division comparison is obvious.
- **GitHub:** the repo is written to be public-portfolio ready (README, no secrets, no downloaded data).

## 10. Timeline

**Resume due ~2026-11-30 (1 week). Interview ~late December (about 1 month).** Stack A stays; the work is split into phases so a working, public repo exists before the resume goes out.

**Phase 1, by the resume deadline (must be on GitHub and work end to end):**
- Docker Compose with Postgres, Dagster and Streamlit
- Downloader + snapshots + header contract + load, and fighter identity resolution
- dbt staging → intermediate → `fighter_career_stats`, a first `fighter_fingerprint` with simple archetype rules (tuning comes in Phase 2), `fighter_print_params`, `fighter_fight_timeline`
- Core dbt tests (keys, landed ≤ attempted, 2 fighters per fight)
- dbt tests on the print inputs (no nulls in archetype, finish rate, KO losses or record; reach and stance may be NULL because the renderer applies flagged defaults; stance in the accepted set, fight count in the timeline = wins + losses + draws/NC)
- Streamlit compare page: the spike's renderer as an HTML component, drawing two real prints side by side, plus the stat table
- README with the architecture diagram, how to run it, and a screenshot of two real prints

**Phase 2, before the interview:**
- Archetype threshold tuning; fade metric and round trend chart
- Forensic view overlay with real fight details, style match %, PNG download
- Optional extra: a pre-rendered `fighter_prints` pipeline asset (PNG per fighter, regenerated only when `input_hash` changes)
- Row-level change report between snapshots (rows added / changed / removed per file)
- Fighter page and plain-English "edges" lines
- `docs/ARCHITECTURE.md` and `docs/INTERVIEW.md`
- The candidate runs a full demo end to end and practises the walkthrough

If Phase 1 slips, the cut line is: keep the pipeline and a bare page that draws prints from the marts. Drop the stat table and comparison polish to Phase 2. The pipeline is what matters for the resume; the prints are what makes people click.

## 11. Open questions for the candidate

- Docker Desktop or OrbStack needs to be installed on the Mac before building starts.
