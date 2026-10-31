"""A tiny stand-in target, so generate.py and execute.py can be tested before real targets exist.

Serves the Target server contract on 127.0.0.1 only: POST /ask and GET /health.
Answers from a target.json's KB by keyword matching and cites the documents used.
No LLM and no memory. It is a test double, not something the framework evaluates.

Usage: python3 stub_target.py [target_json] [--port 8100]
"""
import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_TARGET = Path(__file__).resolve().parent / "contracts" / "sample" / "target.json"
STOPWORDS = set("a an and are at can do does for how i in is it my of on or the to what when where who with".split())
NOT_FOUND = "I could not find that in the IT policy documents."
MAX_SENTENCES = 2


def words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower())) - STOPWORDS


def answer(question, kb):
    """The KB sentences sharing the most words with the question, each with its document cited."""
    asked = words(question)
    scored = []
    for doc in kb:
        for sentence in re.split(r"(?<=[.!?])\s+", doc["text"]):
            score = len(asked & words(sentence))
            if score:
                scored.append((score, sentence, doc))
    scored.sort(key=lambda item: -item[0])
    best = scored[:MAX_SENTENCES]
    if not best:
        return {"answer": NOT_FOUND, "sources": [], "tools": [], "tokens": len(NOT_FOUND.split())}
    text = " ".join(f"{sentence} [{doc['id']}]" for _, sentence, doc in best)
    sources = {doc["id"]: doc for _, _, doc in best}
    return {"answer": text, "sources": list(sources.values()), "tools": [], "tokens": len(text.split())}


def serve(kb, port):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, {"ok": True})
            else:
                self.reply(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/ask":
                self.reply(404, {"error": "not found"})
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                self.reply(200, answer(str(body["question"]), kb))
            except (ValueError, KeyError, TypeError) as error:
                self.reply(400, {"error": f"bad request: {error}"})

        def log_message(self, *args):
            pass

    print(f"stub target on http://127.0.0.1:{port}/ask with {len(kb)} documents", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stub target for testing the runner")
    parser.add_argument("target_json", nargs="?", default=DEFAULT_TARGET)
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()
    serve(json.loads(Path(args.target_json).read_text(encoding="utf-8"))["kb"], args.port)
