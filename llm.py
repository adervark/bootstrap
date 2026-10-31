"""The one place the framework calls its LLM (DeepSeek flash, see DECISIONS.md D2).

ask(system, user)       returns text
ask_json(system, user)  returns a parsed dict; a reply that is not valid JSON is
                        retried, never trusted, then raises ValueError
usage()                 the calls, tokens and estimated cost so far in this process
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

API_URL = "https://api.deepseek.com/chat/completions"
API_KEY = "DEEPSEEK_API_KEY"  # the variable in .env that holds the key
MODEL = "deepseek-flash"  # the API names it DeepSeek-V4.1-Flash
# USD per million tokens. Best-supported list price from pricing pages, 2026-10-31;
# DeepSeek's own rate sheet could not be opened, so cost is an estimate.
PRICE_INPUT, PRICE_OUTPUT = 0.30, 1.20
TRIES = 3

_totals = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0}
_lock = threading.Lock()


def _call(system, user, as_json, temperature):
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "thinking": {"type": "disabled"},
        "stream": False,
    }
    if as_json:
        body["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {os.environ[API_KEY]}"},
    )
    start = time.time()
    with urllib.request.urlopen(request, timeout=120) as response:
        reply = json.load(response)
    used = reply.get("usage", {})
    with _lock:
        _totals["calls"] += 1
        _totals["input_tokens"] += used.get("prompt_tokens", 0)
        _totals["output_tokens"] += used.get("completion_tokens", 0)
        _totals["seconds"] += time.time() - start
    return reply["choices"][0]["message"].get("content") or ""


def ask(system, user, temperature=0.0):
    """One text reply. Retries network errors and rate limits."""
    for attempt in range(TRIES):
        try:
            return _call(system, user, False, temperature)
        except (urllib.error.URLError, TimeoutError):
            if attempt == TRIES - 1:
                raise
            time.sleep(2 ** attempt)


def ask_json(system, user, temperature=0.0):
    """One reply parsed as a JSON object. Invalid JSON is retried, then raises ValueError."""
    problem = None
    for attempt in range(TRIES):
        try:
            parsed = json.loads(_call(system, user, True, temperature))
            if isinstance(parsed, dict):
                return parsed
            problem = "the reply was JSON but not an object"
        except json.JSONDecodeError as error:
            problem = f"the reply was not valid JSON: {error}"
        except (urllib.error.URLError, TimeoutError) as error:
            problem = f"the call failed: {error}"
            time.sleep(2 ** attempt)
    raise ValueError(f"no usable JSON after {TRIES} tries: {problem}")


def usage():
    with _lock:
        cost = (_totals["input_tokens"] * PRICE_INPUT
                + _totals["output_tokens"] * PRICE_OUTPUT) / 1_000_000
        return {**_totals, "seconds": round(_totals["seconds"], 1),
                "cost_usd": round(cost, 5)}


if __name__ == "__main__":
    print(ask_json("You output valid JSON only.", 'Return {"ok": true}'), usage())
