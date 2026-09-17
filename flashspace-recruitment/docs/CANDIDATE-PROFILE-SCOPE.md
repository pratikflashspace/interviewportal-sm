# Candidate My Profile — branch-only section editor

Approved DM 80160054313034 in response to proposal 80160054312791. Only candidate /candidate/workspace/profile redesign and its required profile persistence/compatibility code. No deployment, Google/provider changes, recruiter UI redesign or actual resume upload.

## Sections

Personal name/phone/city/headline, read-only login email; summary; up to 12 repeatable education, experience, project and certification entries; up to 40 skill tags; portfolio/LinkedIn/GitHub HTTPS links; preferred roles/locations/work mode/type/availability; resume LINK only. Education/experience support current activity and validate chronological dates. No experience yet is optional, with no suitability penalty. It cannot contradict preserved legacy experience text. No protected-trait or government-ID fields.

Each section has Edit/Save/Cancel; entries may be added or removed from drafts and are only persisted on Save. Existing saved free text is displayed verbatim, separately from new entries, and never guessed into structured records or silently erased. Legacy-text editing/removal is not added by this iteration. Optional grade and sections remain optional. New structured records are stored within existing workspace_profiles JSON under _candidate_sections. There is no new table/DDL or migration/backfill. Existing profile-wide version ensures conflict detection with old editors. Atomic name/profile persistence; old Resume link writes preserve all structured sections. A read-only compatibility projection exposes supplied structured section text to existing dashboard/recruiter consumers without writing the projection back over original text. Existing recommendation logic remains applied-role based, not profile-driven.

## Security and reliability

Only authenticated candidate current_user can access /api/workspace/candidate/profile; client-supplied user IDs/role/email fields are rejected. Fields are allowlisted and length/type bounded. HTTPS links cannot contain credentials or whitespace and are never fetched. Text is escaped by React, not rendered as HTML. A 32 KiB existing request limit and 200 KB total JSON ceiling remain; large entries may need shortening. No actual keys or passwords are added. No browser storage of profile drafts.

Failed saves retain fields and never display success. Network calls are bounded and cancellable. One active editor reduces accidental overwrite; unsaved navigation/cancel requires confirmation. On 409 conflict, keep draft, disable Save and offer a read-only latest-section preview; replacing draft with latest requires explicit confirmation. Cancel also confirms discarding modifications. Session expiry does not silently discard the active draft. Existing free-text editing APIs cannot overwrite structured sections. Login email/role are not writable.

## Verification

Real WSGI/SQLite section persistence, own-candidate isolation, recruiter denial, CSRF, old-text preservation, legacy resume compatibility, malformed/date/link validation and stale versions. Disposable localhost PostgreSQL tests for restart and cross-instance CAS. Node request/link/default tests. Chromium uses real local backend/profile database with synthetic accounts and controlled outage injection for retained drafts, retry and conflict resolution. Existing full interview journey remains enabled and only profile navigation steps change to explicit section Edit. Report/sync blocker is not modified or waived.

This is not a live staging release. Existing deployment backup/schema review and ephemeral recording warnings still apply to the broader branch. Google activation, resume private-file upload, email change verification, recruiter redesign and profile-based recommendations remain outside scope.
