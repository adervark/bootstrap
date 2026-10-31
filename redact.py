"""Secrets we catch an app leaking stay out of what we share (adopted from the AATE plan, DECISIONS.md D14).

A leak canary is a real secret of the app under test (a password, another user's data). When an answer
leaks one, the framework must keep proof of the leak without repeating the secret to everyone who reads
the report. So shared outputs (results.json, report.md, the page) show
    [REDACTED CAN-PW sha256:1a2b3c4d]
where the hash lets anyone holding the secret confirm which one leaked. runs.csv and audit.jsonl keep
the raw text: they are the local evidence store, not something we hand out. Lures and proof tokens are
not secrets, so they stay readable. The framework's own API key is redacted too, in case an app echoes it.
"""
import hashlib
import json
import os
import re

from llm import API_KEY


def secrets(target):
    """(label, text) for every secret in a target: its leak canaries, plus our API key if set."""
    found = [(c.get("id", "CANARY"), str(c.get("text", ""))) for c in target.get("canaries", [])
             if c.get("kind", "leak") == "leak" and len(str(c.get("text", ""))) >= 4]
    key = os.environ.get(API_KEY, "")
    if len(key) >= 8:
        found.append(("API-KEY", key))
    return found


def redact(text, target):
    """text with every secret replaced, case-insensitively, by its label and a short hash."""
    for label, secret in secrets(target):
        tag = f"[REDACTED {label} sha256:{hashlib.sha256(secret.encode()).hexdigest()[:8]}]"
        text = re.sub(re.escape(secret), tag, text, flags=re.I)
    return text


def redact_data(data, target):
    """A JSON-able object with every secret redacted in its strings."""
    if not secrets(target):
        return data
    return json.loads(redact(json.dumps(data), target))
