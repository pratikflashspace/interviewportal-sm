# Interview-screen-first scope

Latest creator request: implement the AI interview screen first, based on Updates.docx and AI-Recruitment-System-UI.pdf. Work stays on feat/teamrecrut-separated-workspaces. No new dashboard/auth/database/provider changes in this UI increment, and no deployment performed.

The branch already contains the focused conversational page at /interview-v2?application=<saved-application>. This increment finishes its presentation, rather than creating another detached recorder or replacing live integration with a mock.

## Screen

- Paired interviewer waveform and candidate video; question directly below, then a clear state label.
- Use the actual .voice-viz classes emitted by VoiceVisualizer (not the incorrect .voice-visualizer selector), with flexible bars that fit mobile widths.
- 390px mobile keeps the paired view; very narrow 320px screens stack it to preserve legibility. Candidate video uses contain, avoiding unintended cropping.
- Preflight consent/device controls remain before Begin and disappear only after actual start. Retention disclosure is not hidden or deleted.
- Preserve existing automatic speech/listening/answer flow, internal question caps and two replay rule; no normal Pause/typing/per-answer recording controls.
- Question reveal uses current audio playback time, currently a conservative duration-based approximation, NOT provider-aligned word timestamps.
- Explicit interruption and completion states stay truthful. This styling does not fix the separately reported intermittent null recruiter-report issue.

## Verification

Repository source-contract tests plus an isolated screen harness for layout, preflight gating and empty/partial question presentation. Harness uses synthetic screen states, NOT camera capture, real Sarvam speech, persisted applications or recruiter-report validation. Full browser integration remains a separate CI gate; do not infer live readiness from screenshots.

## Deployment boundary

Existing approved new branch includes the broader workspace work already committed; deploying this branch deploys that whole state, not only the CSS/page increment. Do not claim an interview-only rollout of this branch. An interview-only rollout on the OLD live account/dashboard system would require a separately isolated release and navigation/auth compatibility work; do not silently change branch scope.

For the already approved full new-branch staging preview, use docs/STAGING-WORKSPACE-ACTIVATION.md AFTER current checks pass, staging backup/additive schema review is confirmed and TEAMRECRUT_STAGING_SCHEMA_APPROVED=true is explicitly acknowledged. Current Render tools cannot change branch/start command. No restore/delete/upgrade is required just to implement this screen. Do not deploy the new frontend alone against the old backend.
