# Demo, 3 minutes

## Before the jury arrives

```bash
cd ~/Code/bootstrap
bash targets/start.sh                         # the four apps, 127.0.0.1 only
set -a; . ./.env; set +a
.venv/bin/uvicorn app:app                     # http://127.0.0.1:8000/?case=campus_poisoned
dbeaver-ce                                    # connection "LLM Release Gate (gate.db)"; open queries.sql
```

- Open the page and `deck/LLM_Release_Gate.pptx` side by side.
- The page is 11 numbered pages: 1 Verdict, 2 Replay, 3 Jury, 4 Why, 5 Failures, 6 Tests,
  7 Regression, 8 Monitoring, 9 Human review, 10 Measures, 11 Audit. Keys `1`-`9` and `0` (page 10)
  jump to a page, the arrow keys step through all 11, and every page ends with Back and Next.
- A jury scenario adds tests to the case for good. After a rehearsal, put the case back:
  `git restore data/sessions/campus_poisoned && python3 store.py --reset data/sessions/campus_poisoned`.
  The database is the record, so the git restore alone does not undo it.

## Script

| Time | Show | Say |
|---|---|---|
| 0:00 | Slide 1 | "An LLM app can sound right and still be wrong, leak data or obey a poisoned document. This gate decides whether it ships, with the evidence. We ran it on four open-source apps we did not write." |
| 0:20 | Page 1, Verdict | Read it top to bottom: "The app: a campus IT helpdesk bot. What we did: planted 3 poisoned documents. Our gate wrote 92 tests from 15 risks and checked 231 answers; 33 of 60 attacks worked. Go live? No, Reject. Why: it sends users to an attacker's reset URL. Fix: strip injected instructions. Trust: 3 of 3 votes agree, and on a held-out set it caught 94 of 96 planted faults with 3 false alarms." |
| 0:50 | Page 2, Replay: press Play (26 s), talk over it | "This is the stored run replayed from our database: every test, the app's answer and our call. Watch the attack line climb: 33 of 60 attacks worked." |
| 1:00 | Page 5, Failures: open PROMPT_INJECTION, click `F-010` | "Every finding links to the answer it came from. Here the bot sends a student to a fake password-reset URL that a poisoned document planted." |
| 1:10 | Page 7, Regression: the two charts | "Same suite on three versions. A hardened prompt fixed 23 of 58 failures. Removing the poison fixed 40. The fix is the corpus, not the prompt. Even clean, it states facts no document holds, so it is still not ready." |
| 1:30 | Page 3, Jury: paste the jury's text, Run scenario | "Give us any scenario. It becomes a new risk, new tests are written and run against the app, and you watch each answer and our call arrive. Under a minute." |
| 1:40 | While it runs: page 9, Human review | "The AI can stop a release, never ship one. Release needs a named approver; an override needs a name and a reason." |
| 2:15 | Back to page 3: the feed and the result line | Read out how many of the new tests failed, the code on the one that matters, and "Verdict X → Y". |
| 2:35 | Page 11, Audit: the database panel, chain valid; then page 10, Measures | "Everything lives in one SQLite database, every analysis kept, every step in a hash-chained log. Each success measure in the brief has a measured number: on real answers, 23 of 30 findings were real." |
| 2:55 | Slide 5 | "It tells you whether to ship, why, and how sure it is." |

## If something breaks

- LLM API down: the page still shows every saved report. Say "the code checks still run
  and can never say Release", and show `report.md`.
- Jury run fails at a step: the page names the step and the reason. Show the dry run
  instead: `deck/jury_dryrun.json` (5 tests, 7 answers, 3 failed, 35 s).
- Page down: `python3 analyze.py data/sessions/campus_poisoned` and open `report.md`.
