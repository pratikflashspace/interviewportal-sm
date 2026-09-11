# Integrated interview release candidate — staging handoff

No further product-scope approval is required. This branch replaces the rejected floating recording UI with an interview-owned camera/voice flow; it has not yet replaced the currently deployed website.

## Updates
- Personal recorder capture lifecycle handles cancellation during permission and slot setup, marks failed slots incomplete, releases all device/audio-graph resources, and bounds queued uploads.
- Begin/Resume preserves an active recording session. A finished segment permits a new segment rather than permanently blocking the interview. Recovery of abandoned sessions requires explicit owner confirmation; no file is automatically deleted.
- Integrated room restores/saves finalized answer drafts through the existing revision-checked API. Drafts remain separate from submitted evidence and raw audio.
- Role query selection is carried from Apply; recruiter bank mapping controls are present in the integrated room. Unknown roles cannot silently inherit the Sales bank.
- Continued speech during a nonfinal answer commit is captured instead of cutting off the mic; the next TTS is suppressed. A continuation may append to the last saved answer only before the next question is delivered. Ownership, version and original-text preservation are checked server-side.
- The final-answer race still needs a reviewer/manual recovery path: completed reports are not silently rewritten if the candidate resumes after the final commit. UI pauses and retains the recording; do not call this zero-interruption perfection.

## Verification performed
Frontend build/backend CI run on the PR. Fake-media regression tests cover consent, pause/resume, shared audio graph, cancellation after permission and slot creation, upload failures and new capture segments. Auth tests cover continuation before next-question delivery, stale/cross-owner access, recording abort and slot retention.

A managed Chromium test created a real WebM from synthetic canvas video and Web Audio microphone/interviewer signals, paused/resumed MediaRecorder, and played the resulting 320x240 recording successfully (approximately 51 KB). This validates the browser media pipeline primitives, not full React UI interactions, real camera permission, echo rejection, speech turn quality, or live provider access. No applicant content was used and no synthetic recording was uploaded to a live server.

## Deployment settings required
The available Render integration cannot edit branch or start command. A trigger_deploy call would only redeploy the old WSGI configuration. Do not claim it activates this branch.

On the existing isolated staging service only:
- Branch: feat/integrated-interview-recording
- Root: flashspace-recruitment (unchanged)
- Start command: `uvicorn backend.interview_release_asgi:app --host 0.0.0.0 --port $PORT --workers 1`
- Build command and existing database/admin/Sarvam/ClickUp credentials unchanged.

This uses ASGI for WebSockets; the old Gunicorn WSGI command cannot serve live speech. Do not start multiple processes. Preserve the staging database recovery snapshot; download existing temporary recordings before changing settings, as they can disappear during a redeploy. If a settings save starts a deployment, do not trigger another.

## Controlled staging acceptance
Only fictional test candidates. Verify correct commit/runtime, startup, /api/health and existing published roles. Test one new mapped application from Apply, explicit recording consent, inline preview, one Begin action, automatic question playback/listening, six generic then four domain questions with bounded clarifiers, two replays, draft refresh, pause/resume and same-session video upload. Review its transcript/video/evidence and protected ClickUp review link as recruiter; candidate/anonymous media access must fail. Validate actual Sarvam realtime entitlement and quota without exposing keys or raising limits silently.

The existing global MAX_AI_CALLS_PER_DAY may be insufficient for a full long v2 interview. If exhausted, stop and get explicit budget approval; do not bypass the limit to make acceptance look successful. Free-tier sleeping and earlier background-sync issues are independent limitations.

Keep production main unchanged. Do not automatically downgrade a v2 application into a four-question flow. On failed rollout restore the prior staging branch/start configuration; preserve database records and clearly mark v2 sessions unavailable until recovery. Old temporary-video links are not a backup.
