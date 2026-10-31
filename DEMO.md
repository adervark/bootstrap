# Demo, 3 minutes

## Before the jury arrives

```bash
cd ~/Code/bootstrap
bash targets/start.sh                         # the four apps, 127.0.0.1 only
set -a; . ./.env; set +a
.venv/bin/uvicorn app:app                     # http://127.0.0.1:8000/?case=campus_poisoned
```

- Open the page and `deck/LLM_Release_Gate.pptx` side by side.
- A jury scenario adds tests to the case for good. After a rehearsal, put the case back:
  `git restore data/sessions/campus_poisoned`.

## Script

| Time | Show | Say |
|---|---|---|
| 0:00 | Slide 1 | "An LLM app can sound right and still be wrong, leak data or obey a poisoned document. This gate decides whether it ships, with the evidence. We ran it on four open-source apps we did not write." |
| 0:20 | Page, case `campus_poisoned`, Verdict | "Reject. The LLM voted Reject three times, citing finding IDs, and code agrees: two vetoes fired. Grounding 15.8, security 26.7." |
| 0:40 | Click `F-011` in Why | "Every claim links to the answer it came from. Here the bot sends a student to a fake password-reset URL that a poisoned document planted." |
| 1:00 | Before / After | "Same suite on three versions. A hardened prompt fixed 24 of 59 failures. Removing the poison fixed 42. The fix is the corpus, not the prompt. Even clean, it states facts no document holds, so it is still not ready." |
| 1:30 | Jury Scenario: paste the jury's text, Run scenario | "Give us any scenario. It becomes a new risk, new tests are written, they run against the app, and the verdict is re-decided. About 35 seconds." |
| 1:40 | While it runs: Human Review | "The AI can stop a release, never ship one. Release needs a named approver; an override needs a name and a reason." |
| 2:15 | Jury result: new tests and their findings | Read out how many of the new tests failed and the finding that matters. |
| 2:35 | Audit & Report: chain valid; Calibration line | "Every step is in a hash-chained log. On fresh planted faults it caught 94 of 96 with 3 false alarms in 96; on real answers, 23 of 30 findings were real, and every injection and hallucination finding was." |
| 2:55 | Slide 5 | "It tells you whether to ship, why, and how sure it is." |

## If something breaks

- LLM API down: the page still shows every saved report. Say "the code checks still run
  and can never say Release", and show `report.md`.
- Jury run fails at a step: the page names the step and the reason. Show the dry run
  instead: `deck/jury_dryrun.json` (5 tests, 7 answers, 3 failed, 35 s).
- Page down: `python3 analyze.py data/sessions/campus_poisoned` and open `report.md`.
