# Interview v2 conversational pilot — not production-ready

Approved design: https://app.clickup.com/1851686/docs/1rg96-249416
Source banks supplied in the active requirements: https://app.clickup.com/1851686/chat/r/1rg96-249156/t/80160053908115
Implementation approval: https://app.clickup.com/1851686/chat/r/1rg96-249156/t/80160053909248

## Implemented

This branch forks the deployed recruiter-role-management baseline at 4cb4966. No existing service/branch is modified by these commits. New pilot URL `/interview-v2`; default candidate application creation remains v1 during the isolated pilot. Existing applications cannot convert or lose their saved four-question history. Production-wide replacement and navigation integration are deliberately deferred until voice acceptance.

Six generic core topics, then four sampled domain cores (two fundamentals then two scenarios). At most two follow-ups per stage, no follow-up chains; ten to fourteen answers. Generic source has six sections despite Q7 references; incomplete fallback is excluded. The generic routine prompt is narrowed to managing responsibilities. Domain banks contain all supplied core questions, with a curated subset of relevant source follow-ups. Follow-up selection can only choose a provided clarifier; it cannot invent a new question or change the budget. Token-set similarity guards obvious repeats, NOT full semantic equivalence/difficulty calibration.

Bank selections/texts/version and active state are saved per interview. Candidate-facing state does not expose unasked questions/clarifier choices. New recruiter roles require explicit bank mapping at the pilot page. Default mappings are only for the three approved existing role IDs. Closing/editing a vacancy does not alter an existing session's role snapshot or selected questions.

Separate `interview_v2` table (additive) mirrors answers/status atomically with the existing application data. Idempotent answer-event replay, stale question/version rejection, committed-answer-before-follow-up inference and crash recovery that skips optional inference instead of repeating it. V2 answer/finish routes cannot run through the old four-question endpoints. Initial application creation uses the existing validator; if interrupted between application creation and v2 initialization, that record remains v1 and is not silently converted. This edge needs improved atomic creation before general rollout.

V2 reports separate generic competencies from domain fundamentals/application with validated source IDs/quotes and model-assessed confidence. There is no approved new numerical weighting, so v2 reports use `score=null`, `scoring_status=not_scored`; the ASGI entry point strips placeholder legacy criterion numbers and renders evidence in the pilot report panel/ClickUp. Legacy recruiter lists still display Pending in the score column for unscored v2 reports; this label needs migration before general release. No automated hiring outcome.

## Voice implementation

- ASGI adapter (`backend.v2_stream:app`) mounts existing WSGI business logic; one process only.
- Same-origin WebSockets bound to authenticated candidate/application; periodic auth recheck, one active connection per application per process, bounded frames/messages, no provider credentials in browser. Upstream redirects are rejected. Raw mono 16-bit PCM at 16 kHz through AudioWorklet. Browsers unable to supply 16 kHz are rejected with a typing alternative, not silently mislabelled/resampled.
- Sarvam `saaras:v3-realtime`, provider VAD signals and final/interim utterances. Uses the documented `utterance_idx` and `text` contract; live event/entitlement verification still required. The REST TTS provider remains Bulbul v3 MP3. Never send WebM as PCM.
- One Begin/reconnect gesture requests mic consent. Spoken intro precedes question. Normal turns automatically switch from TTS to listening. Optional pause, finish and typing are retained.
- Six-second minimum hold AFTER both latest detected speech end and latest final transcript, with all partial utterances finalized. Initial silence never submits. An additional LLM completion check must agree; uncertainty waits and tries again no sooner than 15 seconds. Explicit finish bypasses semantic inference only once speech/finalization is idle.
- Speech resume invalidates pending checks/playback, stops TTS and returns to listening. Delayed old connection callbacks are detached on close. Headphones plus browser echo cancellation are required for initial tests; acoustic echo separation is NOT proven.
- If speech resumes while the answer commit request is in flight, the pilot pauses and asks to reload authoritative state rather than falsely claim rollback of a commit. Unsaved continuation retention/correction UI is NOT complete; this is a release blocker for seamless no-interruption operation.
- Streams reconnect between turns; bounded reconnect count 24, 30-minute per-connection time/audio budget, real-time PCM rate plus 2s burst slack. Exceeding budgets/connection loss pauses with an error rather than inventing answers. Long-session graceful warning, safe-boundary timeout behaviour, browser autoplay and automatic reconnection are still acceptance work.

## Quotas / cost / privacy

No live Sarvam calls were made during implementation. Existing MAX_AI_CALLS_PER_DAY remains unchanged; 30 may be insufficient for a full v2 voice interview because speech, streaming handshakes, end checks and optional clarifiers all count. Do not raise it silently or describe it as a billing cap. Agree a small staging budget/credits before testing. Realtime endpoint availability can differ from working REST access.

No raw audio retained by this code; bounded transient socket/audio buffers only. New v2 consent explicitly describes Sarvam, automatic capture/submission and ClickUp sharing. Existing v1 disclosure gap remains. Only fictional tests until retention/provider/bias/accessibility review. Neither automatic capture nor the LLM establishes anti-cheating or reliable personal-character judgements.

## Deployment gate

Do NOT deploy this branch to production or merge main. Do NOT replace the working role-management staging runtime until CI, snapshot/recovery, approved test usage and controlled voice test window are ready. A Gunicorn WSGI start command cannot serve this WebSocket bridge.

For an approved isolated staging test only, the required ASGI command is:

```
uvicorn backend.v2_stream:app --host 0.0.0.0 --port $PORT --workers 1
```

Build installs requirements.txt and runs backend tests plus the existing frontend build. Existing DATABASE_URL/Sarvam/admin/ClickUp secrets remain server-side and must not be copied to chat. Preserve root directory flashspace-recruitment. Backup the staging DB first. No paid resources or automated sync-watchdog activation is part of this branch.

Rollback restores feat/recruiter-role-management and backend.role_server:create_app() with its original Gunicorn flags. Do not delete interview_v2 or application data. Old code cannot operate v2 sessions and uses four-answer assumptions, so during rollback do not invite candidate use of v2 records; keep records for recovery under the v2 code. General release needs a backwards-compatible route/feature flag rather than relying on this pilot rollback alone.

## Automated verification scope

Pure question state tests: stage order, role filtering, budgets, persisted selection, no duplicate question IDs, replay, unknown role and stale state. WSGI tests: v1 compatibility, v2 ten-answer completion, ownership, explicit consent, bank authorization, committed answers before inference, failure fallback and atomic rollback. Disposable real PostgreSQL: v2 creation, answer progression, app recreation/resume, completion and mocked ClickUp sync. Evidence tests: quote/source stage checks, no aggregate score and empty evidence confidence. JS tests: 1/3/5 second pauses, initial silence, resume during processing, duplicate/late final events, paused callbacks. Stream tests: metadata filtering, redirect refusal and wrong-origin/invalid-auth rejection.

These tests do NOT establish live microphone accuracy, zero interruptions, actual browser UI behaviour, ASGI hosting behaviour, session authentication under a reverse proxy, or live Sarvam access. Frontend build verifies compilation, not microphone interactions.

## Remaining acceptance work

1. End-to-end browser tests with fake media and controlled Sarvam events; keyboard/mobile UI review and report label integration.
2. Live provider handshake/PCM contract smoke with synthetic audio, secure credentials and explicitly budgeted usage; verify end event shape and 16 kHz support.
3. Two fictional interviews in different role banks, with 1/3/5-second thinking pauses, quiet speech/noise/echo, resume during checks/TTS, reconnect, accessibility input and ten-to-fourteen saved answers.
4. Fix any timing/cancellation/continuation issues; integrate v2 into the ordinary Apply/Resume flow only when passing.
5. Staging PostgreSQL snapshot retention, ClickUp complete evidence/transcript verification, disclosure and operational readiness. Existing sync issue is independent and remains unresolved.
