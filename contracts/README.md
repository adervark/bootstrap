# Contracts

What every lane builds against. `check.py <case_dir>` enforces the CSV part;
`check.py --timeline <case_dir>` also checks `analyze.timeline()` against
`timeline.json`. At 0:15 the main session rewrites "This sample" for the
problem statement; the rules and interfaces below stay.

## Case folder

`data/sessions/<case>/`, and `contracts/sample/` in the same format:

| File | Written by | Read by |
|---|---|---|
| `*.csv`, one per data source | `generate.py` | `analyze.py` |
| `answer.txt`, the planted ground truth | `generate.py` | only `app.py` (`/api/cases`), never `analyze.py` or the LLM |
| `report.md`, the LLM's report plus its evidence | `analyze.py` | `app.py` (`/api/report`) |

CSV rules:

1. The first column is `timestamp`, as `YYYY-MM-DD HH:MM:SS`, local time.
2. The file name is the data source. Letters, digits and `_` only, no dots:
   a series is named `file.column`.
3. A column of numbers (empty cells allowed) is a series. Text columns make
   each row an event, and the file also gets a `file.count` series.
4. IDs are text with an underscore (`dev_01`, `u_123`). A bare number becomes a
   series, and `dev-01` would be grouped with `dev-02` in the evidence.
5. When which entity matters (a device, a server, a store), write one file per
   entity, `sensors_dev_01.csv`, and give the limit as `sensors_*.vibration`.
6. Rows need not be in time order, and steps may have no row (a gap).

## This sample

`contracts/sample/`, 2026-10-31 09:00 to 09:29, one row per minute:

| File | Columns |
|---|---|
| `server.csv` | `timestamp, cpu_pct, memory_pct, db_ms` |
| `web.csv` | `timestamp, users, response_ms` |
| `log.csv` | `timestamp, level, message` |

Planted (`answer.txt`): 09:12 to 09:20 the database slows down (slow
`UPDATE answers`, `db_ms` 20 to 600-900), so pages take over 1 s. The decoy is
a bot scan from 203.0.113.9 at 09:10: its 404s only affect the bot.
`contracts/sample/report.md` is a real report on it (deepseek-flash, 37 s),
which names the cause and rules out the scan.

## analyze.py, as app.py uses it

| Function | Returns |
|---|---|
| `timeline(case_dir)` | dict in the shape of `timeline.json` |
| `run(case_dir)` | the report text; calls the LLM, then writes `report.md` |
| `build_pack(case_dir)` | the evidence pack the LLM gets, as text |

## API (app.py)

| Route | Returns |
|---|---|
| `GET /` | `static/index.html` |
| `GET /api/cases` | `[{"name": "sample", "answer": "..."}]`: `sample` first, then `data/sessions/*` |
| `GET /api/timeline?case=` | `analyze.timeline()`, see below |
| `GET /api/report?case=` | text: the saved `report.md`, or "No report yet. Press Run analysis." |
| `POST /api/analyze?case=` | text: the new report; HTTP 502 with the error when the LLM call fails |

`/api/timeline`, as in `timeline.json`:

- `case`: the folder name.
- `times`: one label per step, `YYYY-MM-DD HH:MM` (with `:SS` when steps are under a minute).
- `limits`: `[{"name", "sign", "value"}]`, one per series with a limit (`*` already expanded); `sign` is `>` or `<`.
- `groups`: `[{"source": file, "series": [{"name": "file.column", "values": [...]}]}]`,
  one value per step, `null` where the file has no row.
- `incidents`: `[{"first", "last"}]`, indexes into `times`, both included.
