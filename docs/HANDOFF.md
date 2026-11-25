# Handoff: Fighterprints (as of 2026-11-23)

## Why this exists
Portfolio project (now named **Fighterprints**) for a **Data Engineer interview at Canada's Department of National Defence**.
- **Resume due:** ~2026-11-30 (needs a public GitHub link).
- **Interview:** ~late December 2026.

## Where we are
**Phase 1 is done, merged into `main` and public at https://github.com/jesthanpham/fighterprints** (pushed 2026-11-25). Commits use GitHub's private no-reply email.

| Piece | Status |
|---|---|
| Pipeline: download 6 CSVs → snapshots → header contract + shrink guard → `src` tables | ✅ |
| Fighter identity resolution (99.94% matched; 10 of 18,030 appearances unresolved) | ✅ |
| dbt staging → intermediate → marts (career stats, archetypes, print contract, style percentiles) | ✅ |
| Dagster: lineage, freshness check, weekly schedule (Sun 10:00 Toronto, on by default) | ✅ |
| Website: two fighter pickers, two generated fingerprints, similarity %, off-white, no explanations | ✅ |
| README with screenshot, architecture, how prints and similarity work | ✅ |
| Fresh-clone check (empty DB → full run from GitHub → 2,778 prints) | ✅ |
| Tests: 59 pytest, 6 renderer (node), 33 dbt data tests + 6 dbt unit tests | ✅ all green |

## How to run it
Docker is OrbStack; its CLI lives at `~/.orbstack/bin` (not on PATH in every shell).

```bash
docker compose up -d --build        # postgres :5433, Dagster :3000, app :8501
docker compose exec dagster dagster asset materialize --select '*' -m ufc.orchestration.definitions
uv run pytest                        # needs the postgres container up
node --test 'app/components/fingerprint/*.test.mjs'
```

## What to do next (in order)
1. **Resume:** add https://github.com/jesthanpham/fighterprints to the resume (done on GitHub's side).
2. **Phase 2 (write a new plan first):**
   - Tune archetype thresholds. For example GSP comes out as a Grappler, though most fans would call him a wrestler.
   - Write `docs/INTERVIEW.md` (60-second pitch, likely questions and answers) and `docs/ARCHITECTURE.md`.
   - Add a row-level change report between snapshots (rows added / changed / removed).
   - Optionally pre-render prints on the server, which would fully hide the logic from page source.
3. **Interview prep:** practise the live demo: Dagster lineage → a run → the compare page.

## Decisions waiting on you
- **Forensic view conflicts with "don't show how stats are used."** It marks every fight on the print. The overlay code exists but is hidden. Keep it hidden, or show it?
- **Fighter records in the pickers**, e.g. "Khabib Nurmagomedov (13-0-0)". They help tell apart same-name fighters. Keep or drop?
- **Data credit** was removed from the site (it's in the README). Re-add a small footer?

## Key decisions already made
- **Source:** the community CSV extract `Greco1899/scrape_ufc_stats` (GPL-3.0). UFCStats bot-blocks scrapers, and we don't bypass that.
- **Prints are drawn in the browser** from the `marts.fighter_print_params` + `marts.fighter_fight_timeline` contract.
- **Similarity** = 100 − the average UFC-percentile gap over 8 style dimensions, minus 10 if the style labels differ. No score if fewer than 4 shared dimensions.
- **Each CSV is its own Dagster asset** (`src/<file>`), so lineage connects into dbt.
- **Manual aliases** for 11 nickname/spelling cases live in `src/ufc/identity/aliases.csv`. 7 names are absent upstream and stay unresolved.

## Known minor issues (deferred)
- If one file fails the shrink guard mid-run, files loaded earlier in that run stay loaded. The run still fails visibly.
- The app's cached DB connection doesn't reconnect after a Postgres restart. Restart the `app` container.
- dbt models sit in Dagster's "default" group; they could be renamed "transform".
- 2 fights from "UFC - Road to UFC 4.6" have no event date, because the event is missing upstream.

## Gotchas
- Streamlit doesn't reload changed modules: restart the server or container after editing `app/*.py`.
- If Dagster shows stale dbt assets, run `uv run dbt parse --project-dir dbt --profiles-dir dbt`.
- Preview configs for this project live in `/Users/jp/Dev/.claude/launch.json` (`fingerprint-demo`, `ufc-app`).
- **Key docs:** `docs/superpowers/specs/2026-11-23-style-fingerprints-design.md` (design, source of truth) and `docs/superpowers/plans/2026-11-23-phase-1-pipeline-and-prints.md` (Phase 1 plan).
