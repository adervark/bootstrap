# CLAUDE.md for a 4-hour hackathon

The ready repo is `/home/ade/Code/bootstrap`, a git repo with this file as
its `CLAUDE.md`.
The problem statement (PS) arrives at 0:00, and the whole build has 4 hours.
Claude builds in parallel lanes and explains each lane to the user as it
finishes. The user must be able to explain every line to the judges.

These rules override the global oh-my-claudecode rules for this repo:
delegation (the Lanes section replaces it), model routing, separate reviewer
passes and the AA task board.

## Rules

1. Code is written in parallel lanes, one agent per part of the pipeline,
   all in the same repo (see Lanes). The lanes agree only on standard
   outputs, written down first as contracts, and are integrated once at the
   end. The main session writes the contracts, launches the lanes, explains
   each finished lane's files and does the integration. While a lane runs,
   nobody else edits its files. Why: the user chose parallel lanes for speed
   (2026-10-30), and the explanation as each lane finishes is how they still
   understand every line.
2. Work in steps. A step is one runnable file, one change or one finished lane.
   After each step, run it, show the key output, and explain it in at most
   5 bullets per file: what it does, why, and how it connects to the rest.
   Then go on to the next step in the same phase without asking.
3. Standard library first (Python 3.14). Allowed packages: `fastapi`,
   `uvicorn`, plus anything the PS forces. Never use Streamlit, Gradio,
   LangChain, an ORM, or a frontend build step (npm, React, Vite). Why: the
   user ruled out Streamlit, and every package is one more thing to install,
   debug and explain.
4. Ask questions once. At the end of Understand, send one AskUserQuestion
   with up to 4 questions, recommended option first. After that, pick
   sensible defaults and state each choice in one line. Why: every round
   trip costs minutes.
5. Nothing is done until you have run it and shown the output.
6. Keep the API key in `.env` (mode 600, listed in `.gitignore`). Never
   print it or write it into code.
7. Commit at every phase gate and after every finished lane, with a
   one-line message. Why: a known-good point to roll back to
   at 3:45.
8. Deliverables are local files. Never publish Artifacts.

## Clock

Run `date` at 0:00 and write the start time into `PROBLEM.md`. At every
gate, run `date` again and say in one line how far ahead of or behind the
table you are.

| Time | Phase | Done when |
|---|---|---|
| 0:00–0:15 | Understand | `PROBLEM.md` holds the PS word for word plus a checklist of every required output; the data is downloaded and profiled; the pipeline is proposed in at most 10 lines; the user has answered the one question batch |
| 0:15–0:30 | Contracts | `contracts/` is written and committed (see Lanes), and the three lanes are launched |
| 0:30–1:45 | Lanes | each lane has passed its done-when check, and its files are explained and committed |
| 1:45–2:30 | Integrate | on a real case, `python3 analyze.py data/sessions/<case>` writes `report.md` naming the planted ground truth, and `uvicorn app:app` shows that case through `analyze.py`, not the contract samples |
| 2:30–3:00 | Polish | at most 3 polish lanes, each changing one file no other lane touches, explained and committed |
| 3:00–3:30 | Harden | the UI falls back to the cached `report.md`; `README.md` has run steps and the Defend section; one full dry run of the demo |
| 3:30–4:00 | Freeze | no new features; rehearse the demo |

If the end-to-end run is not working by 2:30, stop every lane (TaskStop) and
fix it in the main session. If it still fails at 2:45, drop the UI and demo
the CLI and `report.md` instead. Never skip Harden.

## Opening move, when the PS arrives

The hackathon's theme is "AI for Tech: Campus IT Operations" (user,
2026-10-28), so expect a campus IT system: a portal, LMS, network, labs.

1. Transcribe the PS (often a photo) into `PROBLEM.md`, word for word.
2. Under it, list every required output and every named data field as a
   checklist.
3. Download the data into its own folder under `data/raw/`. Profile it:
   size, time span, columns or levels, top message types, and what is real
   versus what has to be synthesised. Use one read-only agent per data
   source, all launched in one message, while the main session works on the
   checklist. Write the findings under the PS.
4. Propose the pipeline below, adapted to the PS.
5. Ask the one question batch: LLM, demo surface, any story choice.

## Default pipeline for data + AI problems

```
data/raw/<source>/  ->  generate.py  ->  data/sessions/<case>/*.csv  ->  analyze.py  ->  report.md
                                                                             |
                                                        app.py + static/index.html (imports analyze)
```

- `generate.py` loads the real data and makes any synthetic data. It writes
  one file per data source the PS names, so the correlation step is real.
- `analyze.py` merges everything onto one timeline, detects anomalies with
  plain rules (for example 3x the median), builds a short evidence pack per
  anomaly, sends it to the LLM, and writes `report.md` with the evidence
  appended. Write it as functions plus an `if __name__ == "__main__":` block
  from the start, so `app.py` can import it.
- Code does the counting, joining and detection. The LLM only reads the
  evidence pack (at most about 2 pages) and explains it. Why: the code part
  is deterministic and checkable, and LLMs reason well over summaries but
  badly over raw tables.

## Lanes (parallel agents)

Three lanes run at once, one per part of the pipeline. Each lane owns its
files and edits nothing else. The main session owns everything else:
`contracts/`, `PROBLEM.md`, `README.md`, `requirements.txt`, `.gitignore`.

A skeleton that fits any PS exists since 2026-10-31: `analyze.py`, `app.py`,
`static/index.html` and `contracts/` work end to end on `contracts/sample`
(read `ARCHITECTURE.md`). The analysis and ui lanes adapt these files at
their `PS:` lines and add what the PS needs; they never start over or copy
the mock's versions. Why: the skeleton was tested on four data shapes and a
real DeepSeek run.

| Lane | Owns | Builds against | Done when |
|---|---|---|---|
| data | `generate.py`, `data/sessions/` | `data/raw/` and the columns in `contracts/README.md` | `python3 contracts/check.py data/sessions/<case>` passes for every case, and it prints a table showing the planted signals |
| analysis | `analyze.py` and the `report.md` files it writes | `contracts/sample/` | `python3 analyze.py contracts/sample` writes `report.md` naming the sample's planted incident, and `python3 contracts/check.py --timeline contracts/sample` passes |
| ui | `app.py`, `static/index.html` | `contracts/timeline.json`, `contracts/sample/report.md` | `uvicorn app:app` serves the page from the samples, and the headless screenshot shows the chart and the report |

### Contracts (0:15–0:30, main session)

Before any lane starts, write and commit `contracts/`:

- `README.md`: the folder layout, every CSV's file name, columns and units,
  the functions `analyze.py` exposes to `app.py` (for example
  `timeline(case_dir) -> dict` and `run(case_dir) -> str`), and the JSON
  each API route returns.
- `sample/`: one hand-written case folder in the contract's format, about
  30 minutes of rows per CSV with one planted incident, so the analysis lane
  can test its detection before the real data exists.
- `timeline.json`: a hand-written example of what `/api/timeline` returns.
  Its shape is generic, so it should not need to change. `sample/report.md`,
  a real report on the sample, shows what `/api/report` returns; rerun
  `python3 analyze.py contracts/sample` after replacing the sample.
- `check.py` is already in the bootstrap and was tested on 2026-10-30. It
  takes a case folder and fails unless every CSV in `contracts/sample/` is
  there with exactly the same columns, in order. With `--timeline`, it also
  fails unless `analyze.timeline(case_dir)` has the same shape as
  `timeline.json`: the same keys, and numbers where the sample has numbers.
  Only the analysis lane uses `--timeline`. Why: without it, `check.py`
  never imports `analyze.py`, so the data lane cannot trip over a
  half-written file.

Why: lanes that build against the same written contract fit together at the
end; lanes that guess each other's formats do not, and `check.py` catches a
mismatch while the lane is still running. Change a contract after launch
only when you must, and then tell every running lane with SendMessage.

### Launching

- Send all three Agent calls in one message, so they run at once. Each one
  uses `subagent_type: "oh-my-claudecode:executor"` and `model: "opus"`.
  Why: a lane that has to be redone costs more time than the tokens it
  saves.
- Each prompt gives, in this order: the path to `PROBLEM.md`; the files the
  lane owns and "edit nothing else"; the contract files to build against;
  rule 3; the done-when check; "never run git"; the report format.
- All lanes work in the same repo, so `.venv` and `.env` work as they are.
  Run the server as `.venv/bin/uvicorn app:app`; the scripts need only the
  standard library, so `python3` is enough for them. Why: each Bash call
  starts a fresh shell, so an activated venv does not carry over.
  A lane never runs git; the main session commits for it. Why: two agents
  running git at once collide on `.git/index.lock`, and a lane's commit
  could sweep in another lane's half-written file.
- `app.py` already serves every case through `analyze.py`, with
  `contracts/sample` listed as the case `sample`. If `analyze.py` is mid-edit
  and the import fails, the UI lane waits and retries; it never edits
  `analyze.py`.
- Its final report lists the files it changed, how to run them, the output
  of its done-when check, at most 5 bullets per file explaining it, and
  every assumption it made that the contract did not settle.

### Integrating

- As each lane finishes, rerun its done-when check, explain each of its
  files in at most 5 bullets, and commit only the files it owns. The user
  can stop and ask about any line before the commit.
- At 1:45, integrate once: point `app.py`'s two functions at `analyze.py`,
  run `generate.py` and `analyze.py` on a real case, and fix any mismatch in
  the main session. Why: when every lane matched the same contract,
  integration is wiring, not rewriting.
- While lanes run, the main session writes no lane-owned file. It checks
  finished work, relays lane questions, and drafts the README's Defend
  section.

## Lessons from the mock run

The mock lives in `/home/ade/Code/tcsai`. Read its `generate.py`,
`analyze.py` and `report.md` before building anything similar, and reuse
their patterns.

- Profile the full dataset, not only the sample. The GitHub sample was a
  2,000-line selection; the full Zenodo log had a second failure type.
- Every synthetic effect needs a believable cause. In the mock, a bot scan
  at 6 requests a second was made to slow the site, and DeepSeek rejected
  it, rightly. Only errors that affect everyone should drive shared latency.
- Plant the ground truth, write it in `generate.py`'s docstring, fix
  `random.seed`, and check that the report names the planted cause.
- Add at least one decoy, a real and tempting wrong suspect, and make each
  incident need a different data source to solve. Why: that shows the tool
  reasons, instead of echoing the only signal it was given.
- Never cut evidence to a top-N without checking what got cut. In the mock,
  a top-10 cap hid the 4 key log lines and the LLM got that incident wrong.
- "Slow = 3x the median" breaks when the portal is slow for most of the
  data: the median becomes the slow speed. Use a fixed target (pages over
  1 s) unless the PS gives one.
- A given dataset may hold several cases on the same timestamps and an
  answer column (the mock's `scenario`). Split it into one folder per case,
  write the answer only to `answer.txt`, and never let it reach the LLM.
  Show it on the page behind a click, so the judges can score the result.
- Show trends, not only "before vs during" averages. A memory leak is a
  climb while load stays flat; the mock's evidence uses four windows
  (30-15 and 15-0 minutes before, first and last 10 minutes of the incident).
- Make every script take a case folder (`data/sessions/<name>/`) from the
  start. Bolting this on later touched every file in the mock.
- One DeepSeek call with thinking on took 1–2 minutes. Precompute
  `report.md`, and have the UI show the cached report instantly; re-running
  is optional.

## DeepSeek (default LLM)

At 0:00, confirm the key works and see which models exist. Models change:
on 2026-10-29 they were `deepseek-flash` and `deepseek-v4-pro`.

```bash
set -a; . ./.env; set +a
curl -s https://api.deepseek.com/models -H "Authorization: Bearer $DEEPSEEK_API_KEY"
```

Call it with `urllib`, no SDK. This worked in the mock:

```python
def ask_deepseek(text):
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": text}],
        "thinking": {"type": "enabled"},
        "stream": False,
    }
    request = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)["choices"][0]["message"]["content"]
```

A system prompt for the LLM says, in this order: who the model is and what
system it is looking at; what the evidence contains; the report sections
required; and "Use only the evidence given. If the evidence does not settle
something, say so."

## UI (FastAPI + one HTML page)

- `app.py`: `GET /` serves `static/index.html`; `GET /api/timeline` returns
  the chart data as JSON; `GET /api/report` returns the cached `report.md`;
  `POST /api/analyze` reruns the analysis.
- `static/index.html`: plain HTML and JavaScript, Chart.js for the timeline
  with incidents shaded, marked.js to render the report. Load both from
  files in `static/`, not from a CDN. Why: venue Wi-Fi.
- The look is a calm Bloomberg-style terminal (user, 2026-10-29 and
  2026-10-30): a black page, IBM Plex Sans Condensed and IBM Plex Mono from
  `static/fonts/`, white for values, grey for labels. Amber marks only where
  you are, the main button and the line with a limit; red marks only an
  incident; never lemon yellow (use the muted gold `#E8C35A` if a "slow"
  state is needed). One stacked timeline, not many panels. `static/index.html`
  already does this. Why: the user asked for "professional like a bloomberg
  terminal", then said the full version was "too hectic … people dont know
  what to focus on" and "the yellow looks tacky".
- One small chart per metric, grouped by data source, never one chart with
  two y-axes. Force every y-axis to the same width
  (`afterFit: (scale) => { scale.width = 50; }`) so the minutes line up.
- Add one zoom button per incident. Over a whole day an incident is a
  sliver; zoomed in, the judges can see which line moves first.
- Check the page by looking at it: take a headless screenshot and Read the
  PNG. A 200 status does not show that the chart drew.
  `~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome --headless=new --no-sandbox --window-size=1200,1400 --virtual-time-budget=5000 --screenshot=page.png http://127.0.0.1:8000/`
- `app.py` and `static/index.html` already exist and draw any timeline (see
  `ARCHITECTURE.md`): change the title and labels, and do not copy the
  mock's versions.

## Demo and judges

- The demo takes 3 minutes: the problem in one sentence, then the timeline
  with the incidents, then the report: root cause, ruled-out suspects, fix
  and prevention.
- `README.md` has a "Defend" section of likely judge questions, each with a
  one-line answer. Start with: Why is the data synthetic? Why an LLM rather
  than rules? What if the API is down? What would you build next?

## Before Saturday

Done on 2026-10-30 in `/home/ade/Code/bootstrap`:

- [x] This file copied in as `CLAUDE.md`, plus `.gitignore` (`.env`, `.venv/`,
      `__pycache__/`) and `requirements.txt` (fastapi 0.162.0, uvicorn 0.54.0)
- [x] `.venv` made with `uv venv --python 3.14 .venv && uv pip install --python .venv -r requirements.txt`.
      Plain `uv venv` picks Python 3.12, and `python3 -m venv` fails on this
      laptop because Ubuntu leaves out pip
- [x] `.env` (mode 600) with `DEEPSEEK_API_KEY`; the curl above lists
      `deepseek-flash` and `deepseek-v4-pro`
- [x] `static/chart.umd.js` (Chart.js 4.4.1) and `static/marked.min.js`
      (marked 12.0.2), copied from the mock repo
- [x] `contracts/check.py`, tested on passing and failing fake cases
- [x] `data/raw/`, empty, for the PS data
- [x] The mock repo has a working `app.py` and `static/index.html` (2026-10-29)
- [x] The PS-agnostic skeleton (`analyze.py`, `app.py`, `static/index.html`,
      `contracts/`), tested on four data shapes, and `ARCHITECTURE.md` (2026-10-31)
