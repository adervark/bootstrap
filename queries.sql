-- Queries for data/gate.db (store.py, README.md D18). Open the file in DBeaver's SQL editor
-- on the "LLM Release Gate (gate.db)" connection and run one with Ctrl+Enter.
-- "Current" means each case's newest analysis; older analyses stay as its history.

-- 1. Each app's current verdict, worst first.
SELECT case_name, final_verdict, overall, status, created
FROM analyses
WHERE id IN (SELECT MAX(id) FROM analyses GROUP BY case_name)
ORDER BY overall;

-- 2. Attacks that worked per app: security and safety tests that got an answer, and how many
--    of them have a PROMPT_INJECTION, DATA_LEAK, PII_LEAK or UNSAFE_CONTENT finding (analyze.ATTACK_WON).
SELECT t.case_name,
       COUNT(DISTINCT t.test_id) AS attack_tests,
       COUNT(DISTINCT CASE WHEN f.code IN ('PROMPT_INJECTION', 'DATA_LEAK', 'PII_LEAK', 'UNSAFE_CONTENT')
                           THEN t.test_id END) AS attacks_worked
FROM tests t
JOIN risks r ON r.case_name = t.case_name AND r.risk_id = t.risk_id
LEFT JOIN findings f ON f.case_name = t.case_name AND f.test_id = t.test_id
     AND f.analysis_id = (SELECT MAX(id) FROM analyses a WHERE a.case_name = t.case_name)
WHERE r.dimension IN ('security', 'safety')
  AND EXISTS (SELECT 1 FROM runs u WHERE u.case_name = t.case_name AND u.test_id = t.test_id)
GROUP BY t.case_name
ORDER BY attacks_worked DESC;

-- 3. Failure codes across apps, current analyses.
SELECT code, case_name, COUNT(*) AS findings
FROM findings
WHERE analysis_id IN (SELECT MAX(id) FROM analyses GROUP BY case_name)
GROUP BY code, case_name
ORDER BY code, findings DESC;

-- 4. Critical findings with the question and the answer they came from.
SELECT f.case_name, f.id, f.code, f.test_id, t.prompt, u.answer, f.detail
FROM findings f
JOIN tests t ON t.case_name = f.case_name AND t.test_id = f.test_id
JOIN runs u ON u.case_name = f.case_name AND u.run_id = f.run_id
WHERE f.severity = 'critical'
  AND f.analysis_id IN (SELECT MAX(id) FROM analyses GROUP BY case_name)
ORDER BY f.case_name, f.id;

-- 5. Every analysis of every case: the verdict over time.
SELECT id, case_name, created, final_verdict, overall, status,
       (SELECT COUNT(*) FROM findings f WHERE f.analysis_id = a.id) AS findings
FROM analyses a
ORDER BY id;

-- 6. One case's audit chain: each entry carries the hash of the one before it.
SELECT seq, time, actor, action, substr(details, 1, 120) AS details,
       substr(previous, 1, 12) AS previous, substr(hash, 1, 12) AS hash
FROM audit
WHERE case_name = 'data/sessions/campus_poisoned'
ORDER BY seq;
