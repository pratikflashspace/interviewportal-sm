# Integrated staging AI usage correction

The user requested removal of the application usage limits after the live log confirmed `voice_failed phase=quota reason=usage_limit_reached`.

## Cause and scope

The old policy charges `global-ai` before each per-application action counter, including reconnect attempts that never reach Sarvam. The global counter uses MAX_AI_CALLS_PER_DAY (code default 500; historical staging configuration reported 30, not re-read here). Action counters last seven days: voice 24, introduction 5, speech 42, turn-end checks 50, followups 10, evaluation 20. These are application safeguards, not Sarvam credit balances. Logs prove a local quota rejection, not which old counter was exhausted.

Only InterviewRelease opts into the new V2UsagePolicy. V2 voice, intro, TTS, end-checks, followups and v2 evaluation no longer consult global daily or per-action seven-day counters. Existing counters and candidate data are not deleted or reset. Legacy v1 behavior is preserved. Main is not a deployment target.

## Retained protection

A shared application bucket permits 20 AI operation attempts per 60-second window; the integrated v2 workspace bucket permits 120 per 60-second window. Windows begin with the first request, not calendar-minute boundaries. These are burst controls, NOT daily budgets. Errors and attempts may count. Store.quota remains the atomic SQLite/PostgreSQL implementation; no new schema or raw SQL is introduced. No long-term cost ceiling remains for integrated v2 at application level, so sustained use can increase Sarvam charges. Provider credits and provider rate limits still apply.

Origin, login, application ownership, active-interview checks, single active socket, bounded frames/stream duration, two question replays, answer limits and temporary video capacity remain unchanged. Removing AI counters does not remove the 10-recording/50MB video storage constraints.

## Validation and rollback

Tests cover exhausted historical counters, all v2 actions and report evaluation, over 24 reconnects across time windows, burst rejection/expiry, global scope, v1 fallback and database error propagation. Existing bridge and replay tests must pass too. Live media E2E is not established by these tests.

Deploy only to the approved staging branch after CI. Replacing the instance may lose temporary recordings. To roll back, revert the policy integration in InterviewRelease through a tested PR; historical counters will then apply again. Do not wipe quotas to work around errors.
