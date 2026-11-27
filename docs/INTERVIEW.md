# Interview prep: Fighterprints

For the Data Engineer interview at the Department of National Defence. Read it out loud a few times; the answers are written the way you'd say them.

---

## 1. The 60-second pitch

> "I built an end-to-end data pipeline on the full UFC stats history: about 800 events, 9,000 fights and 42,000 fighter-rounds.
>
> The source has no API, and the stats site blocks scrapers, so I consume a community-published CSV extract instead, the way you'd receive an export from another team's system. The pipeline keeps every version of every file, checks each one against a column contract, and refuses files that suddenly shrink, so a broken upload can't wipe good data.
>
> The hardest part was identity. The stats files name fighters but don't identify them, and names collide: there are two Bruno Silvas. I wrote a rule-based matcher that resolves 99.94% of 18,000 appearances and logs exactly how each one was matched.
>
> Then dbt cleans and models it in tested layers, Dagster orchestrates it weekly with lineage and freshness checks, and the output feeds a web page that turns every fighter's career into a generated fingerprint and scores how similar two fighters are. Every ridge traces back to tested data. It's live: the pipeline re-runs in the cloud every Sunday and the site updates itself."

**If they only remember one thing:** *I take messy data from a system I don't control, prove it's correct, and make it usable.*

---

## 2. The demo (about 3 minutes)

**Before the interview:**
- [ ] Open the live site once so it's warm: https://fighterprints.up.railway.app
- [ ] Open **OrbStack**, run `docker compose up -d`, and open Dagster at http://localhost:3000 (the pipeline graph).
- [ ] Open Railway → fighterprints → **pipeline** → **Cron Runs** (the real Sunday runs, plus **Run now**).
- [ ] Have the README screenshot ready as a last resort.

**Script:**
1. **Dagster → Lineage** (http://localhost:3000). *"Here's the whole pipeline as a graph: the download, one asset per source file, identity resolution, then dbt's staging, intermediate and mart layers. Each box knows what it depends on."*
2. **Railway → pipeline → Cron Runs.** *"These are the real Sunday runs in the cloud; I can also click Run now."* Then back in Dagster, click a run: *"Every run is logged: how many new file versions arrived, rows loaded, how many names each matching rule resolved. The freshness check warns me if the upstream source stops updating."*
3. **The live site** (https://fighterprints.up.railway.app). Pick **Khabib Nurmagomedov** vs **Islam Makhachev** (85%), then swap one for **Max Holloway** (48%). Each print draws itself as you pick. *"Teammates with the same style score high; a wrestler against a volume striker scores low."*
4. **Forensic view** (on when the page opens). Every fight appears as a mark: shape for the result, colour for the method. Hover one: *"This mark is his first UFC fight: the opponent, the event, the round and time. Every mark traces back to a row in the database."* Scroll to the two tables: *"This is how each print is made, stat by stat, and this is the style match worked out line by line. The table and the big number come from the same function, so they can't disagree."*
5. **Close:** *"The page only reads three tables from the final layer. That's the contract between the pipeline and the app, and it's tested."*

---

## 3. Likely questions, and how to answer them

### The source

**Why not just scrape UFCStats?**
"The site serves a bot check to automated clients, so I respected that and used a published extract instead. It's also closer to real life: most of the time you don't control the source, you receive a file from another system and your job is to validate and integrate it."

**What happens if the source goes down?**
"Downloads retry three times with backoff. If it still fails, the run fails visibly and nothing downstream changes, so the app keeps serving the last good data. A separate freshness check warns if the upstream hasn't updated in seven days."

**What if they rename a column?**
"Every file has a header contract, an exact list of expected columns. If it changes, the load fails with a message naming the missing and unexpected columns. Loud failure beats silently loading garbage."

**What if they publish a broken or half-uploaded file?**
"A shrink guard refuses any file with less than 90% of the previous load's rows, and the old table stays in place. The load is one transaction, so it's all or nothing."

**How do you know what changed?**
"Every file is fingerprinted with a SHA-256 hash. Same hash means nothing to do, so reruns are idempotent. A new hash becomes a new immutable snapshot, so I keep full history and can always reprocess from raw."

**What if upstream reverts to an older version?**
"I hit that one. Because old versions are stored by hash, a revert wouldn't create a new snapshot, and 'newest snapshot' would have pointed at the wrong file. I fixed it by tracking when each version was *last seen* and wrote a test that reproduces the revert."

### Data quality

**How do you know the data is right?**
"Three levels. pytest covers the Python loaders and matcher. dbt unit tests pin the parsing rules: things like turning '11 of 25' into two numbers and computing fight time from formats like '5 Rnd (5-5-5-5-5)'. And 33 dbt data tests run on every build: unique keys, nobody lands more strikes than they attempt, every fight has exactly two fighters, the strike breakdowns add up."

**What happens when a test fails?**
"Structural problems are errors and stop the build. Things worth knowing but not blocking, like a few unresolved names, are warnings. Unresolved names become an error above 1%, because at that point the matching is broken, not just a few odd names."

**Tell me about a bug the real data caught.**
"My test data used whole numbers, but the real file writes counts as '3.0'. The first real build failed on casting. I added that format to the test data and a unit test, then fixed the parser. The lesson: make your test fixtures reproduce the real quirks, not the clean version you imagine."

### Identity resolution (the most likely deep-dive)

**How do you match fighters with no IDs?**
"In order of confidence: exact name; if the name is shared, the fighter whose weight matches the bout's division, then age on the event date; then a small manual alias list for nicknames; then a normalized name without accents or suffixes like 'III'; then fuzzy matching, only within the same weight class and only with a clear single winner. Everything else is marked unresolved, never guessed."

**Results:** 17,917 exact · 50 by weight · 1 by age · 22 alias · 26 normalized · 4 fuzzy · **10 unresolved out of 18,030 (0.06%)**. The 10 are fighters missing from the source's fighter list entirely.

**Why not just use fuzzy matching?**
"Fuzzy matching is confident and wrong in exactly the cases that matter, like two real people with the same name. I use it last, restricted to the same weight class, and I record the method on every match so it can be audited."

**How would this scale to millions of records?**
"Same idea, more formal: blocking on stable attributes like division and date of birth so you only compare likely candidates, a probabilistic record-linkage model instead of hand rules, and a human review queue for the low-confidence middle. The alias file is the small version of that review queue."

### Design choices

**Why Postgres, dbt and Dagster? Why not Airflow or Spark?**
"The data is about 12 MB, so Spark would be the wrong tool. Postgres is reliable and everywhere. dbt gives tested, version-controlled SQL with layers. I chose Dagster over Airflow because it models *data assets* rather than tasks, so lineage and freshness are built in. I'd be comfortable in Airflow too; the concepts map across."

**Why staging, intermediate and marts?**
"Staging makes raw data trustworthy, intermediate joins it into one row per fighter per fight, and marts are what consumers read. The app only touches three mart tables, so I can rework anything upstream without breaking it."

**How does the similarity score work?**
"Each fighter is ranked against the whole UFC on 9 style stats as percentiles, so very different stats share one 0–100 scale. Similarity is 100 minus the average gap, minus 10 if their style labels differ. If they share fewer than 4 stats, there's no score instead of a misleading one. On the site, Forensic view shows the working: each stat's percentile for both fighters, the gaps, the average, the penalty and the result."

**Why does the site open in Forensic view?**
"Because the point is that every number can be checked. The page opens on the audit trail: each mark traces to a fight, and both tables show the working, the same idea as a dashboard that lets you drill down to the source rows. One click switches to the clean view, just the prints and the score. Both views read the same tables."

**What would you change to run this in production?**
"CI already runs lint and every test on each push; I'd add branch protection so nothing merges while it's red. Alerts to email or Teams on failures. A read-only database user for the app; it currently uses the pipeline's user. Secrets in a vault instead of defaults. And probably a managed cloud database. Government of Canada teams commonly use Azure, and the design would move over as-is."

**Where does it run?**
"On Railway, as three services from one Docker image: Postgres, the website, and a pipeline job that Railway's cron starts every Sunday. The job runs every asset and check once, then exits, so I'm not paying to keep a scheduler awake all week. The database has no public address; only those services can reach it. For exploring the pipeline, I run the identical stack locally in Docker."

**What if a Sunday run is missed or fails?**
"Each run compares file hashes instead of looking at 'the last 7 days', so the next run catches up on everything it missed. A failed run leaves the previous good data in place, and the failure shows in Railway's logs and in Dagster's run history."

### About you

**Why this project?**
"I wanted something I'd enjoy explaining, but with real data-engineering problems: no API, a source I don't control, messy formats and no IDs. Those are the same problems as merging records between government systems."

**Did you build it yourself?**
Be straight about it: *"I designed it and built it with an AI coding assistant, the way a lot of teams work now. I made the design calls, reviewed everything, and I can walk you through any part of it."* Then prove it by explaining any piece they point at. That's what this document is for.

---

## 4. How it maps to DND work

| In this project | At DND |
|---|---|
| Consuming another system's CSV export | Receiving extracts from partner systems or departments |
| Header contract + shrink guard | Validating feeds before they reach reporting |
| Identity resolution without shared IDs | Linking personnel, supplier or asset records across systems |
| Immutable snapshots + method recorded on every match | Audit trail and data provenance |
| Weekly schedule + freshness check | Reliable, monitored batch loads |
| Mart tables as the app's only contract | Stable data products for analysts and dashboards |

---

## 5. Numbers to know

- **798** events (March 1994 → November 2026), **9,015** fights, **42,334** fighter-rounds, **2,778** fighters with prints
- **18,030** fighter appearances resolved; **99.94%** matched; **10** unresolved
- **6** source files, about **12 MB**; a full rebuild takes about a minute
- **33** dbt data tests + **6** dbt unit tests, **77** Python tests, **15** renderer tests, all run by CI on every push
- Retries: **3** · shrink guard: **90%** · freshness: **7 days** · unresolved error threshold: **1%** · fuzzy threshold: **92**
- Schedule: Sundays 15:00 UTC (10:00 Toronto), Railway cron · hosting: about $4/month of Railway usage

---

## 6. Weak spots: know them before they find them

Saying these first comes across as maturity, not weakness.

- **The style labels need tuning.** GSP comes out as a Grappler. The thresholds are simple percentile rules on purpose, so they're explainable.
- **If one file fails mid-run, files loaded earlier in that run stay loaded.** Each file is internally consistent and the run fails visibly, but a stricter design would stage all six and swap them in together.
- **The app uses the pipeline's database user.** In production it would get a read-only user.
