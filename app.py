"""Web server for the LLM release gate: one page, and the JSON it draws from analyze.py.

Run from the repo root:
  .venv/bin/uvicorn app:app --port 8000
then open http://127.0.0.1:8000

generate, execute, analyze and audit are imported inside the routes, so the page
still loads when one of them is broken: the sample falls back to
contracts/timeline.json and every other route reports the error.
"""
import base64
import csv
import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

SESSIONS = Path("data/sessions")
PAGE = Path("static/index.html")
SAMPLE_TIMELINE = Path("contracts/timeline.json")
SCENARIO_LIMIT = 2000
NAME_LIMIT = 100
REASON_LIMIT = 1000
STEPS = ["mapping to risk", "generating tests", "executing", "verifying", "deciding"]
JOBS = {}  # job id -> what /api/job returns; lost on restart, which the page reports
BUSY = {}  # case -> job id, or "analysis": at most one writer per case folder
BUSY_LOCK = threading.Lock()

csv.field_size_limit(10_000_000)  # a run's sources column holds whole documents

# The llm.py key comes from .env, so the plain uvicorn command above is enough.
if Path(".env").exists():
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        key, equals, value = line.partition("=")
        if equals and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))

app = FastAPI(title="LLM Release Gate")
app.mount("/static", StaticFiles(directory="static"), name="static")


class Scenario(BaseModel):
    text: str


class Approval(BaseModel):
    name: str
    reason: str = ""
    action: str


def cases():
    """Every case the page can show, name -> folder: the contract sample, then
    each folder in data/sessions/ (.DS_Store and a lane's _scratch are not cases)."""
    found = {"sample": Path("contracts/sample")}
    if SESSIONS.is_dir():
        for folder_path in sorted(SESSIONS.iterdir()):
            if folder_path.is_dir() and not folder_path.name.startswith((".", "_")):
                found[folder_path.name] = folder_path
    return found


def folder(case):
    """The case's folder. Only listed names are accepted, so a request cannot
    reach files outside the case folders."""
    found = cases()
    if case not in found:
        raise HTTPException(404, f"no case {case!r}")
    return found[case]


def clean(error):
    """An exception as text for the page: short, and never holding the API key."""
    text = str(error) or type(error).__name__
    key = os.environ.get("DEEPSEEK_API_KEY")
    return (text.replace(key, "***") if key else text)[:600]


def read_rows(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_target(path):
    target = path / "target.json"
    return json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}


def parse_list(text):
    """A run's sources or tools column. Unreadable JSON is shown as raw text, not hidden."""
    try:
        parsed = json.loads(text or "[]")
        return parsed if isinstance(parsed, list) else [{"id": "(not a list)", "text": str(text)}]
    except json.JSONDecodeError:
        return [{"id": "(unreadable)", "text": text, "name": "(unreadable)", "output": text}]


def claim(case, holder):
    with BUSY_LOCK:
        if case in BUSY:
            raise HTTPException(409, f"{case} is busy with {BUSY[case]}. Wait for it to finish.")
        BUSY[case] = holder


def release(case):
    with BUSY_LOCK:
        BUSY.pop(case, None)


@app.get("/")
def page():
    """The page, with a Content-Security-Policy that allows only its own inline
    script by hash. So even if target text ever reached the HTML, an onerror or a
    <script> in it would not run: the second lock behind textContent."""
    html = PAGE.read_text(encoding="utf-8")
    hashes = " ".join(
        "'sha256-" + base64.b64encode(hashlib.sha256(script.encode()).digest()).decode() + "'"
        for script in re.findall(r"<script>(.*?)</script>", html, re.S))
    policy = (f"default-src 'none'; script-src 'self' {hashes}; style-src 'self' 'unsafe-inline'; "
              "font-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; "
              "form-action 'none'; frame-ancestors 'none'")
    return HTMLResponse(html, headers={"Content-Security-Policy": policy,
                                       "X-Content-Type-Options": "nosniff"})


@app.get("/api/cases")
def list_cases():
    """Every case with its answer key, which the page keeps hidden until asked.
    "analyzed" is extra to the contract: it picks the case the page opens on."""
    result = []
    for name, path in cases().items():
        answer = path / "answer.txt"
        result.append({"name": name, "answer": answer.read_text(encoding="utf-8").strip()
                       if answer.exists() else "No answer key for this case.",
                       "analyzed": (path / "results.json").exists()})
    return result


@app.get("/api/timeline")
def get_timeline(case: str):
    """Everything the page shows: see analyze.timeline() and contracts/timeline.json.
    The sample falls back to the contract's file, and says so in "offline"."""
    path = folder(case)
    try:
        import analyze
        result = analyze.timeline(path)
        if "scorecard" not in result:
            raise ValueError("analyze.timeline does not return the contract's shape yet")
        return result
    except Exception as error:
        if case != "sample":
            raise HTTPException(503, f"analyze.timeline failed: {clean(error)}")
        return {**json.loads(SAMPLE_TIMELINE.read_text(encoding="utf-8")),
                "offline": f"analyze.timeline failed: {clean(error)}"}


@app.get("/api/evidence")
def get_evidence(case: str, test: str):
    """One test's full trace, from the case's raw files rather than the summary: the
    test, its risk and lineage, every captured answer, and each retrieved source
    marked in_kb or not. The KB is the framework's copy (target.json), so a source
    the target retrieved that is not in it is a poison document. "samples" are the
    answers the no-KB check compares (D8): the test's repeats plus its rephrase test.
    "outside_parent" is a parent in another case, as regression tests have. Not in the
    contract's API table: added because timeline.json has no source text."""
    path = folder(case)
    tests = {row["test_id"]: row for row in read_rows(path / "tests.csv")}
    if test not in tests:
        raise HTTPException(404, f"no test {test!r} in {case}")
    target = read_target(path)
    kb_ids = {doc["id"] for doc in target.get("kb", [])}
    all_runs = read_rows(path / "runs.csv")
    runs = []
    for row in all_runs:
        if row["test_id"] == test:
            sources = [{**source, "in_kb": source.get("id") in kb_ids if kb_ids else None}
                       for source in parse_list(row["sources"])]
            runs.append({**row, "sources": sources, "tools": parse_list(row["tools"])})
    lineage, seen = [test], {test}
    while (parent := tests[lineage[0]]["parent_test"]) in tests and parent not in seen:
        lineage.insert(0, parent)
        seen.add(parent)
    outside = tests[lineage[0]]["parent_test"]
    base = tests[test]["parent_test"] if tests[test]["origin"] == "rephrase" and tests[test]["parent_test"] in tests else test
    sampled = {base} | {t for t, row in tests.items() if row["origin"] == "rephrase" and row["parent_test"] == base}
    risk_id = tests[test]["risk_id"]
    return {"test": tests[test],
            "risk": next((r for r in read_rows(path / "risks.csv") if r["risk_id"] == risk_id), {}),
            "runs": runs,
            "samples": [{**{k: row[k] for k in ("timestamp", "run_id", "test_id", "repeat", "answer", "latency_ms", "tokens", "error")},
                         "origin": tests[row["test_id"]]["origin"], "prompt": tests[row["test_id"]]["prompt"]}
                        for row in all_runs if row["test_id"] in sampled],
            "lineage": lineage,
            "outside_parent": "" if outside in tests else outside,
            "children": [t for t, row in tests.items() if row["parent_test"] == test],
            "canaries": target.get("canaries", [])}


@app.get("/api/report", response_class=PlainTextResponse)
def get_report(case: str):
    """The last saved report, so the page shows something at once, even offline."""
    path = folder(case) / "report.md"
    return path.read_text(encoding="utf-8") if path.exists() else "No report yet. Press Run analysis."


@app.post("/api/analyze", response_class=PlainTextResponse)
def run_analysis(case: str):
    """Ask the LLM again and return the new report. FastAPI runs a plain def in a
    worker thread, so the server keeps answering meanwhile."""
    path = folder(case)
    claim(case, "analysis")
    try:
        import analyze
        return analyze.run(path)
    except Exception as error:  # no key, no network, API down: the page keeps the saved report
        raise HTTPException(502, f"analysis failed: {clean(error)}")
    finally:
        release(case)


def watch(job, path):
    """add_scenario and analyze.run each cover two steps and report nothing on the
    way, so the step and the progress count are read from the files they write."""
    while job["state"] == "running":
        try:
            if job["step"] == "mapping to risk" and len(read_rows(path / "risks.csv")) > job["_risks"]:
                job["step"], job["detail"] = "generating tests", "Risk added; writing tests for it."
            elif job["step"] == "executing":
                import audit
                captured = sum(row["test_id"] in job["tests"] for row in read_rows(path / "runs.csv"))
                # execute.py decides the repeats per test and logs the total it will run.
                planned = [entry["details"].get("to_run") for entry in audit.read(path)[job["_audit"]:]
                           if entry["action"] == "run_started"]
                job["detail"] = f"{captured} of {planned[-1]} answers captured." if planned \
                    else f"{captured} answers captured."
            elif job["step"] == "verifying":
                import audit
                if any(re.search("vote|decid|decision|verdict", entry["action"], re.I)
                       for entry in audit.read(path)[job["_audit"]:]):
                    job["step"], job["detail"] = "deciding", "Three LLM votes, then the code's vetoes."
        except (OSError, ValueError, KeyError, csv.Error):
            pass  # a file caught mid-write: read it on the next pass
        job["elapsed_s"] = round(time.time() - job["_start"])
        time.sleep(0.4)
    job["elapsed_s"] = round(time.time() - job["_start"])


def run_scenario(job, case, path, text):
    """The jury's text through the whole pipeline. Any failure ends the job as
    "failed" at the step it happened in, with the reason, and never silently."""
    try:
        import audit
        import execute
        import generate
        import analyze

        job["_risks"] = len(read_rows(path / "risks.csv"))
        job["_audit"] = len(audit.read(path))
        threading.Thread(target=watch, args=(job, path), daemon=True).start()

        job["tests"] = generate.add_scenario(path, text)
        if not job["tests"]:
            raise RuntimeError("the generator returned no tests for this scenario")
        job["step"], job["detail"] = "executing", f"Running {len(job['tests'])} new tests."
        added = execute.run_tests(path, job["tests"])
        new = [row for row in read_rows(path / "runs.csv") if row["test_id"] in job["tests"]]
        if not added and not new:
            raise RuntimeError("no answers captured. Is the target running?")
        failed = [row for row in new if row["error"]]
        if len(failed) == len(new):
            raise RuntimeError(f"every call to the target failed. First error: {failed[0]['error']}")
        job["step"], job["detail"] = "verifying", f"Checking {len(new)} answers."
        analyze.run(path)
        job["step"], job["detail"] = "deciding", f"{len(job['tests'])} new tests, {len(new)} answers."
        job["state"] = "done"
    except Exception as error:
        job["detail"], job["state"] = clean(error), "failed"
    finally:
        release(case)


@app.post("/api/scenario")
def start_scenario(case: str, body: Scenario):
    path = folder(case)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "The scenario text is empty.")
    if len(text) > SCENARIO_LIMIT:
        raise HTTPException(400, f"The scenario is {len(text)} characters; the limit is {SCENARIO_LIMIT}.")
    if case == "sample":
        raise HTTPException(400, "sample is a fixed offline fixture with no target behind it. "
                                 "Choose a real case to run a jury scenario.")
    job_id = uuid.uuid4().hex[:12]
    claim(case, f"job {job_id}")
    job = {"state": "running", "step": STEPS[0], "detail": "Reading the scenario.", "steps": STEPS,
           "case": case, "tests": [], "elapsed_s": 0, "_start": time.time()}
    JOBS[job_id] = job
    threading.Thread(target=run_scenario, args=(job, case, path, text), daemon=True).start()
    return {"job": job_id}


@app.get("/api/job")
def get_job(id: str):
    if id not in JOBS:
        raise HTTPException(404, f"no job {id!r}. Was the server restarted?")
    return {k: v for k, v in JOBS[id].items() if not k.startswith("_")}


@app.post("/api/approve")
def approve(case: str, body: Approval):
    """A human's decision. Here only the request's shape is checked: the D7 rules live
    in analyze.approve, which also logs each refusal, and its reason is shown as a 400."""
    path = folder(case)
    if body.action not in ("approve", "override"):
        raise HTTPException(400, f"action must be approve or override, not {body.action[:40]!r}.")
    if len(body.name) > NAME_LIMIT or len(body.reason) > REASON_LIMIT:
        raise HTTPException(400, f"Name is limited to {NAME_LIMIT} characters, reason to {REASON_LIMIT}.")
    claim(case, "a human decision")
    try:
        import analyze
        return analyze.approve(path, body.name, body.reason, body.action)
    except ValueError as error:  # analyze.approve refusing the request
        raise HTTPException(400, clean(error))
    except Exception as error:
        raise HTTPException(503, f"analyze.approve failed: {clean(error)}")
    finally:
        release(case)


@app.get("/api/audit")
def get_audit(case: str):
    """The log and whether its hash chain holds. A log too damaged to read counts
    as invalid: it is reported, not raised."""
    path = folder(case)
    try:
        import audit
        valid, where = audit.verify(path)
        return {"valid": valid, "entries": audit.read(path), "broken_at": None if valid else where}
    except Exception as error:
        return {"valid": False, "entries": [], "broken_at": None, "error": clean(error)}


@app.get("/api/calibration")
def get_calibration():
    path = Path("data/calibration.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
