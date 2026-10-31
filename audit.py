"""A tamper-evident audit log: audit.jsonl in each case folder.

Each line holds its event plus a hash of itself and the line before it, so editing
or deleting any earlier line breaks the chain, and verify() says where.
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

GENESIS = "0" * 64


def _hash(entry):
    text = json.dumps({k: v for k, v in entry.items() if k != "hash"}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def read(case_dir):
    path = Path(case_dir, "audit.jsonl")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def log(case_dir, actor, action, **details):
    """Add one event. actor is who did it: a script's name, the llm, or a person."""
    entries = read(case_dir)
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "actor": actor,
             "action": action, "details": details,
             "previous": entries[-1]["hash"] if entries else GENESIS}
    entry["hash"] = _hash(entry)
    with open(Path(case_dir, "audit.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def verify(case_dir):
    """Returns (True, entries checked), or (False, the 0-based line where the chain breaks)."""
    previous = GENESIS
    entries = read(case_dir)
    for number, entry in enumerate(entries):
        if entry["previous"] != previous or _hash(entry) != entry["hash"]:
            return False, number
        previous = entry["hash"]
    return True, len(entries)
