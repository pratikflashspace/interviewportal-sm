# Corrected application-owned interview recording

Requested correction: candidate applies, enters THAT interview, grants consent and device permission once, sees self-preview inside the interview, answers voice questions, and the recording stays with the application for human review. A floating/global recorder is explicitly not wanted.

## Delivered wiring
- main.jsx no longer mounts RecordingDock. Old source files are inert, not imported.
- Existing Apply and Resume render IntegratedInterview through the same exported Interview component. No candidate selects another application for recording.
- Begin starts camera and microphone and allocates an application-bound segment before question audio plays. A continuous MediaRecorder records webcam + mixed candidate microphone and decoded interviewer TTS audio using Web Audio. Self-preview is local/muted.
- Question playback ends -> listening starts automatically. Local speech activity plus six seconds quiet -> transcribe finalized short audio parts -> semantic completion check -> save answer -> next spoken question. I’m finished is optional, not a mandatory per-turn recording-start step.
- STT remains the existing Sarvam REST adapter, split into <=20-second media clips while recording video continuously. This is not the separate realtime WebSocket v2. Clip rollover may have a small capture gap and must be evaluated on real devices. Short speech/noise detection uses a basic RMS threshold, not a calibrated VAD model.
- Four-question existing sessions remain four questions. Two-stage 6+4 bank logic remains separate/unreleased. Do not call this correction a completed v2 release.
- Pause stops camera/audio and finalizes the current recording segment. Resume uses the SAME application and a new segment. All segments appear together in recruiter review. Final interview submission waits for recording upload finalization. Browser local download available when a segment stops.
- Device loss, capture/size/time limits and upload errors pause rather than report a successful complete recording. Temporary recordings remain limited to ten slots, 50 MB and ten minutes per segment; this is not a long-term archive.
- Recruiter application modal has a Recording tab, filtered server-side by application. ClickUp gets a stable /recordings?application=<id> login-protected link. Candidate media uploads are owner-bound; server playback requires recruiter authorization.
- Three server speech deliveries per question (initial + two replays); attempts may count even if playback fails. Repeat allowance is persistent, not reset by refresh.

## Validation
Existing backend/database tests plus active-interview capture gates, single unfinished segment per application, private scoped review, replay allowance, mixed-audio media lifecycle and cleanup. Frontend CI also launches real Chromium with synthetic camera/mic and mocked APIs to test one Begin -> live preview -> four answers -> recording finalization -> submission and application-specific reviewer UI. This does not prove live Sarvam, physical microphone/echo behaviour or temporary-storage durability.

## Deployment
Staging only: merge tested branch into feat/recruiter-role-management after passing CI. Existing role_server:create_app entrypoint delegates to IntegratedApp; no manual Render settings change needed. Production main unchanged. Deploy/replacement can remove temporary existing recording files: do not claim preservation of those videos. Database applications/roles/transcripts remain unchanged in storage design.

## Known pilot limits
Background sync remains the existing implementation with its earlier stall risk. No Google Drive account/access/storage change. Existing pending/incomplete segments may require recruiter removal before starting a new segment; no auto-delete/eviction. Browser permission failures and overloaded networks require retry/reconnect after inspecting errors. Automatic endpointing is conservative but cannot guarantee zero false cuts or perfect end-of-answer detection. Use fictional data only until physical-device acceptance and a durable retention plan are approved.
