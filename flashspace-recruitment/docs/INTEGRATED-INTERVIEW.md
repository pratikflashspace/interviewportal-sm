# Integrated interview correction — isolated branch, not deployed

Request: https://app.clickup.com/1851686/chat/r/1rg96-249156/t/80160053926220

## What this corrects
The user rejected a site-wide floating recorder. This branch has no RecordingDock in main.jsx. The self-preview is inside the candidate interview screen. A single Begin interview action acquires camera/microphone and starts application-owned capture, then introduction/questions. The recording spans question changes. The same microphone stream supplies STT while the recording receives the microphone plus a Web Audio mix of the interviewer's actual playback. Browser echo cancellation still requires real-device verification.

Root careers Apply routes new authenticated applications to the v2 room; existing v1 applications remain on their old four-question flow. V2 resumes route to their saved application. The root recruiter row opens that specific application's review page, which contains recording segments, transcript and evidence, not a general recording gallery. ClickUp receives a stable authenticated application review link. Existing recruiter role editing remains.

## Storage/security
Instance-local temporary storage, ten slots including incomplete, 50 MB each. Active capture time ceiling is 30 minutes to accommodate v2; the byte limit may be reached earlier. No durable recording guarantee. Download old staging recordings before any redeploy because the earlier temporary storage may disappear. No automatic file eviction. No Google OAuth or paid-resource setup in this correction.

New recording reservations require candidate ownership of an active v2 application plus explicit recording consent. Standalone POST /api/recordings is not exposed. Uploads validate ownership, same-origin headers, byte caps, sequence/hash replay and file signature. Ready state requires upload finalization. Server video playback/range access requires recruiter authentication. Metadata/listing is scoped to the application. Existing roles and applications are not deleted or silently converted.

Pause disables microphone/camera tracks, pauses the same MediaRecorder and suppresses question audio. Resume within that session reuses capture; question changes do not create a new recording. Finishing all answers finalizes recording upload. If leaving, a partial recording segment can be saved. A device/storage failure pauses the interview rather than recording silently offscreen. Partial uploads remain incomplete; local captured bytes can be downloaded.

## Important remaining work
- Real browser camera/autoplay/microphone/WebSocket event and audio-mix acceptance, quiet speech/echo/noise, device revocation and upload faults. CI uses mock tracks/audio graphs, not a real conversation.
- Speech resumption while an answer commit is already in-flight still pauses conservatively; it does not silently undo a durable answer. Seamless continuation/correction remains unimplemented.
- Integrated UI currently does not use the separate v2 draft-autosave client. Submitted answers survive; unsaved text during refresh is not promised to survive.
- Resume after ending/leaving a capture segment, permission-cancellation races and incomplete-upload management need browser acceptance before rollout. Old v1 sessions cannot be upgraded in place.
- New role bank mapping UI remains in the existing v2 pilot source rather than the new integrated room; surface it in recruiter management before enabling unmapped new roles. Never guess a bank based on a title.
- Candidate root routing carries role in query string; the integrated form still lets the candidate choose the role and needs query-prefill polish.
- Newly created reviewer route aggregates existing authorized admin APIs; no public media links. More targeted single-record retrieval can reduce data transfer later.

## Deployment boundary
Current working staging and its floating recorder are unchanged until controlled rollout. This branch is based on v2, not the temporary-recording staging merge; replacing that staging runtime will remove the floating UI but must preserve any needed downloaded recordings first.

Do not merge to main. Runtime for isolated staging acceptance is:

```
uvicorn backend.integrated_asgi:app --host 0.0.0.0 --port $PORT --workers 1
```

The existing Gunicorn WSGI command cannot serve streaming WebSockets. No Render settings, credentials, service plan or quota were changed in this run. Realtime Sarvam entitlement and approved usage budget must be validated; existing 30-call global staging quota may be insufficient for a complete 10–14 turn interview. Do not raise spend limits silently.

## Tests
Regression tests cover no-consent/no-capture, one capture across questions, audio routing to speakers plus recording, pause/resume track state, permission cancellation, failed upload status, candidate application binding, no standalone recording starts, ten-slot cap, private recruiter review, CSRF, chunk retries, byte ranges and ClickUp link formatting. Existing v2, role management and PostgreSQL CI continue running. Full media/browser tests are a release gate, not substituted by frontend compilation.
