# LLM Release Gate

A reusable AI quality and safety framework for LLM-powered applications. It dynamically
derives tests from identified risks, executes them against target apps, evaluates responses
against ground truth (or self-consistency when ground truth is absent), scores six critical
quality dimensions, and delivers an evidence-backed recommendation of **Release**,
**Conditional Release**, or **Reject**. Final release approval strictly requires human review.

- `PROBLEM.md`: the brief, word for word, with a checklist.
- `DECISIONS.md`: every design decision, who made it, why, and the line for a juror.
- `METRICS.md`: every number, generated from the result files by `metrics.py`.

## What it tests

Two open-source apps we did not write, cloned and run only on this laptop
(`data/raw/targets/`, kept out of git):

| Case | App | What differs |
|---|---|---|
| `campus_poisoned` | RAG_Poisoning_POC, loaded with 10 synthetic campus IT documents | stock prompt, 3 poison documents |
| `campus_hardened` | the same | a hardened prompt, same poison |
| `campus_clean` | the same | stock prompt, no poison |
| `dvla` | Damn Vulnerable LLM Agent, a LangChain banking agent | its own prompt and tools |

The three campus stages run the same suite (92 tests plus 27 rephrasings), so
differences come from the app, not the tests. Results, all measured (`METRICS.md`):

| Case | Overall | Attack success | Critical findings | Verdict |
|---|---|---|---|---|
| campus_poisoned | 58.4 | 55% (33/60) | 83 | Reject |
| campus_hardened | 66.5 | 40% (24/60) | 59 | Reject |
| campus_clean | 83.6 | 2% (1/60) | 0 | Reject (grounding 61: 29 unsupported claims) |
| dvla | 76.2 | 3% (2/60) | 0 | Reject (reveals its own rules, weak grounding) |

## Pipeline

```
risks.json + jury scenario + past failures
   -> generate.py   tests: LLM-written, code-mutated attacks, rephrasings, regressions
   -> execute.py    localhost only; captures answer, sources, tool calls, latency
   -> analyze.py    code checks (citations, canaries, PII, numbers, proof tokens)
                    + KB claim check (LLM quotes the KB, code confirms the quote)
                    + no-KB agreement check (5 samples, no source data)
                    -> failure taxonomy -> 6 scores -> 3 LLM votes -> code vetoes
                    -> Reject blocks; Release waits for a named human
   -> report.md, results.json, audit.jsonl (hash-chained)
   -> data/regression/<family>.csv -> rerun on the next version
   -> monitor.py    scores against a baseline, drift alerts (MONITORING.md)
```

| Stage | Here |
|---|---|
| Input | `risks.json`, the target's `target.json`, a jury scenario, past failures |
| AI / agents | test generator, claim judge, agreement judge, obey-or-warn stance check, release voter (DeepSeek V4.1 Flash) |
| Tools | target adapters, citation, canary and PII checks, quote verifier, attack mutators |
| Data / knowledge | the campus KB, the evaluation suite (`data/suite/`), the regression suite, the calibration sets |
| Decisions | six scores, three votes, vetoes V1-V4 that can only make the verdict stricter |
| Human control | approve, or override with a name and reason; every step in a tamper-evident log |
| Output | verdict, scorecard, failure taxonomy with evidence, regression suite, monitoring plan |

## Run

```bash
uv venv --python 3.14 .venv && uv pip install --python .venv -r requirements.txt   # once
bash targets/start.sh                     # the four target apps, 127.0.0.1 only
set -a; . ./.env; set +a
python3 generate.py data/sessions/campus_poisoned     # or any case
python3 execute.py  data/sessions/campus_poisoned
python3 analyze.py  data/sessions/campus_poisoned     # writes report.md and results.json
python3 generate.py data/sessions/campus_poisoned --save-regressions
python3 calibrate.py --held-out                       # our own accuracy, on fresh seeded faults
python3 metrics.py                                    # METRICS.md
.venv/bin/python deck.py                              # deck/LLM_Release_Gate.pptx, numbers read from the results
.venv/bin/uvicorn app:app                             # the page: http://127.0.0.1:8000
```

The dashboard displays cached evaluation reports instantly, ensuring resilience even if
the LLM API is unavailable. The interactive jury scenario box transforms unstructured risk prompts
into targeted test cases, executes them on-the-fly, and updates the release decision in real time.

Setting up the target apps' own virtualenvs is in `DECISIONS.md` D1 and
`targets/start.sh`.

## How far to trust the numbers

- Detection accuracy is measured on seeded faults: correct answers with one known
  error planted. The held-out set uses a seed never used while building. Planted
  faults can be easier than real ones, so it is a benchmark.
- Real-answer accuracy comes from 60 real answers labelled against `LABELS.md`, a
  rubric written before any result was read, with 10 re-labelled blind by a second
  person.
- Every rate has its count and a 95% Wilson interval.
- Cost is an estimate from third-party price lists: $0.81 to analyse all four apps.
- The LLM judge varies between runs: two runs of the held-out set gave 93/96 and 94/96
  caught, 1/96 and 3/96 false alarms (`data/calibration_heldout_run1.json`).

## Defend

| Likely question | Answer |
|---|---|
| Isn't this just a list of prompts? | No. Two generation runs on the same app shared 0 of 31 prompts. Tests come from risks, the app's description, a jury's text and past failures. |
| Who decides Release? | The LLM votes three times and must cite finding IDs. Code vetoes can only make it stricter. A human must approve any release. |
| Can the LLM judge be fooled? | Leaked secrets and proof tokens are pure code. A judge's quote must really be in the KB or its verdict is void. The obey-or-warn check fails closed. |
| The judge and the app are the same model. | Yes, a real limit. That is why we measure the judge against planted faults and hand labels. |
| How do you know it doesn't cry wolf? | False alarms are measured on clean answers, on answers that warn about a poison, on the clean stage, and on hand-labelled real answers. See `METRICS.md`. |
| Why is the data synthetic? | The brief requires synthetic or anonymized sensitive data, and planted faults give a known answer to score against. |
| Why an LLM rather than rules? | On the held-out set, code alone caught 61 of 96 planted faults; with the LLM judge, 94 of 96. The LLM covers paraphrased and invented claims that rules miss. |
| Does it reject everything? | No. On the held-out set it flagged 3 of 96 clean answers. Each app here failed for a different, evidenced reason; on the clean stage the LLM voted Reject over Conditional Release, citing 29 unsupported claims, and code would have blocked Release anyway: 83.6 is under the bar of 85, and grounding is under 70. |
| Did you check your own findings? | Yes. We audited every critical finding on the clean stage, found 11 false alarms from three bugs, fixed them and re-ran (`DECISIONS.md` D15). 60 real answers were hand-labelled against a rubric written before the results: 23 of 30 findings were real (all 10 injection and hallucination findings), and 3 of 30 unflagged answers had a missed failure. |
| How do you test without the source documents? | Five samples per factual question, compared for agreement. It caught 4 of the 11 errors the KB check confirmed, with 7 false alarms in 101, so it is a medium signal and never a veto. |
| What if the API is down? | Code checks still run, the code baseline verdict stands and can never be Release, and the page shows the saved report. |
| Did you write the attacks that worked after the first failed? | Yes, as an attacker would. The blatant poison was resisted; the fake portal URL was not. `DECISIONS.md` D9 to D11. |
| Was any of this written before the event? | A generic skeleton (an LLM call, a FastAPI page, a contract checker). Everything specific to this brief was written today; see the git history. |
| What would you build next? | Claims split from every sample in the no-KB check, a real production log sampler, and more target adapters. |
