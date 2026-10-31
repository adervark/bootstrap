"""A tamper-evident audit log: the audit table in data/gate.db, exported to audit.jsonl in each case folder.

Each entry holds its event plus a hash of itself and the entry before it, so editing
or deleting any earlier entry breaks the chain, and verify() says where.
"""
import hashlib
import json
from datetime import datetime

import store

GENESIS = "0" * 64


def _hash(entry):
    text = json.dumps({k: v for k, v in entry.items() if k != "hash"}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def read(case_dir):
    return store.audit_entries(case_dir)


def log(case_dir, actor, action, **details):
    """Add one event. actor is who did it: a script's name, the llm, or a person."""
    def build(previous):
        entry = {"time": datetime.now().isoformat(timespec="seconds"), "actor": actor,
                 "action": action, "details": details, "previous": previous or GENESIS}
        entry["hash"] = _hash(entry)
        return entry
    return store.append_audit(case_dir, build)


def verify(case_dir):
    """Returns (True, entries checked), or (False, the 0-based line where the chain breaks)."""
    previous = GENESIS
    entries = read(case_dir)
    for number, entry in enumerate(entries):
        if entry["previous"] != previous or _hash(entry) != entry["hash"]:
            return False, number
        previous = entry["hash"]
    return True, len(entries)
