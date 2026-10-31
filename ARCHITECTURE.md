# Architecture baseline

Prepared on 2026-10-31, before the problem statement (PS), and written to fit any
"data from several sources, find what went wrong, explain it" PS. Every line
to change for the PS is marked `PS:`; `grep -n "PS:" analyze.py static/index.html`
lists them. Formats and interfaces are in `contracts/README.md`.

## Pipeline

```
data/raw/<source>/ -> generate.py -> data/sessions/<case>/*.csv -> analyze.py -> <case>/report.md
                      (PS-specific)   (+ answer.txt)                    |
                                                         app.py + static/index.html
```

`analyze.py`, for one case folder:

| Step | Function | What it does |
|---|---|---|
| a | `load()` | every CSV onto one timeline of fixed steps: number columns become series (`file.column`), text columns become events, plus `file.count` |
| b | `find_incidents()` | steps where a series breaks its limit in `LIMITS`, joined into incidents when at most `GAP` normal steps separate them |
| c | `build_pack()` | per incident: every series averaged over 4 windows (30-15 and 15-0 steps before, first and last 10), and the events from `LEAD` steps before to the end, grouped when they differ only in numbers, each with its count, first and last time, and one real example |
| d | `ask_llm()` | the pack and `SYSTEM_PROMPT` to DeepSeek (any OpenAI-style API: change `API_URL`, `API_KEY`, `MODEL`) |
| e | `run()` | writes the report plus the pack as `report.md`, only after the LLM answers |

`timeline()` gives the page the same series, limits and incidents as JSON.
`python3 analyze.py --pack <case>` prints the evidence without calling the LLM.

## Settings in analyze.py

| Setting | Default | Change it when |
|---|---|---|
| `STEP` | 1 minute | the data is per second, hour or day |
| `LIMITS` | `web.response_ms > 1000` | always: the PS's "bad" (a fixed target, never "3x the median") |
| `TOTALS` | none | a series should add up within a step (sales, bytes), not average |
| `SYSTEM_PROMPT` | a web app | always: its first paragraph names the system; sections follow the PS's outputs |
| `GAP`, `LEAD`, `KINDS` | 2, 5, 40 | rarely |

The page (`static/index.html`) knows no metric names: it draws one chart per
series from `/api/timeline`, grouped by file, with incidents shaded, a dashed
line at each limit and one zoom button per incident. Only its title is `PS:`.

## Fit check, during Understand (0:00-0:15)

The skeleton bends to the PS, never the other way round. Find the PS's rows
below; the pipeline proposal then says, per file, keep, change or replace.
A required output with no row gets its own function, not a workaround.

| The PS needs | Keep | Change |
|---|---|---|
| Incidents in time-series data (outage, IoT fault, fraud spike, sales drop) | everything | `generate.py` and the `PS:` lines |
| Which of a few dozen devices, servers or stores | everything | `generate.py` writes one file per entity; `LIMITS` uses `*` |
| Which of thousands (accounts, users, IPs) | everything | one total series per file; `evidence()` adds the top entities during the incident against before |
| No target in the PS | everything | pick a fixed limit from the healthy data and write why in `PROBLEM.md`; a rolling baseline in `find_incidents()` only if the PS asks |
| A forecast or a trained model | everything | a new step before the pack; its output is one more series, so the page draws it; packages only if the PS forces them (rule 3) |
| Live or real time | everything | a replay route in `app.py` that plays a case step by step |
| Another LLM | everything | `API_URL`, `API_KEY`, `MODEL`; drop the `thinking` line |
| Another output (alert, ticket, scorecard) | everything | the sections in `SYSTEM_PROMPT`; the page renders any Markdown |
| No timeline (screening, matching, chat over documents) | `app.py`, `ask_llm()`, `run()`, the report panel, answer keys | replace `load()` to `build_pack()`, and make `timeline()` return what the page shows instead (a table, not charts); keep the name, since `check.py --timeline` compares any JSON shape |

## At 0:15, for the PS

1. Contracts: rewrite "This sample" in `contracts/README.md` and replace the
   CSVs in `contracts/sample/` with about 30 minutes in the PS's files and
   columns, one planted incident, a decoy and `answer.txt`. Then
   `python3 contracts/check.py contracts/sample` and update `contracts/timeline.json`
   only if the JSON shape must change (it should not).
2. Data lane: `generate.py` from scratch (the only part that cannot be ready).
3. Analysis lane: the `PS:` lines, plus any PS-specific evidence (for example
   client IPs per incident) inside `evidence()`. The function signatures stay.
4. UI lane: the title and any PS-specific panel. `app.py` already serves real
   cases through `analyze.py`.

## Tested on 2026-10-31

The same `analyze.py`, changing only the `PS:` settings:

| Case | Shape | Found |
|---|---|---|
| `contracts/sample` | 30 min, 2 metric files and a log | the incident; DeepSeek named the slow UPDATE and ruled out the decoy scan |
| mock Loghub day | 1,440 min, real Apache log, complaints | both incidents; `db_query_time_ms` 24 to 2,283 |
| IoT | 1 row a second, 3 device files, `STEP` 10 s, `sensors_*.vibration > 5` | the incident; only `dev_02` rises, 1.5 to 25 |
| Retail | per transaction, `STEP` 1 day, `TOTALS`, `amount < 7000` | the incident; `store_3` last seen the day before |

## For the Defend section

- "Was this written before the event?" Yes, this generic skeleton was
  prepared beforehand; the commit history shows it. Everything that is
  specific to the PS (the data, the rules, the prompt, the planted cases) was
  written during the event.
