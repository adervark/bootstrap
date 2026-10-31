# Problem statement

Clock start (0:00): Sat 2026-10-31 09:26 IST. Hard stop (4:00): 13:26 IST.
Hackathon theme: "AI for Tech: Campus IT Operations".

## PS, word for word

Theme Objective: Build intelligent AI systems capable of understanding, engineering, operating, securing and optimizing complex technology environments.
Context & Background
Traditional testing cannot fully address LLM risks such as hallucination, variability, prompt injection, grounding failures, bias and model drift. A few successful prompts are not enough to establish release confidence.

Your Challenge
Build a reusable AI quality framework that evaluates LLM-enabled systems for accuracy, grounding, completeness, safety, consistency, security and release readiness. The framework should detect failures and recommend Release, Conditional Release or Reject with supporting evidence.

Think End-to-End
Define Risks → Generate Tests → Execute → Capture Responses → Verify Grounding → Classify Failures → Score Quality → Recommend Release → Human Review → Monitor → Regress

What Your AI Must Demonstrate
Dynamically generate tests from risk scenarios
Test an LLM-enabled application
Detect hallucinations and unsupported claims
Verify grounding and citations
Run prompt- injection and adversarial tests
Produce quality and safety scores
Explain the release recommendation
Convert failures into regression tests
Important Requirement
A manually prepared collection of prompts is not sufficient. The solution should dynamically generate or vary test scenarios based on risks, context and previous failures.

Expected Outcome
Reusable evaluation dataset and test suite
Quality and safety scorecard
Failure taxonomy with evidence
Release recommendation
Regression suite
Continuous-monitoring plan
Guardrails
Test only against sandbox/demo or authorized applications
Do not attack real external systems
Use synthetic or anonymized sensitive data
Maintain test evidence and audit logs
Require human review for critical release decisions
Success Measures
Failure and hallucination detection accuracy
Grounding verification accuracy
Prompt-injection detection
Low false-positive rate
Test and risk coverage
Regression coverage
Consistency and explainability
Quality of release recommendations
Ability to adapt to new jury- provided scenarios

## Judging deliverables, word for word

1. Problem Understanding Presentation
Explain the real problem and stakeholders. Have less no of slide (max 5 slides) to articluate your AI work but mandatory to coverer Architecture ,Working Prototype ,Dynamic Adaptation

2. AI Architecture
Show: Input → AI/Agents → Tools → Data/Knowledge → Decisions → Human Control → Output

3. Working Prototype
A functional implementation is required.

4. AI Reasoning
Demonstrate why AI made its recommendation.

5. Evidence & Traceability
Show which evidence influenced important conclusions.

6. Evaluation
Define measurable metrics. Examples:

accuracy
groundedness
latency
cost
false-positive rate
task-success rate
recovery time
business KPI.
7. Responsible AI
Explain:

privacy
security
hallucination control
human approval
failure handling
bias/fairness where applicable.
8. Dynamic Adaptation
Demonstrate how the solution handles the jury's surprise scenario.

## Checklist

Required behaviour:

- [ ] Tests generated dynamically from risks, context and previous failures (not a fixed prompt list)
- [ ] Tests an LLM-enabled application (sandbox only)
- [ ] Detects hallucinations and unsupported claims
- [ ] Verifies grounding and citations
- [ ] Runs prompt-injection and adversarial tests
- [ ] Measures accuracy, grounding, completeness, safety, consistency, security
- [ ] Quality and safety scores
- [ ] Recommends Release, Conditional Release or Reject, and explains why
- [ ] Converts failures into regression tests

Required outputs:

- [ ] Reusable evaluation dataset and test suite
- [ ] Quality and safety scorecard
- [ ] Failure taxonomy with evidence
- [ ] Release recommendation
- [ ] Regression suite
- [ ] Continuous-monitoring plan

Guardrails:

- [ ] Only the sandbox target is tested; no real external system
- [ ] Synthetic or anonymized sensitive data only
- [ ] Test evidence and audit logs kept
- [ ] Human review required for critical release decisions

Success measures to report with numbers:

- [ ] Failure and hallucination detection accuracy
- [ ] Grounding verification accuracy
- [ ] Prompt-injection detection
- [ ] False-positive rate
- [ ] Test and risk coverage
- [ ] Regression coverage
- [ ] Consistency and explainability
- [ ] Quality of release recommendations
- [ ] Adapts to new jury-provided scenarios

Judging deliverables:

- [ ] Presentation, at most 5 slides: problem, stakeholders, Architecture, Working Prototype, Dynamic Adaptation
- [ ] Architecture diagram: Input → AI/Agents → Tools → Data/Knowledge → Decisions → Human Control → Output
- [ ] Working prototype
- [ ] AI reasoning shown: why this recommendation
- [ ] Evidence and traceability: which evidence drove each conclusion
- [ ] Metrics defined and measured, including latency and cost
- [ ] Responsible AI: privacy, security, hallucination control, human approval, failure handling, bias/fairness
- [ ] Jury's surprise scenario handled live

## Data

The PS names no dataset, so there is nothing to download. Everything is
synthetic: the target's knowledge base, its users and any personal data.

## Fit check against ARCHITECTURE.md

This is the "No timeline" row. Keep `app.py`, `ask_llm()`, `run()`, the report
panel and the answer keys. Replace `load()` to `build_pack()`. `timeline()` keeps
its name but returns what the page shows.
