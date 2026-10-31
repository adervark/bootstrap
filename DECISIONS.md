# Decisions

One entry per design decision: what was chosen, who chose it, why, and the line
to use if a juror asks. Newest last.

## D1. Test two real open-source apps, cloned and run locally (user)

- Replaces the first plan, a bot of our own, because cloning saves time.
- `damn-vulnerable-llm-agent` (Apache-2.0): a LangChain agent with known exploits.
- `RAG_Poisoning_POC` (AGPL-3.0): a real RAG app, loaded with our synthetic campus
  IT documents through a wrapper, without editing the repo. Poisoned corpus, then
  clean corpus, is the before and after.
- Skipped `openai-cs-agents-demo`: pinned to OpenAI's models and Agents SDK.
- Guardrail: only our local copies are attacked, and the runner refuses any URL
  that is not localhost. Clones stay out of git; we run AGPL code, not ship it.
- `litellm` is pinned below 1.82 because these apps receive our API key.
- If asked: "We didn't write these apps. Each one needs a small adapter, and the
  framework doesn't change. That is what makes it reusable."

## D2. DeepSeek flash for everything (user)

- `deepseek-flash` for the bot, the test generator and the judge. On 2026-10-31
  the API names it `DeepSeek-V4.1-Flash`. It is the only flash model listed, and
  the API shows no build number, so "v4.107" could not be confirmed.
- Why: fast, and 20 of 20 test calls returned valid JSON at 0.7-1.5 s.
- Known limit: the judge and the bot are the same model, so they can share blind
  spots. Planted faults measure how much this costs.
- Also: one earlier call with thinking off and JSON mode returned broken JSON.
  So every JSON reply is validated and retried, never trusted.
- If asked: "The same model is a real limit. So the citation, quote and leak
  checks are plain code, and we measure the judge against planted faults."

## D3. The deck is a local .pptx, at most 5 slides (user)

- Saved in the repo, nothing published. One exception to the Markdown-only rule.
- Must cover: problem, stakeholders, Architecture, Working Prototype, Dynamic Adaptation.

## D4. Adapt the prepared skeleton (proposed, not yet confirmed)

- Keep `app.py`, `ask_llm()`, `run()`, the report panel and the answer keys.
  Replace `load()` to `build_pack()`, because this problem has no timeline.
- If asked: "Yes, the generic skeleton was prepared before the event, and the
  commit history shows it. Everything specific to this problem was written today."

## D5. The LLM decides the verdict; code can veto (user)

- The LLM recommends Release, Conditional Release or Reject from the scorecard
  and findings, and must cite finding IDs.
- Code can only make the verdict stricter, never more lenient. Vetoes: a confirmed
  critical failure forces Reject; too little coverage blocks Release; a cited ID
  that does not exist voids the recommendation.
- The LLM votes three times and the majority counts, because the LLM can vary
  between runs. Agreement is reported as a number.
- If the LLM fails, the code's own rule-based verdict stands, and it can never
  be Release.
- Known limit: this LLM reads text influenced by the target. It is passed as
  marked data, and the vetoes do not depend on the LLM.
- If asked: "The AI weighs the evidence. Code holds a hard floor, so even a
  fooled LLM can't ship a release with a confirmed critical failure."

## D6. We measure our own accuracy with seeded faults (user)

- Code plants known errors in correct answers (a wrong number, an invented
  policy, a fake citation) and mixes them with untouched answers.
- Gives precision, recall and false-positive rate against known labels.
- Known limit: planted faults can be easier to catch than real ones, so we
  report these numbers as a benchmark, not as real-world accuracy.
- If asked: "We test the tester. Here is its score on faults we planted."

## D7. A human must approve any Release; a Reject blocks by itself (user)

- Release and Conditional Release wait for a named human. Overriding a Reject
  also needs a named human and a reason. Every step goes in the audit log.
- If asked: "The AI can stop a release alone, but it can never ship one alone."
