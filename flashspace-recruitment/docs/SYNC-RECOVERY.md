# Supervised sync recovery (staging proposal)

## Incident and evidence
The completed Sales interview stayed Queued with a stale one-answer ClickUp task, then synced its complete transcript and Sarvam report after a same-version redeploy. That establishes restart recovery, NOT which operation stalled. The original worker logs only emitted failures, so absence of logs cannot identify whether a lock, database operation, provider call, or worker lifecycle was responsible.

## Changes
Opt-in `backend.reliable_sync:create_app()` preserves the durable interview APIs and Sarvam provider. The original entry points and Cloudflare branch remain unchanged.

- Explicit phase/elapsed/count logging for queue reads, advisory lock acquisition/release, application locking, evaluation, ClickUp requests, persistence and retry scheduling. Never log candidate identifiers, content, credentials or raw exceptions.
- Track worker liveness and phase age. A separate watchdog checks every 5 seconds and exits the process if a phase exceeds 180 seconds or the thread dies. Gunicorn must supervise and replace the process.
- Never start a replacement thread while the old one may still hold a lock or complete an external request. Process exit closes local connections; advisory locking and existing remote identity reconciliation remain intact.
- Wake the worker after request completion, as well as at request arrival, so queue scans before a commit do not consume the only wakeup.
- Keep the existing durable queue/version acknowledgement and retry delays. A newer concurrently saved answer cannot be falsely acknowledged as synced by an older snapshot.
- Recruiter-authenticated GET /api/admin/sync-health exposes worker_alive, phase, phase age and sequence; public /api/health stays a cheap liveness check.

## Trade-offs and limits
This is automatic fail-stop recovery plus diagnostics, not proof that every sync failure is permanently eliminated. The watchdog can interrupt in-flight requests in that one Gunicorn process; clients must retry using existing answer idempotency. Committed data is not deleted. An ambiguous remote create may still require reconciliation; ClickUp does not provide transactional exactly-once task creation here.

The 180-second phase budget can restart a process during exceptionally slow legitimate work, including long ClickUp reconciliation scans. Repeated stalls require investigation of the logged phase, not repeated redeploys or more watchdog threads. An exhausted quota/bad credential will remain Retry pending and must not be bypassed. CPU starvation or a process unable to schedule Python threads may also prevent watchdog execution.

Render Free still sleeps, and the worker deliberately stops database polling after ten minutes without HTTP activity. This version therefore does NOT guarantee unattended background processing while hosting is asleep. Always-on processing needs an approved always-on web/worker plan or an external scheduled queue consumer; no paid resource has been created.

## Tests
Inherited backend/durable tests, automatic background drain without manual work_once, post-commit wake, lock-busy skip, recovery after loop errors, authenticated diagnostics and watchdog fail-stop decision. Existing CI also runs disposable PostgreSQL tests. Fault injection against a real deployed process remains required; mocks do not prove Gunicorn restarts or live lock release.

## Staging rollout (not automatic from this branch)
Branch: fix/sync-worker-recovery, based on feat/sarvam-interviews at b301c56fab4bb8ead909954320ded3fd6855dfb3.

After CI passes and the recovery trade-off is approved, set only the existing staging branch and start command:

```
gunicorn 'backend.reliable_sync:create_app()' --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120 --access-logfile /dev/null
```

Preserve root, build, database, credentials, role/test Folder and quota settings. No schema migration. Do not deploy until current tests are confirmed and no live applicant test is underway. Auto-deploying on a branch switch is expected; do not trigger duplicate deploys.

Validate fictional interview -> four committed answers -> complete -> report/task automatic update without Retry. Check phase logs and recruiter diagnostics. Then test a controlled worker stall with no candidate requests and verify supervised restart, durable answer retention and resumed sync; do not expose a public fault-injection endpoint. Test transient provider/ClickUp errors without changing production credentials. Verify two successive interviews without restart before claiming operational recovery.

Rollback: restore feat/sarvam-interviews and backend.sarvam_server:create_app() using the same Gunicorn flags; restore no database backups and delete no records. That restores the known pre-hardening code, including its observed stall risk. Production/main remain untouched.
