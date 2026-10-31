# Incident Report — 2026-10-31

## 1. Summary
A few hundred web users (about 401–403 active users in the evidence) were affected for 9 minutes, from 09:12 to 09:20, by severely slow web responses. Average web response time rose from 141.3 ms before the incident to 1591.0 ms during the first/last 10-step windows, while database time rose from 19.8 ms to 748.7 ms. The evidence points to slow `UPDATE answers SET body=? WHERE id=?` database work; it does not show CPU, memory, user-load, or worker-pool saturation.

## 2. Timeline
- 2026-10-31 09:12–09:20 — Incident 1: `web.response_ms` above 1000 ms for 9 steps, averaging 1591.0 ms; `server.db_ms` averaged 748.7 ms; 19 slow-query log rows for `UPDATE answers SET body=? WHERE id=?` were logged from 09:11:40 to 09:20:40.

## 3. Root cause
### Incident 1
**Cause:** Slow database execution of `UPDATE answers SET body=? WHERE id=?` drove database latency up and caused the web response-time incident.

Evidence: `server.db_ms` was 19.8 in the pre-incident `-15..0` window and 748.7 in both the first and last 10-step windows; `web.response_ms` was 141.3 before and 1591.0 in the first/last 10-step windows. The logs include 19 slow-query rows from 09:11:40 to 09:20:40, with example `error | slow query took 1670 ms: UPDATE answers SET body=? WHERE id=?`, beginning just before the incident start at 09:12.

- **CPU:** `server.cpu_pct` moved only from 29.6 to 30.5, so CPU saturation is not supported as the cause.
- **Memory:** `server.memory_pct` moved only from 49.3 to 49.9, so memory pressure is not supported as the cause.
- **Web user load:** `web.users` moved only from 401.1 to 403.3, so a traffic surge is not supported as the cause.
- **Worker pool:** the log reports `worker pool: 13 busy / 50`, which shows capacity remaining; worker-pool exhaustion is not supported.
- **Scanner/probe traffic from 203.0.113.9:** the `File does not exist` errors for `wp-login.php`, `xmlrpc.php`, `.env`, `admin.php`, and `phpmyadmin/` ran from 09:10:05 to 09:10:29, before the 09:12 incident start and before the slow-query interval; they are not supported as the cause.
- **Log/error volume:** `log.count` stayed about flat (2.7 before, 2.6 during), so a general log flood or broad error storm is not supported.
- **DB lock contention / query plan / payload details:** the evidence does not settle why the UPDATE was slow; it shows the slow UPDATE but provides no lock-wait, query-plan, index, or payload-size data.

## 4. Resolution
1. **First, confirm whether the slow `UPDATE answers SET body=? WHERE id=?` workload is still active; if it is, pause, throttle, or queue that update path** so the database can recover. This targets the only metric that rose with the incident.
2. Capture the query plan, lock waits, and execution context for that UPDATE while it is available.
3. Optimize the UPDATE path: verify the `WHERE id=?` access path, reduce unnecessary payload work if possible, batch/rate-limit the updates, and add a database statement timeout for this path.
4. Confirm `server.db_ms` and `web.response_ms` return to the pre-incident baseline; if not, continue limiting the UPDATE workload until the query is fixed.

## 5. Prevention
- Add alerts on `server.db_ms`, `web.response_ms`, and slow-query count/rate against baseline so this is caught before users see 1.6 s responses.
- Instrument and review the `answers` UPDATE path with query plans and lock-wait monitoring; add or verify the appropriate index/access path, batching, and timeouts.
- Add database statement timeouts/limits for application queries so a single slow UPDATE cannot dominate database latency.
- Keep CPU, memory, user-load, and worker-pool monitoring; evidence shows they were not the limiting resource here, but they help exclude them in future incidents.
- Handle scanner/probe traffic separately from this incident; the evidence does not support it as the cause.

---

## Evidence sent to the LLM

```
Case sample: 2026-10-31 09:00 to 2026-10-31 09:29, one step = 0:01:00. A step is bad when web.response_ms > 1000. 1 incident(s) found. A file's .count is its rows per step.

Incident 1: 2026-10-31 09:12 to 2026-10-31 09:20 (9 steps)
  series             -30..-15    -15..0  first 10   last 10
  log.count                 -       2.7       2.6       2.6
  server.cpu_pct            -      29.6      30.5      30.5
  server.memory_pct         -      49.3      49.9      49.9
  server.db_ms              -      19.8     748.7     748.7
  web.users                 -     401.1     403.3     403.3
  web.response_ms           -     141.3    1591.0    1591.0
  log: 51 rows from 2026-10-31 09:07 to 2026-10-31 09:21, 7 kinds, first seen first
        7x  09:08:01-09:20:01  e.g. info | worker pool: 13 busy / 50
        5x  09:10:05-09:10:25  e.g. error | [client 203.0.113.9] File does not exist: /var/www/html/wp-login.php
        5x  09:10:06-09:10:26  e.g. error | [client 203.0.113.9] File does not exist: /var/www/html/xmlrpc.php
        5x  09:10:07-09:10:27  e.g. error | [client 203.0.113.9] File does not exist: /var/www/html/.env
        5x  09:10:08-09:10:28  e.g. error | [client 203.0.113.9] File does not exist: /var/www/html/admin.php
        5x  09:10:09-09:10:29  e.g. error | [client 203.0.113.9] File does not exist: /var/www/html/phpmyadmin/
       19x  09:11:40-09:20:40  e.g. error | slow query took 1670 ms: UPDATE answers SET body=? WHERE id=?
```
