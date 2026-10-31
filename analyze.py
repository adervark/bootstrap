"""Find incidents in one case folder and explain them with an LLM (DeepSeek).

A case is a folder, data/sessions/<case>/ or contracts/sample/, of CSV files
whose first column is `timestamp` (2026-10-31 09:00:00). The file name is the
data source. In each file
  - a column of numbers (empty cells allowed) is a series, e.g. cpu_pct, amount;
  - the text columns, if any, make each row an event, e.g. a log line, a
    complaint, a transaction's store, and the file also gets a count per step.
So write IDs as text (u123, not 123), or they become a series.
For one case:
  a. put every file on one timeline, one value per step   load()
  b. find incidents: runs of steps that break a limit     find_incidents()
  c. build a short evidence pack per incident             build_pack()
  d. send it to the LLM                                   ask_llm()
  e. save its report, plus the evidence, as report.md     run()
timeline() gives app.py the same timeline as JSON for the charts.
Every line to change for a new problem statement is marked "PS:".

Run: set -a; . ./.env; set +a; python3 analyze.py <case_dir> ...
     python3 analyze.py --pack <case_dir> ...   (print the evidence only, no LLM)
"""
import csv
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from fnmatch import fnmatchcase
from pathlib import Path
from statistics import mean

API_URL = "https://api.deepseek.com/chat/completions"  # any OpenAI-style chat API works
API_KEY = "DEEPSEEK_API_KEY"  # the variable in .env that holds the key
MODEL = "deepseek-flash"  # or "deepseek-v4-pro": slower, stronger
STEP = timedelta(minutes=1)  # PS: one point per step, e.g. seconds=10, hours=1, days=1
# PS: a step is bad when any series breaks its limit. Series are named
# "file.column"; a file with text also gets "file.count", its rows per step.
# A name may use * to cover many files, e.g. "sensors_*.vibration".
LIMITS = {"web.response_ms": (">", 1000)}
TOTALS = set()  # PS: series added up within a step instead of averaged, e.g. {"sales.amount"}
GAP = 2  # at most this many normal steps between bad ones: still one incident
LEAD = 5  # events from this many steps before an incident are evidence too
KINDS = 40  # event kinds listed per file and incident; the pack says what it left out
EPOCH = datetime(2000, 1, 1)  # steps are counted from here, so a day step starts at midnight

# PS: the first paragraph says what system this is; the sections are what the PS asks for.
SYSTEM_PROMPT = """You investigate incidents in a web application: a web server in front
of an app server and a database, used by a few hundred people at once.

You get evidence for each incident in one case. Every series (named
file.column) is averaged over four windows: 30-15 and 15-0 steps before the
incident, and its first and last 10 steps, so you can see what changed first
and what keeps changing. Then come the event rows (logs, complaints, ...) from
just before and during the incident, grouped when they differ only in numbers:
each group gives its count, when it was first and last seen, and one example.

Write an incident report in Markdown with these sections:
1. Summary: two or three sentences, starting with the impact: who was
   affected, for how long, and how badly.
2. Timeline: one line per incident.
3. Root cause: one part per incident, headed "### Incident n", that opens with
   "**Cause:**" and one sentence, then gives the exact evidence for it, then
   one bullet per other suspect in the evidence that starts with its name in
   bold and says whether the evidence rules it out and why.
4. Resolution: what to do now, the step that helps most first.
5. Prevention: what to change so it does not happen again.
Use only the evidence given. If the evidence does not settle something, say so."""


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_number(text):
    try:
        float(text)
        return True
    except ValueError:
        return False


def parse(stamp):
    return datetime.fromisoformat(stamp).replace(tzinfo=None)  # all times are local


def step_of(t):
    """The start of the step a time falls in."""
    return t - (t - EPOCH) % STEP


def label(t):
    """A step as text: to the minute, or to the second when steps are shorter."""
    return f"{t:%Y-%m-%d %H:%M:%S}" if STEP < timedelta(minutes=1) else f"{t:%Y-%m-%d %H:%M}"


def load(case_dir):
    """a. Read every CSV in the case folder onto one timeline.

    Returns (times, series, events):
      times   the start of every step from the first timestamp to the last
      series  {"file.column": one number per step, None where the file has no row}
      events  {"file": [(time, text), ...]} for each file with text, in time order
    """
    files = {path.stem: read(path) for path in sorted(Path(case_dir).glob("*.csv"))}
    steps = {step_of(parse(row["timestamp"])) for rows in files.values() for row in rows}
    if not steps:
        raise ValueError(f"{case_dir} has no CSV rows")
    times = [min(steps)]
    while times[-1] < max(steps):
        times.append(times[-1] + STEP)
    index = {t: i for i, t in enumerate(times)}

    series, events = {}, {}
    for name, rows in files.items():
        columns = [c for c in (rows[0] if rows else {}) if c != "timestamp"]
        numeric = [c for c in columns if all(row[c] == "" or is_number(row[c]) for row in rows)]
        for column in numeric:
            cells = [[] for _ in times]  # the numbers that fall in each step
            for row in rows:
                if row[column] != "":
                    cells[index[step_of(parse(row["timestamp"]))]].append(float(row[column]))
            if f"{name}.{column}" in TOTALS:
                series[f"{name}.{column}"] = [sum(c) for c in cells]  # no rows: 0
            else:
                series[f"{name}.{column}"] = [mean(c) if c else None for c in cells]  # no rows: a gap
        text = [c for c in columns if c not in numeric]
        if text or not columns:  # a file of bare timestamps is events too
            events[name] = sorted((parse(row["timestamp"]), " | ".join(row[c] or "" for c in text))
                                  for row in rows)
            counts = Counter(index[step_of(t)] for t, _ in events[name])
            series[f"{name}.count"] = [counts[i] for i in range(len(times))]
    return times, series, events


def broken(value, rule):
    """Does one value break its limit? A rule is (">", 1000) or ("<", 5)."""
    sign, limit = rule
    return value is not None and (value > limit if sign == ">" else value < limit)


def rules(series):
    """LIMITS for this case's series, with each * pattern expanded to the names it matches."""
    missing = [p for p in LIMITS if not any(fnmatchcase(name, p) for name in series)]
    if missing:
        raise KeyError(f"LIMITS names {missing}, but the case has {sorted(series)}")
    return {name: rule for pattern, rule in LIMITS.items()
            for name in series if fnmatchcase(name, pattern)}


def find_incidents(series):
    """b. Bad steps (any series past its limit), joined into incidents [first, last]."""
    limits = rules(series)
    incidents = []
    for i in range(len(next(iter(series.values())))):  # every series has one value per step
        if not any(broken(series[name][i], rule) for name, rule in limits.items()):
            continue
        if incidents and i - incidents[-1][1] <= GAP + 1:
            incidents[-1][1] = i
        else:
            incidents.append([i, i])
    return incidents


def average(values):
    """The mean of the numbers in some steps, 9 characters wide; "-" when there are none."""
    numbers = [v for v in values if v is not None]
    return f"{mean(numbers):9.1f}" if numbers else f"{'-':>9}"


def evidence(number, times, series, events, first, last):
    """One incident's block: every series in four windows, then the events around it."""
    # Four snapshots, so slow trends like a leak show up, not just a jump.
    windows = [(first - 30, first - 15), (first - 15, first),  # 30-15 and 15-0 steps before
               (first, min(first + 10, last + 1)),             # its first 10 steps
               (max(last - 9, first), last + 1)]               # its last 10 steps
    width = max(map(len, series))
    lines = [f"Incident {number}: {label(times[first])} to {label(times[last])} "
             f"({last - first + 1} steps)",
             f"  {'series':{width}} {'-30..-15':>9} {'-15..0':>9} {'first 10':>9} {'last 10':>9}"]
    for name, values in series.items():
        lines.append(f"  {name:{width}} "
                     + " ".join(average(values[max(a, 0):max(b, 0)]) for a, b in windows))

    since, until = times[max(first - LEAD, 0)], times[last] + STEP
    clock = "%H:%M:%S" if since.date() == (until - timedelta(seconds=1)).date() else "%m-%d %H:%M"
    for name, rows in events.items():
        found = [(t, text) for t, text in rows if since <= t < until]
        # Rows that differ only in their numbers are one kind: "took 812 ms" = "took 95 ms".
        kinds, seen, example = Counter(), {}, {}
        for t, text in found:
            kind = re.sub(r"\b\d+\b", "N", text)
            kinds[kind] += 1
            seen[kind] = (seen.get(kind, (t,))[0], t)
            example.setdefault(kind, text)
        lines.append(f"  {name}: {len(found)} rows from {label(since)} to {label(until)}, "
                     f"{len(kinds)} kinds, first seen first")
        kept = sorted(kinds.most_common(KINDS), key=lambda pair: seen[pair[0]][0])
        for kind, count in kept:
            start, end = seen[kind]
            lines.append(f"    {count:5}x  {start:{clock}} to {end:{clock}}  e.g. {example[kind]}")
        left = kinds.most_common()[KINDS:]
        if left:
            lines.append(f"    and {len(left)} rarer kinds ({sum(n for _, n in left)} rows), left out")
    return "\n".join(lines)


def build_pack(case_dir):
    """c. A line about the case, then one evidence block per incident."""
    times, series, events = load(case_dir)
    incidents = find_incidents(series)
    rules = ", ".join(f"{name} {sign} {limit}" for name, (sign, limit) in LIMITS.items())
    header = (f"Case {Path(case_dir).name}: {label(times[0])} to {label(times[-1])}, "
              f"one step = {STEP}. A step is bad when {rules}. "
              f"{len(incidents)} incident(s) found. A file's .count is its rows per step.")
    return "\n\n".join([header] + [evidence(n, times, series, events, first, last)
                                   for n, (first, last) in enumerate(incidents, 1)])


def ask_llm(text):
    """d. Send the evidence pack and return the Markdown report (1-2 minutes)."""
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": text}],
        "thinking": {"type": "enabled"},  # DeepSeek only: drop this line for other APIs
        "stream": False,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {os.environ[API_KEY]}"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)["choices"][0]["message"]["content"]


def run(case_dir):
    """Steps a-e for one case. report.md is only written once the LLM has
    answered, so a failed call keeps the last good report. Returns the report."""
    pack = build_pack(case_dir)
    report = ask_llm(pack) + "\n\n---\n\n## Evidence sent to the LLM\n\n```\n" + pack + "\n```\n"
    Path(case_dir, "report.md").write_text(report, encoding="utf-8")
    return report


def timeline(case_dir):
    """The charts' data for app.py: every series, grouped by the file it came
    from, plus the limits and the incidents (first and last step, as indexes)."""
    times, series, events = load(case_dir)
    groups = {}
    for name, values in series.items():
        groups.setdefault(name.split(".")[0], []).append(
            {"name": name, "values": [None if v is None else round(v, 2) for v in values]})
    return {"case": Path(case_dir).name,
            "times": [label(t) for t in times],
            "limits": [{"name": name, "sign": sign, "value": limit}
                       for name, (sign, limit) in rules(series).items()],
            "groups": [{"source": source, "series": items} for source, items in groups.items()],
            "incidents": [{"first": first, "last": last} for first, last in find_incidents(series)]}


if __name__ == "__main__":
    args = sys.argv[1:]
    for case_dir in [a for a in args if a != "--pack"]:
        if "--pack" in args:
            print(build_pack(case_dir))
        else:
            print(run(case_dir))
            print(f"wrote {Path(case_dir, 'report.md')} ({MODEL})")
