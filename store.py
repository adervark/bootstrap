"""The store: every case's data lives in one SQLite database, data/gate.db (README.md D18).

Tables, each row tagged with its case (the case folder, relative to the repo):
  risks, tests, runs   one row per risk, test and captured answer; the contract's columns,
                       read from contracts/sample/*.csv, so the store and the contract never differ
  analyses             one row per analysis: when, verdict, overall, the full results and report.
                       Every analysis is kept, so a case has a history; the newest is the current one
  findings             each analysis's findings, one row each, for queries across cases and runs
  audit                the hash-chained log (audit.py); appends are serialised so the chain cannot fork
  check_cache          the reused checks of unchanged answers (D16)

The database is the only record, and it is committed to git (D20). Nothing writes a case's
CSV or JSON any more; report.md is still written, for a person to read. A case folder seen
for the first time is imported once from whatever files it has (contracts/sample does).

Standard library only (sqlite3). Every value goes in through a ? parameter.
"""
import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

csv.field_size_limit(10_000_000)  # a run's sources column holds whole documents
ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "gate.db"
TABLES = ("risks", "tests", "runs")
COLUMNS = {name: next(csv.reader(open(ROOT / "contracts" / "sample" / f"{name}.csv", encoding="utf-8")))
           for name in TABLES}
FINDING_COLUMNS = ["id", "code", "severity", "dimension", "check", "test_id", "run_id", "detail", "evidence", "owasp"]


def _q(name):
    """A column name, quoted: some contract columns, like check, are SQL keywords."""
    return '"' + name.replace('"', '""') + '"'


def _schema(db):
    for name in TABLES:
        cols = ", ".join(f"{_q(c)} TEXT" for c in COLUMNS[name])
        db.execute(f"CREATE TABLE IF NOT EXISTS {name} (seq INTEGER PRIMARY KEY, case_name TEXT NOT NULL, {cols})")
        db.execute(f"CREATE INDEX IF NOT EXISTS {name}_case ON {name} (case_name)")
    db.executescript(f"""
        CREATE TABLE IF NOT EXISTS cases (case_name TEXT PRIMARY KEY, imported TEXT);
        CREATE TABLE IF NOT EXISTS analyses (id INTEGER PRIMARY KEY, case_name TEXT NOT NULL, created TEXT,
            final_verdict TEXT, overall REAL, status TEXT, results TEXT, report TEXT);
        CREATE INDEX IF NOT EXISTS analyses_case ON analyses (case_name);
        CREATE TABLE IF NOT EXISTS findings (seq INTEGER PRIMARY KEY, analysis_id INTEGER NOT NULL,
            case_name TEXT NOT NULL, {", ".join(f"{_q(c)} TEXT" for c in FINDING_COLUMNS)});
        CREATE INDEX IF NOT EXISTS findings_analysis ON findings (analysis_id);
        CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY, case_name TEXT NOT NULL, time TEXT, actor TEXT,
            action TEXT, details TEXT, previous TEXT, hash TEXT);
        CREATE INDEX IF NOT EXISTS audit_case ON audit (case_name);
        CREATE TABLE IF NOT EXISTS check_cache (case_name TEXT NOT NULL, key TEXT NOT NULL, value TEXT,
            PRIMARY KEY (case_name, key));
    """)


def connect():
    """A fresh connection per call: the server's threads never share one. WAL lets readers
    (the page, the live feed) read while a run writes."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=60)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    _schema(db)
    return db


def case_of(case_dir):
    path = Path(case_dir).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


# ---- the one-time import of a case folder's files

def _read_file_csv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _ensure(db, case_dir):
    """Import a case's files the first time the case is seen; after that the database is the record."""
    case = case_of(case_dir)
    if db.execute("SELECT 1 FROM cases WHERE case_name = ?", (case,)).fetchone():
        return case
    db.execute("BEGIN IMMEDIATE")
    if db.execute("SELECT 1 FROM cases WHERE case_name = ?", (case,)).fetchone():
        db.commit()
        return case
    folder = Path(case_dir)
    for name in TABLES:
        _insert(db, case, name, _read_file_csv(folder / f"{name}.csv"))
    results = folder / "results.json"
    if results.exists():
        report = folder / "report.md"
        created = datetime.fromtimestamp(results.stat().st_mtime).isoformat(timespec="seconds")
        _insert_analysis(db, case, json.loads(results.read_text(encoding="utf-8")),
                         report.read_text(encoding="utf-8") if report.exists() else "", created)
    log = folder / "audit.jsonl"
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            if line:
                _insert_audit(db, case, json.loads(line))
    cache = folder / "check_cache.json"
    if cache.exists():
        db.executemany("INSERT OR REPLACE INTO check_cache VALUES (?, ?, ?)",
                       [(case, key, json.dumps(value)) for key, value in json.loads(cache.read_text(encoding="utf-8")).items()])
    db.execute("INSERT INTO cases VALUES (?, ?)", (case, datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return case


# ---- risks, tests, runs

def _insert(db, case, name, rows):
    cols = COLUMNS[name]
    db.executemany(f"INSERT INTO {name} (case_name, {', '.join(map(_q, cols))}) VALUES (?{', ?' * len(cols)})",
                   [(case, *(str(row.get(c, "") if row.get(c) is not None else "") for c in cols)) for row in rows])


def _table(path):
    """The table a case file maps to, or None for any other CSV (suites, regression sets)."""
    name = Path(path).name
    return name[:-4] if name.endswith(".csv") and name[:-4] in TABLES else None


def _rows(db, case, name):
    cols = COLUMNS[name]
    return [dict(zip(cols, row)) for row in
            db.execute(f"SELECT {', '.join(map(_q, cols))} FROM {name} WHERE case_name = ? ORDER BY seq", (case,))]


def read_csv(path):
    """The rows of a case's risks.csv, tests.csv or runs.csv, from the database; any other CSV from its file."""
    name = _table(path)
    if not name:
        return _read_file_csv(path)
    with connect() as db:
        return _rows(db, _ensure(db, Path(path).parent), name)


def write_csv(path, columns, rows):
    """Replace a case table's rows; any other CSV is written as a file."""
    name = _table(path)
    if not name:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, columns)
            writer.writeheader()
            writer.writerows(rows)
        return
    if list(columns) != COLUMNS[name]:
        raise ValueError(f"{name}: columns {list(columns)} differ from the contract's {COLUMNS[name]}")
    folder = Path(path).parent
    with connect() as db:
        case = _ensure(db, folder)
        db.execute(f"DELETE FROM {name} WHERE case_name = ?", (case,))
        _insert(db, case, name, rows)
        db.commit()


def add_rows(case_dir, name, rows):
    """Append rows to a case table."""
    with connect() as db:
        case = _ensure(db, case_dir)
        _insert(db, case, name, rows)
        db.commit()


# ---- analyses and findings

def _insert_analysis(db, case, results, report, created=None):
    decision, card = results.get("decision") or {}, results.get("scorecard") or {}
    cursor = db.execute("INSERT INTO analyses (case_name, created, final_verdict, overall, status, results, report) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (case, created or datetime.now().isoformat(timespec="seconds"), decision.get("final_verdict", ""),
                         card.get("overall"), decision.get("status", ""), json.dumps(results), report))
    db.executemany(f"INSERT INTO findings (analysis_id, case_name, {', '.join(map(_q, FINDING_COLUMNS))}) "
                   f"VALUES (?, ?{', ?' * len(FINDING_COLUMNS)})",
                   [(cursor.lastrowid, case, *(str(f.get(c, "")) for c in FINDING_COLUMNS)) for f in results.get("findings", [])])
    return cursor.lastrowid


def save_analysis(case_dir, results, report):
    """A new analysis: its row and its findings, then report.md for a person to read."""
    with connect() as db:
        number = _insert_analysis(db, _ensure(db, case_dir), results, report)
        db.commit()
    Path(case_dir, "report.md").write_text(report, encoding="utf-8")
    return number


def _latest(db, case_dir):
    return db.execute("SELECT * FROM analyses WHERE case_name = ? ORDER BY id DESC LIMIT 1",
                      (_ensure(db, case_dir),)).fetchone()


def results(case_dir):
    """The current analysis's results, or None before the first analysis."""
    with connect() as db:
        row = _latest(db, case_dir)
    return json.loads(row["results"]) if row else None


def report(case_dir):
    with connect() as db:
        row = _latest(db, case_dir)
    return row["report"] if row else None


def update_results(case_dir, data):
    """Change the current analysis in place: a human's decision (D7) belongs to the analysis it signs."""
    with connect() as db:
        row = _latest(db, case_dir)
        if not row:
            raise ValueError("This case has no analysis yet.")
        decision = data.get("decision") or {}
        db.execute("UPDATE analyses SET results = ?, status = ?, final_verdict = ? WHERE id = ?",
                   (json.dumps(data), decision.get("status", ""), decision.get("final_verdict", ""), row["id"]))
        db.commit()


def history(case_dir):
    """Every analysis of a case, newest first: the verdict over time."""
    with connect() as db:
        case = _ensure(db, case_dir)
        rows = db.execute("SELECT a.id, a.created, a.final_verdict, a.overall, a.status, "
                          "(SELECT COUNT(*) FROM findings f WHERE f.analysis_id = a.id) AS findings "
                          "FROM analyses a WHERE a.case_name = ? ORDER BY a.id DESC", (case,)).fetchall()
    return [dict(row) for row in rows]


def summary():
    """Row counts per table, and the current analysis of each case, for the page."""
    with connect() as db:
        counts = {name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("cases", *TABLES, "analyses", "findings", "audit", "check_cache")}
        current = db.execute("SELECT case_name, final_verdict, overall, MAX(id) AS analysis, COUNT(*) AS analyses "
                             "FROM analyses GROUP BY case_name ORDER BY case_name").fetchall()
        codes = db.execute("SELECT f.case_name, f.code, COUNT(*) AS n FROM findings f "
                           "WHERE f.analysis_id IN (SELECT MAX(id) FROM analyses GROUP BY case_name) "
                           "GROUP BY f.case_name, f.code ORDER BY f.case_name, n DESC").fetchall()
    return {"path": str(DB_PATH.relative_to(ROOT)), "counts": counts,
            "cases": [dict(row) for row in current], "codes": [dict(row) for row in codes]}


# ---- the audit chain

def _insert_audit(db, case, entry):
    db.execute("INSERT INTO audit (case_name, time, actor, action, details, previous, hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (case, entry["time"], entry["actor"], entry["action"], json.dumps(entry["details"]), entry["previous"], entry["hash"]))


def audit_entries(case_dir):
    with connect() as db:
        rows = db.execute("SELECT time, actor, action, details, previous, hash FROM audit WHERE case_name = ? ORDER BY seq",
                          (_ensure(db, case_dir),)).fetchall()
    return [{**dict(row), "details": json.loads(row["details"])} for row in rows]


def append_audit(case_dir, build):
    """build(previous hash) returns the finished entry. Reading the last hash and inserting happen
    under one write lock, so two writers can never both chain onto the same entry."""
    with connect() as db:
        case = _ensure(db, case_dir)
        db.execute("BEGIN IMMEDIATE")
        last = db.execute("SELECT hash FROM audit WHERE case_name = ? ORDER BY seq DESC LIMIT 1", (case,)).fetchone()
        entry = build(last["hash"] if last else None)
        _insert_audit(db, case, entry)
        db.commit()
    return entry


# ---- reused checks (D16)

def cache_load(case_dir):
    with connect() as db:
        rows = db.execute("SELECT key, value FROM check_cache WHERE case_name = ?", (_ensure(db, case_dir),)).fetchall()
    return {row["key"]: json.loads(row["value"]) for row in rows}


def cache_save(case_dir, cache):
    with connect() as db:
        case = _ensure(db, case_dir)
        db.execute("DELETE FROM check_cache WHERE case_name = ?", (case,))
        db.executemany("INSERT INTO check_cache VALUES (?, ?, ?)", [(case, k, json.dumps(v)) for k, v in cache.items()])
        db.commit()


def forget(case_dir):
    """Drop a case from the database. The next access imports whatever files its folder has.
    To put a case back as committed, restore the database instead: `git restore data/gate.db`."""
    case = case_of(case_dir)
    with connect() as db:
        for name in (*TABLES, "audit", "check_cache", "cases"):
            db.execute(f"DELETE FROM {name} WHERE case_name = ?", (case,))
        db.execute("DELETE FROM findings WHERE case_name = ?", (case,))
        db.execute("DELETE FROM analyses WHERE case_name = ?", (case,))
        db.commit()


if __name__ == "__main__":
    # python3 store.py [--reset] [case folders...]: import each case if new (or re-import it with
    # --reset), then print what the database holds.
    reset = "--reset" in sys.argv
    for folder in [arg for arg in sys.argv[1:] if arg != "--reset"]:
        if reset:
            forget(folder)
        with connect() as db:
            print(_ensure(db, folder))
    print(json.dumps(summary()["counts"], indent=1))
