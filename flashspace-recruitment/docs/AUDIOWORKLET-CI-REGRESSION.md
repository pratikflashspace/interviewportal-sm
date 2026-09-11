# AudioWorklet startup failure — test runner root cause

## Evidence

At ec223ff05a368497099896f4e22db5ec0745eff3 the isolated native probes in CI timed out on all of: URL/default sample rate, blob/default sample rate, blob/16 kHz, suspended URL context, and offline blob context. An earlier test also timed out with a connected silent audio graph while the context clock advanced. Fetching the worklet route returned 200 application/javascript. These ran on a bare local health page before any application diagnostics wrapper; neither interview state, candidate data nor Sarvam was involved.

The pinned test dependency was Playwright 1.55.1. Upstream documents the exact regression: https://github.com/microsoft/playwright/issues/37592 (AudioWorklet addModule hangs under Playwright 1.55.1, fixed for 1.56 via revert of auto-attach filtering). Stable release checked: https://github.com/microsoft/playwright/releases/tag/v1.56.1 .

## Fix and verification

Updated only the Playwright development dependency from 1.55.1 to 1.56.1. Production audio, authorization, consent, recording limits and the existing 10-second application safety timeout were NOT disabled or relaxed.

At 450fb528879e6ddc5fe0bd468f0f83fec31e4487, with unchanged application code and unchanged full interview assertions:
- Backend checks PASS: https://github.com/pratikflashspace/interviewportal-sm/actions/runs/34595433904/job/103249983935
- Frontend build + postbuild Chromium integration PASS: https://github.com/pratikflashspace/interviewportal-sm/actions/runs/34595433812/job/103249983024

Replaced temporary diagnostic permutations with a permanent native regression assertion: load the real local PCM worklet within 3 seconds, instantiate the node, and require a nonzero 640-byte PCM frame at 16 kHz. All nodes/context are cleaned up. Then run the unchanged full browser journey.

The full journey uses actual Chromium, local ASGI/WSGI, SQLite, cookies, profile persistence, Apply, local device checks, AudioWorklet, MediaRecorder upload, protected media download/decoding, candidate-access rejection and ten automatic answer transitions. Sarvam speech/events/evaluation and ClickUp network calls are SYNTHETIC test boundaries, not real-provider acceptance.

## Scope and next step

This resolves the reproduced CI startup blocker, not every possible real-device speech issue. It does not show that a user's browser had the same cause. No deployment, real account provisioning, environment changes or live-provider testing was done.

Next work remains resume upload/storage, candidate OAuth/recovery, PostgreSQL/backup/security review and an explicitly approved staging test with real Sarvam and ClickUp. MFA stays deferred. Draft PR #15 must not merge into main.
