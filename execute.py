"""Send a case's tests to its target and capture every answer in runs.csv.

Guardrail: any URL whose host is not 127.0.0.1 or localhost is refused before a
request is sent. Redirects and environment proxies are switched off, so a target
cannot bounce the runner to a real external system.

Everything a target returns is untrusted data: it is stored as text, never acted on.

Usage: python3 execute.py <case_dir> [--repeats N]
"""
import argparse
import csv
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Lock

import audit

ACTOR = "execute.py"
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
RUN_COLUMNS = ["timestamp", "run_id", "test_id", "repeat", "answer", "sources", "tools",
               "latency_ms", "tokens", "error"]
MAX_WORKERS = 6
TIMEOUT_SECONDS = 120
MAX_BODY_BYTES = 2_000_000
SAMPLE_ONE_IN = 5  # one test in this many also gets repeats, outside the consistency dimension
# The no-KB agreement check (D8): a factual test's 4 repeats and its rephrase test make 5 samples.
FACTUAL_DIMENSIONS = ("accuracy", "grounding", "completeness")
FACTUAL_REPEATS = 4
PROBE_TEMPERATURE = 0.7  # repeats at temperature 0 are near-identical and would show false agreement

csv.field_size_limit(10_000_000)  # sources hold whole documents


class RefusedTarget(ValueError):
    """The URL is not on this machine, so no request was or will be sent."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


# No proxies, and a redirect becomes an error: the only host reached is the one checked.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def check_url(case_dir, url):
    """Raise RefusedTarget, and audit-log it, unless url is http(s) on this machine."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.hostname not in ALLOWED_HOSTS:
        audit.log(case_dir, ACTOR, "refused_target", url=url, requests_sent=0)
        raise RefusedTarget(f"REFUSED {url!r}: host must be one of {sorted(ALLOWED_HOSTS)}. "
                            "No request was sent.")


def _read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_runs(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, RUN_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _ask(url, prompt, temperature=None):
    """One POST to the target. Every failure comes back in error, never as an exception."""
    start = time.time()
    outcome = {"answer": "", "sources": "[]", "tools": "[]", "tokens": 0, "error": ""}
    body = {"question": prompt}
    if temperature is not None:
        body["temperature"] = temperature
    try:
        request = urllib.request.Request(url, json.dumps(body).encode(),
                                         {"Content-Type": "application/json"})
        with _opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read(MAX_BODY_BYTES))
        if not isinstance(body, dict) or not body.get("answer"):
            raise ValueError("the reply has no answer")
        outcome.update(answer=str(body["answer"]),
                       sources=json.dumps(body.get("sources") or []),
                       tools=json.dumps(body.get("tools") or []),
                       tokens=body.get("tokens") or 0)
    except urllib.error.HTTPError as error:
        outcome["error"] = f"HTTP {error.code}"
    except Exception as error:  # a target can fail in any way; it must never stop the run
        outcome["error"] = f"{type(error).__name__}: {error}"
    outcome["latency_ms"] = round((time.time() - start) * 1000)
    return outcome


def _plan(test, dimension, repeats):
    """(how many times to send a test, the temperature to send, or None for the app's own)."""
    if test["origin"] == "rephrase":
        return 1, PROBE_TEMPERATURE
    if test["should_refuse"] == "no" and dimension in FACTUAL_DIMENSIONS:
        return FACTUAL_REPEATS, PROBE_TEMPERATURE
    if dimension == "consistency" or zlib.crc32(test["test_id"].encode()) % SAMPLE_ONE_IN == 0:
        return repeats, None
    return 1, None


def _check_health(case_dir, url):
    parts = urllib.parse.urlsplit(url)
    health = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/health", "", ""))
    try:
        with _opener.open(health, timeout=10) as response:
            if json.loads(response.read(MAX_BODY_BYTES)).get("ok"):
                return
        problem = "the reply was not ok"
    except Exception as error:
        problem = f"{type(error).__name__}: {error}"
    audit.log(case_dir, ACTOR, "target_down", url=health, problem=problem)
    raise RuntimeError(f"The target is not up at {health}: {problem}")


def run_tests(case_dir, test_ids=None, repeats=3):
    """Run the tests not run yet and append them to runs.csv. Returns how many runs were added."""
    target = json.loads(Path(case_dir, "target.json").read_text(encoding="utf-8"))
    url = target["url"]
    check_url(case_dir, url)
    _check_health(case_dir, url)

    dimensions = {r["risk_id"]: r["dimension"] for r in _read_csv(Path(case_dir, "risks.csv"))}
    tests = _read_csv(Path(case_dir, "tests.csv"))
    if test_ids is not None:
        wanted = set(test_ids)
        # A caller naming a factual test gets its rephrase too, or the test would lack a sample.
        wanted |= {t["test_id"] for t in tests if t["origin"] == "rephrase" and t["parent_test"] in wanted}
        tests = [t for t in tests if t["test_id"] in wanted]

    # A failed or half-written row is not a finished run: a resume retries it.
    runs_path = Path(case_dir, "runs.csv")
    earlier = _read_csv(runs_path)
    finished = [r for r in earlier if r.get("error") == "" and r.get("run_id")]
    if len(finished) != len(earlier):
        audit.log(case_dir, ACTOR, "retrying_failed_runs", count=len(earlier) - len(finished),
                  errors=sorted({r.get("error") or "half-written row" for r in earlier
                                 if r not in finished}))
    if len(finished) != len(earlier) or not runs_path.exists() or not runs_path.stat().st_size:
        _write_runs(runs_path, finished)

    done = {(r["test_id"], r["repeat"]) for r in finished}
    numbers = [int(r["run_id"].split("-")[1]) for r in earlier if r.get("run_id")]
    next_number = max(numbers, default=0) + 1
    planned = []
    for test in tests:
        count, temperature = _plan(test, dimensions.get(test["risk_id"]), repeats)
        planned += [(test, repeat, temperature) for repeat in range(1, count + 1)]
    pairs = [plan for plan in planned if (plan[0]["test_id"], str(plan[1])) not in done]
    skipped = len(planned) - len(pairs)
    # A target that handles one request at a time sets max_concurrency to 1 in target.json.
    # Otherwise time spent queueing inside it is recorded as its latency.
    workers = max(1, min(int(target.get("max_concurrency") or MAX_WORKERS), MAX_WORKERS))
    audit.log(case_dir, ACTOR, "run_started", url=url, to_run=len(pairs), skipped=skipped,
              repeats=repeats, workers=workers, probe_temperature=PROBE_TEMPERATURE,
              at_probe_temperature=sum(1 for plan in pairs if plan[2] is not None))

    lock = Lock()
    errors = [0]
    with open(runs_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, RUN_COLUMNS)

        def run_one(pair):
            nonlocal next_number
            test, repeat, temperature = pair
            outcome = _ask(url, test["prompt"], temperature)
            with lock:
                run_id = f"R-{next_number:03d}"
                next_number += 1
                writer.writerow({"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                 "run_id": run_id, "test_id": test["test_id"], "repeat": repeat,
                                 **outcome})
                f.flush()
                if outcome["error"]:
                    errors[0] += 1
                    audit.log(case_dir, ACTOR, "run_error", run_id=run_id,
                              test_id=test["test_id"], error=outcome["error"])

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(run_one, pairs))

    digest = hashlib.sha256(runs_path.read_bytes()).hexdigest()
    audit.log(case_dir, ACTOR, "run_finished", added=len(pairs), skipped=skipped, errors=errors[0],
              runs_csv_sha256=digest)
    print(f"{case_dir}: {len(pairs)} runs added, {skipped} already done and skipped, {errors[0]} errors")
    return len(pairs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a case's tests against its local target")
    parser.add_argument("case_dir")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    try:
        run_tests(args.case_dir, repeats=max(1, args.repeats))
    except (RefusedTarget, RuntimeError) as error:
        raise SystemExit(str(error))
