# Turn-based interviews: staging design and release gate

Status: preparation only. No production entry point, deployment, schema or credentials changed.

## Goal and existing behavior

Candidate chooses a published role, signs in, consents, records, stops, reviews the transcript, submits, and receives a follow-up. The current frontend already implements MediaRecorder, Stop, Cloudflare transcription transport, editable transcript, typed fallback and on-demand Hear question playback. The backend already has PostgreSQL selection, saved applications, authenticated candidate/recruiter endpoints, report generation and retrying ClickUp sync. Those source features are not proof that live integrations pass.

A verified gap in backend/server.py is that the next AI question is generated BEFORE the submitted answer is committed. A provider error therefore discards that submission on the server. This change stages an alternative entry point that fixes that ordering without changing production.

## Staged implementation

Use backend.durable_server:create_app for staging; backend.server:create_app remains unchanged. The existing WSGI request wrapper continues to enforce session, origin, payload and content-type checks. The answer handler checks ownership and ordered turns, then commits the submitted text, its original question and timestamp with a labelled standard follow-up before inference. A successful provider response replaces that standard question. A provider/quota failure leaves the already-committed standard question, so the current UI can continue rather than becoming stuck. It is not presented as a successful adaptive AI response: fallback question text starts with 'Standard follow-up:' and question_source records standard/ai/complete. Duplicate submissions do not append another answer or spend inference quota. Database errors propagate rather than producing false saved acknowledgements.

Tradeoff for review: on AI failure, a standard job-related question keeps the interview moving, but loses adaptive probing for that turn. An identical retry returns the stored question instead of regenerating it. Approve this fallback behavior before promotion; if explicit retry of AI generation is preferred, add a separate pending-question endpoint and matching UI state instead.

No migration: question_source is an additive field in existing application JSON. No new providers or credentials. No raw audio retention. Existing role snapshots and ClickUp mappings remain intact. Four answers, human-review-only scores, existing report and transcript access rules are preserved.

The current one-worker/in-process lock limitation remains: provider calls can delay other mutations. Do not scale worker/instance count until database-level concurrency control is designed and tested. This PR is not a production-readiness certification.

## Observed deployment and isolation

Existing Render service: interviewportal-sm, Team's workspace, Singapore, Free, main, root flashspace-recruitment. Auto-deploy is enabled; do not push experimental commits to main. No separate interview staging service was listed; PR previews are disabled. No production settings were altered.

Before creating staging, configure a separate disposable PostgreSQL database and separate test recruiter credentials through secure Render settings. Never reuse the live candidate database. Use a dedicated private test ClickUp Folder and suitably scoped token, not the real hiring Folder. Cloudflare test access and usage cap must be confirmed securely. Do not place secrets in this document, GitHub, chat or build logs. Staging infrastructure creation awaits those prerequisites; no placeholder-secret service should be deployed.

Staging build (root flashspace-recruitment):

```sh
pip install -r requirements.txt && python -m unittest discover -s tests -v && (cd web && npm install --include=dev && npm run build)
```

Staging start:

```sh
gunicorn 'backend.durable_server:create_app()' --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120 --access-logfile /dev/null
```

Set DATABASE_URL, REQUIRE_DATABASE_URL=true, separate ADMIN_EMAIL/ADMIN_PASSWORD, Cloudflare variables, and separate ClickUp integration variables through secure service settings. Health path: /api/health (liveness only, not database/inference readiness).

## Verification and promotion gates

1. Isolated unit suite: 13 tests passed locally using a temporary SQLite-backed test adapter, covering save-before-inference, process exit, provider/quota failure, duplicate/conflicting retries, ownership, invalid turns, final turn and first/second database failures.
2. Run complete existing backend suite plus tests/test_durable_backend.py against the new WSGI app. These complete-app tests were authored but not executed in this preparation run.
3. Run a real disposable PostgreSQL test for the durable entry point, including process recreation and provider failure; existing optional Postgres test alone exercises the old entry point and is insufficient.
4. Browser smoke tests on staging: supported desktop/mobile browsers, permission denial, Record/Stop, transcript correction, typed fallback, speech playback, reload/resume, provider timeout, fourth-answer completion and export. Only submitted answers are durable; unsent typed drafts are not autosaved.
5. Two test candidates must not see each other's data or recruiter reports. Verify admin login and advisory report visibility.
6. Confirm persisted record after service restart and that test ClickUp sync succeeds/retries without losing transcripts. Test only fictional candidate data.
7. Merge approved vacancy PR #1 into the staging integration branch only after its tests pass. This reliability branch alone retains main's unpublished sample roles.
8. Verify full CI, review requirements, privacy contact/retention policy and rollback before production approval. Workflow credential permissions remain a separate unresolved CI setup issue.

Rollback before production: leave production on its existing entry point. A future approved promotion should explicitly switch entry points only with a tested artifact and rollback plan. The ClickUp artifact is a separate network-isolated preview and is not updated by this PR.
