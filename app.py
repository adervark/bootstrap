"""Web server for the analysis: one page, and the JSON it draws from analyze.py.

Run from the repo root:
  set -a; . ./.env; set +a; .venv/bin/uvicorn app:app
then open http://127.0.0.1:8000
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

import analyze

SESSIONS = Path("data/sessions")
app = FastAPI(title="Root-cause analysis")
app.mount("/static", StaticFiles(directory="static"), name="static")


def cases():
    """Every case the page can show, name -> folder: the contract sample, then
    each folder in data/sessions/ (hidden ones like .DS_Store are not cases)."""
    found = {"sample": Path("contracts/sample")}
    if SESSIONS.is_dir():
        for folder in sorted(SESSIONS.iterdir()):
            if folder.is_dir() and not folder.name.startswith("."):
                found[folder.name] = folder
    return found


def folder(case):
    """The case's folder. Only listed names are accepted, so a request cannot
    reach files outside the case folders."""
    found = cases()
    if case not in found:
        raise HTTPException(404, f"no case {case!r}")
    return found[case]


@app.get("/")
def page():
    return FileResponse("static/index.html")


@app.get("/api/cases")
def list_cases():
    """Every case with its answer key, which the page keeps hidden until asked."""
    result = []
    for name, path in cases().items():
        answer = path / "answer.txt"
        result.append({"name": name, "answer": answer.read_text(encoding="utf-8").strip()
                       if answer.exists() else "No answer key for this case."})
    return result


@app.get("/api/timeline")
def get_timeline(case: str):
    """Everything the charts need: see analyze.timeline() and contracts/timeline.json."""
    return analyze.timeline(folder(case))


@app.get("/api/report", response_class=PlainTextResponse)
def get_report(case: str):
    """The last saved report, so the page shows something at once, even offline."""
    path = folder(case) / "report.md"
    return path.read_text(encoding="utf-8") if path.exists() else "No report yet. Press Run analysis."


@app.post("/api/analyze", response_class=PlainTextResponse)
def run_analysis(case: str):
    """Ask the LLM again (1-2 minutes) and return the new report. FastAPI runs a
    plain def in a worker thread, so the server keeps answering meanwhile."""
    path = folder(case)
    try:
        return analyze.run(path)
    except Exception as error:  # no key, no network, API down: the page keeps the saved report
        raise HTTPException(502, f"analysis failed: {error}")
