# Sarvam staging version

## Goal and design

Validate the existing Record -> Stop -> review transcript -> submit -> receive flow using direct Sarvam APIs, without altering the preserved Cloudflare implementation or production. Success means one fictional interview produces playable voice, usable transcripts, durably saved answers, a validated advisory report and a reconciled test ClickUp record, including failure/restart cases.

- Branch: `feat/sarvam-interviews`, forked from `feat/workers-ai-proxy` at `b6d2bada03637adb46a0a237c3c0d6ec405551bc`.
- Keep `feat/workers-ai-proxy`, its entry point, and PR #3 unchanged as the Cloudflare/proxy reference. The historical direct Cloudflare adapter also remains present.
- New `backend.sarvam_provider`: fixed Sarvam HTTPS origin, REST multipart STT, JSON TTS, structured chat completion. No Cloudflare fallback.
- New `backend.sarvam_server:create_app()`: injects Sarvam into the existing durable backend. Same routes, authentication, ownership checks, database schema and ClickUp sync. No migration or frontend rebuild logic changes.
- STT: `saaras:v3`, transcribe mode, automatic language detection. Returns the existing `{text: ...}` interface. Never auto-translate candidate evidence.
- TTS: `bulbul:v3`, `shubh`, `en-IN`, 24 kHz MP3 matching the existing audio/mpeg route. Question language remains English for this initial staging version.
- Questions/reports: `sarvam-105b`, strict JSON schema, reasoning disabled, 1800 output tokens, one completion. Local structural and existing semantic validations still apply; incomplete/refused/tool-call output is rejected.
- Reports identify `provider=sarvam`, the actual model, and `rubric_version=flashspace-sarvam-v1`; scoring criteria remain unchanged and advisory, with human review required.
- PostgreSQL saves submitted answers before inference; AI failure retains the saved answer and labelled standard follow-up. Report failures retain the transcript for sync/retry. No existing answers are rescored automatically.

## Safety and limitations

Only fictional candidates. The existing UI consent text/version originated with the Cloudflare implementation; it is NOT approval to send real candidate data to Sarvam. Before real use, update provider disclosures and consent/version handling, review retention/deletion, region/subprocessors and data-training terms, and approve processing costs. Do not reuse real applications for the staging switch: pending background reports may be processed by the newly selected provider.

Credentials remain server-side. Requests use only the fixed `https://api.sarvam.ai` origin and three allowlisted paths. Redirects are blocked. Errors do not include tokens, bodies, transcripts or upstream diagnostic text. No automatic provider fallback or immediate retry is made; this avoids duplicate inference charges. Existing durable application-level report retries and quotas still apply.

Response cap: 16 MB; input recording cap: 2 MB. Size is NOT a duration check. Sarvam's REST guide describes short recordings under 30 seconds: use 20–25 second clips during staging. The existing browser recorder can produce longer clips and is not yet duration-gated for Sarvam. Long-recording UX, chunking/batch transcription and server-side duration validation remain release gates; type longer answers for now. No claim of two-minute recording support for this adapter.

40-second socket timeout is not a hard end-to-end deadline. Validate actual latency and concurrency. Existing one-worker mutation lock and free-tier cold starts remain constraints; do not increase workers without redesigning locking. No new dependencies or paid resources are introduced by this code.

## Activation — only after passing CI and secure configuration

This commit does not change any Render service. Use the existing **staging** service only:
https://dashboard.render.com/web/srv-dagpprpt0dsc73a6guv0

1. Confirm the database is the isolated Test TeamRecrut database with fictional data only and ClickUp points to the private test Folder. Check pending jobs before activation.
2. Obtain a Sarvam key with access/credits for all three models. Enter `SARVAM_API_KEY` directly in Render Environment, never chat, Git, screenshots or frontend configuration. Use Save only where possible until activation is ready. No paid upgrade without approval.
3. Preserve existing DATABASE_URL, REQUIRE_DATABASE_URL=true, admin credentials and test ClickUp variables. Keep `MAX_AI_CALLS_PER_DAY=30`; this is an application-call cap, NOT a billing cap. Check Sarvam dashboard credits/spend separately.
4. After CI is green and the staging switch is approved, set branch to `feat/sarvam-interviews` and start command to:

```bash
gunicorn 'backend.sarvam_server:create_app()' --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120 --access-logfile /dev/null
```

Root Directory remains `flashspace-recruitment`. Existing build command and /api/health stay unchanged. Changing only the branch will NOT activate Sarvam while the proxy start command remains. Prefer saving both settings together. Do not trigger a duplicate deployment if Render already started one automatically. Keep production and main unchanged.

## Tests and release gates

CI: `python -m unittest discover -s tests -v` from `flashspace-recruitment`. Existing PR-to-main workflow tests this branch without editing workflow permissions. New tests are mocked Sarvam contract/security tests and local WSGI/SQLite integration tests; inherited real PostgreSQL tests continue running with disposable CI PostgreSQL. None proves live Sarvam account access or voice quality.

After deployment:
1. Confirm correct deployed commit, start command, successful startup and /api/health (liveness only).
2. Register a fictional test candidate; test Hear question MP3 playback and a short Record -> Stop transcript. Check English/Indian-English accuracy and optionally code-mixed input without assuming quality.
3. Review/correct transcript, submit four answers, test duplicate submit and resume. Simulate provider outage and app restart in the isolated environment; confirm saved answers remain.
4. Complete and verify recruiter-only report, exact evidence quotes, human-review label and test ClickUp sync/reconciliation. Confirm another candidate cannot access audio/records and API keys never appear in browser responses.
5. Review latency, quotas, credit use and sanitized errors for authentication, invalid audio, exhaustion and timeout. Do not interpret a healthy /api/health as successful AI inference.
6. Before production: finish long-recording handling, provider disclosure/consent work, fairness/evidence evaluation, privacy review and full live PostgreSQL/ClickUp checks; get explicit release approval. No merge or production activation in this change.

## Rollback

For a staging regression, restore branch `feat/workers-ai-proxy` and start command `backend.proxy_server:create_app()` with the same Gunicorn flags, using its recorded passing commit above. This restores the previous code, NOT a guarantee that its known 401/403 access problem is fixed. Database schema is unchanged; do not restore/delete candidate records. If an unexpected real record is discovered, stop testing and resolve data handling before switching providers.

## References

- https://docs.sarvam.ai/api-reference/speech-to-text/transcribe
- https://docs.sarvam.ai/api-reference/text-to-speech/convert
- https://docs.sarvam.ai/api-reference/chat/chat-completions
- https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview
