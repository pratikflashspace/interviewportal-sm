# Workers AI proxy: staged integration

## Scope and design

Explicit opt-in entry point `backend.proxy_server:create_app()` injects ProxyAI into the existing durable interview app. Production `backend.server:create_app()` and current staging `backend.durable_server:create_app()` are unchanged. No database migration, candidate-auth change, workflow permission changes, worker scaling or automatic provider fallback.

The server posts only `{model, input}` to the approved HTTPS endpoint. Never override employee-identification fields. The browser never receives the credential. No direct Cloudflare account API calls occur in proxy mode. Question generation and reports use GLM-4.7-Flash, transcription uses Whisper Large V3 Turbo, speech uses MeloTTS (English). Existing evidence-quote validation, advisory scoring, human-review requirement and save-before-inference logic remain in use. Model quality/fairness is not established by parser tests.

The proxy contract supplied by its operator uses integer audio bytes for STT. Limit proxy recordings to 2 MB to bound JSON expansion/memory; type answers or use shorter recordings. STT omits the English hint to allow model language detection; TTS is English only in this adapter. English/Hindi/Hinglish accuracy requires live testing, not assumed support.

LLM parsing supports result/response JSON and non-streaming choices[0].message.content with finish_reason=stop. Refusals, truncation, reasoning-only output and invalid structured responses fail closed. TTS accepts MP3 or JSON base64 audio and rejects obvious non-MP3 payloads. Actual proxy response envelopes remain unverified until a rotated token is securely configured.

Fixed HTTPS endpoint and a no-redirect handler prevent forwarding credentials. At most one additional request after HTTP 429/503, after 1s. No automatic retry for auth failures or ambiguous transport errors. Socket timeout is 25s per attempt; this is not a hard total deadline for a slow streaming response. Response read is bounded to 16 MB; keep Gunicorn's 120s timeout. Retries can still incur provider charges; the app's daily quota counts logical calls, not every retry. No token, audio, transcript or provider error-body logging in the adapter.

## Credential and privacy gates

The previously shared credential is exposed and must be revoked/rotated by the proxy owner. Do not use it for testing. No token is stored in this repository. Obtain a replacement via a secure channel and enter it directly in Render. Never post tokens here or in ClickUp. The proxy operator must confirm revocation, permitted usage and whether audio/transcripts/prompts are logged, retained or shared; usage metadata alone does not answer that. Fictional test data only until content handling and retention are approved. No paid resources or upgrades are authorized by this change.

## Secure staging activation (after CI passes)

Current staging service: interviewportal-sm-1, Singapore Free. Never modify production interviewportal-sm. This feature branch is separate so pushing it does not deploy either service. Do not merge this PR into main.

Use branch `feat/workers-ai-proxy`; keep root `flashspace-recruitment` and the existing tested build command. In staging's secure Environment settings add:

- PRATIK_WORKERS_AI_URL: https://pool-a-pratik-ai.yasasv.workers.dev/v1/run
- PRATIK_WORKERS_AI_TOKEN: rotated credential entered privately (not the exposed credential)
- MAX_AI_CALLS_PER_DAY: 30 (logical request quota, not a billing guarantee)

Keep separate Test TeamRecrut DATABASE_URL with TLS, REQUIRE_DATABASE_URL=true, test ADMIN_EMAIL/ADMIN_PASSWORD and private test ClickUp configuration. No new Cloudflare account/gateway/voice variables are needed in proxy mode; direct-provider variables are ignored by this entry point, not deleted automatically.

Start command:

```sh
gunicorn 'backend.proxy_server:create_app()' --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120 --access-logfile /dev/null
```

Changing branch/start command/environment may trigger deployment. Coordinate changes to avoid testing a partially configured service. Never paste replacement credentials into a command or screenshot. Missing token fails startup rather than reverting to the old provider.

## Validation and release

CI runs mock proxy transport and parser tests plus the inherited backend and disposable PostgreSQL suites. It does not prove real proxy access or output quality. After rotated token configuration, verify:

1. Health/liveness and the three approved roles on staging.
2. Hear question (MP3), Record/Stop, editable transcription, typed fallback, and four-turn interview using fictional details.
3. Adaptive question generation, labelled standard fallback on AI outage, saved answers after reload and actual service restart.
4. Recruiter-only advisory report, evidence quotes and no cross-candidate access.
5. Test ClickUp sync and recovery; no real hiring records.
6. Proxy latency, quota behavior and content-retention approval with operator before any real candidate use.

Rollback: restore staging's previous branch and durable_server start command as a pair, keeping the separate database and test ClickUp settings. This restores the previous implementation; it does not fix its known direct Cloudflare authorization error. Production remains unchanged. Keep PR draft until review and live integration gates pass.
