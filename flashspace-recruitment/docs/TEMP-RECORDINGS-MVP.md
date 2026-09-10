# Temporary ten-recording MVP

Supersedes Google Drive/OAuth setup for the immediate MVP. No Google account, Cloud Console, refresh token, storage provider or paid plan is required.

The current working role-management branch is the baseline. Keep unfinished v2 conversational voice changes separate; this addition records alongside the already working interview. After tests pass, merge only into feat/recruiter-role-management (the staging deployment branch), never main. The unchanged Render start command backend.role_server:create_app() now lazily delegates to the recording-capable subclass. A merge/push to that staging branch automatically deploys; do not trigger a duplicate deploy.

## Candidate usage
Log in, create/resume a test application, open the Camera recording dock at bottom right, select that application, accept the explicit temporary-recording notice, and click Enable camera & start recording. Browser camera/microphone consent and a live self-preview are shown. Continue the interview in the SAME tab. Capture stops on Stop or at the 10-minute MVP limit; application completion is checked every five seconds and stops an active recording for an application that was unfinished at recording start. If already completed when selected, stop manually.

Recording starts once for the interview, not once per answer. The existing interview UI still controls answer transcription independently. Camera video and candidate mic audio are captured. Clean interviewer TTS audio is not guaranteed; transcript provides questions. No automatic face/emotion/anti-cheating assessment is included.

## Storage and limits
Up to 10 stored or incomplete recording slots per instance; 50 MB each, max 500 MB video content. Low-bitrate 640x480/15fps requested; actual codec/device settings vary. Files are outside public web/dist and require authenticated access. Active capture shows elapsed seconds. Automatic stopping at 10 minutes stops video capture, not the interview or its saved answers. All recordings are temporary and can disappear on instance replacement/redeploy/restart. This is not durable storage, a backup, or production retention compliance. Do not use real candidates yet.

Chunks upload sequentially with bounded request size and hash-checked retry idempotency. Ready status requires an explicit finish after uploaded part count matches. Incomplete sessions consume a slot; there is no silent eviction. An authorized recruiter can download then remove a slot. Server deletion is irreversible; UI asks confirmation. Byte-range responses support video seeking.

The candidate gets a local browser download after stopping even when server upload fails, for whatever captured bytes remain available in the tab. Closing/reloading before upload and download complete can lose data. No cross-device/page-reload upload recovery is claimed. Browser memory holds at most the configured recording cap, but recording/video encoding overhead is additional.

## Recruiter review / ClickUp
Recruiter logs into the website, opens MVP recordings (or /recordings), plays/downloads ready videos, and removes copies only after saving what is needed. Each row identifies the application. No public media links: candidate owner can upload, recruiter can play/download server copies. The candidate uses their own local download.

On completion the app persists recording_review_url into the application and queues normal ClickUp synchronization. ClickUp description gets an authenticated /recordings?recording=<id> review link. The review page lists accessible recordings; it does not bypass login. An expired/lost temporary recording returns not found even if the old ClickUp link remains. Existing sync delay/retry issues are not resolved by this feature.

## Tests / rollout
Backend tests cover ten-slot cap/no eviction, container validation, chunk size, idempotency/conflicts, unfinished upload rejection, manifest persistence on the same disk, candidate ownership, recruiter playback/delete access, CSRF, recording consent, range reads and same-origin camera policy. Full frontend build runs in CI. Actual camera/mic/codec playback acceptance still requires a browser test after controlled staging deployment.

Production/main and the old Cloudflare branch remain unchanged. No database schema migration is added by recording storage itself; a review URL is stored in existing application JSON. Existing role-management migrations are unchanged. To roll back, restore the previous staging code commit 4cb4966be8e8daf6b348a12b9e3f7e7c3b9601b4; download temporary recordings before any redeploy. Never promise recordings will survive rollback.

Google Drive preparation remains on separate feat/personal-drive-recordings and is not part of this feature. Do not execute its OAuth utility for this MVP.
