# Handoff: Fighterprints (final, 2026-11-26)

**Status: finished.** The site is live, the code is on GitHub, and no work is open. Only the checks under **What's left** remain, and they're yours.

## Why this exists
Portfolio project (now named **Fighterprints**) for a **Data Engineer interview at Canada's Department of National Defence**.
- **Resume due:** ~2026-11-30 (needs a public GitHub link).
- **Interview:** ~late December 2026.

## Where we are
**Phase 1 is done, merged into `main` and public at https://github.com/jesthanpham/fighterprints** (pushed 2026-11-25). Commits use GitHub's private no-reply email.

**Live since 2026-11-25:** https://fighterprints.up.railway.app on Railway (project `fighterprints`: Postgres + `web` + `pipeline` cron job, Sundays 15:00 UTC). The database has no public address (public access was tried and switched off); Dagster's UI runs locally via `docker compose up`, and cloud runs are visible in Railway's Cron Runs tab. The Discord bot project on the same account is untouched. The cron (`0 15 * * 0`) is set in the Railway dashboard (pipeline → Settings → Cron Schedule); Railway ignores railway.json on CLI uploads. Deploy code changes with `./scripts/deploy.sh`.

| Piece | Status |
|---|---|
| Pipeline: download 6 CSVs → snapshots → header contract + shrink guard → `src` tables | ✅ |
| Fighter identity resolution (99.94% matched; 10 of 18,030 appearances unresolved) | ✅ |
| dbt staging → intermediate → marts (career stats, archetypes, print contract, style percentiles) | ✅ |
| Dagster: lineage, freshness check; in the cloud the weekly trigger is Railway cron (Sun 15:00 UTC) | ✅ |
| Website: wide layout with large prints (up to 460px, drawn at 800×1000), two pickers, prints that draw themselves stroke by stroke (no reload/blink), count-up **style match** %, a **Forensic view** toggle (marks, hover notes, two explainer tables), a small data-credit line, off-white, no Streamlit chrome, fingerprint favicon, stacks on phones | ✅ |
| README with a current screenshot, architecture, how prints, similarity and Forensic view work | ✅ |
| `docs/INTERVIEW.md`: pitch, demo script (ends on Forensic view), likely questions, numbers, weak spots | ✅ |
| Fresh-clone check (empty DB → full run from GitHub → 2,778 prints) | ✅ |
| Tests: 77 pytest, 15 renderer (node), 33 dbt data tests + 6 dbt unit tests; CI green on GitHub | ✅ all green |

## CI
GitHub Actions runs lint, the pytest suite (including the full dbt build against a Postgres service) and the renderer tests on every push; the README badge shows the result.

## How to run it
Docker is OrbStack; its CLI lives at `~/.orbstack/bin` (not on PATH in every shell).

```bash
docker compose up -d --build        # postgres :5433, Dagster :3000, app :8501
docker compose exec dagster dagster asset materialize --select '*' -m ufc.orchestration.definitions
uv run pytest                        # needs the postgres container up
node --test 'app/components/fingerprint/*.test.mjs'
```

## What's left (yours)
1. **Phone check:** on a real phone, turn on Forensic view, tap a mark (its note should appear) and scroll to the two tables. The built-in browser's phone emulation drew the bottom of the frame wrongly, so this was never confirmed visually. If the button is missing, move it above the prints in `app/render.py`.
2. **Monday 2026-11-30:** check that Sunday's first scheduled cloud run is green in Railway → pipeline → Cron Runs.
3. **Resume:** done 2026-11-26 in `/Users/jp/Dev/resume/benz_pham_resume.tex` (rebuild with `tectonic`). The Fighterprints bullets are rewritten and the live site and GitHub links added; originals are kept as `*.before.*`. Open question: the resume says "Benz Pham", the GitHub account is `jesthanpham`.
4. **Interview prep:** practise `docs/INTERVIEW.md`; dry-run the demo: live site → Forensic view → Railway Cron Runs (Run now) → `docker compose up` → Dagster at http://localhost:3000 (Lineage).

Optional extras: tune archetype thresholds (GSP shows as Grappler), "Surprise me" button, shareable matchup links, download-print button, row-level change report between snapshots.

## Decisions settled (2026-11-25/26)
- **Forensic view: shown**, and **on when the page opens** (changed 2026-11-27; the button under the prints switches it off). It marks every fight (circle = win, square = loss, diamond = other; red = KO/TKO, blue = submission, grey = decision; no number labels). Hovering a mark shows a magnifying-glass cursor and a note naming the fight behind it (result, opponent, event, date, round and time). A table below the prints lists each print feature, the stat that drives it and both fighters' values; a second table shows how the style match is made (each stat's UFC percentile for both fighters, the gap, the average gap, the style-label penalty and the final score). Both come from the same code as the print and the score (`explainRows` in the renderer, `match_breakdown` in `app/data.py`), so they can't disagree. Switched off, the page shows just the prints and the score.
- **Fighter records in the pickers: kept.** They tell apart same-name fighters.
- **Data credit: back**, as one small grey line at the bottom linking `Greco1899/scrape_ufc_stats` (GPL-3.0).

## Key decisions already made
- **Source:** the community CSV extract `Greco1899/scrape_ufc_stats` (GPL-3.0). UFCStats bot-blocks scrapers, and we don't bypass that.
- **Prints are drawn in the browser** from the `marts.fighter_print_params` + `marts.fighter_fight_timeline` contract.
- **Similarity ("style match")** = 100 − the average UFC-percentile gap over 9 style dimensions (incl. where they aim), minus 10 if the style labels differ. No score if fewer than 4 shared dimensions.
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
