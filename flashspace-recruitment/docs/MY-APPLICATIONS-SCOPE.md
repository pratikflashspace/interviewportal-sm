# My Applications — approved candidate page only

Approval DM 80160054304623 responding to proposal 80160054302802. Existing feat/teamrecrut-separated-workspaces branch; only /candidate/workspace/applications is routed to the new component. All other pages, database schemas, provider configurations and deployments are untouched.

## Data and behavior

Uses /api/me then /api/workspace/candidate/applications, with stored candidate role/admin=false required before loading or rendering records. Existing backend owns authorization and candidate filtering. Whitelisted response projection excludes AI evaluations, internal confidence/scores, actor IDs and notes. No client-supplied candidate IDs. Newest valid application dates first; unknown dates last, with Date not recorded rather than fabricated dates. Search by role; filter current recorded hiring/interview statuses; actual counts and clear filters.

Preserve candidate shell, purple/lilac cards, fixed desktop sidebar, responsive mobile navigation, top-right My Profile. Existing Resume link-only disclosure is unchanged. View application modal uses existing Dialog primitives, focus management and visual style. Status refresh/loading/error/empty states remain explicit; failed loads never become empty success.

## Factual history

Submission timestamp is stored. Recruiter stage events include recorded timestamps where present. No eligibility, assessment or implied future events are added. Existing API reports under_review as the default for completed interviews even before a recruiter decision. When version=0, present this as Awaiting recruiter review and do not create a review event. Explicit under_review records remain Under review. Contacted is a recorded status, not proof an email was sent. Hired is not relabelled Offer made.

The current tracking endpoint has no interview completion timestamp. Completed status is displayed separately as an undated confirmed milestone, with that limitation explained; neither last answer nor application time is substituted. Unknown event dates are explicitly undated and not placed in a fabricated chronology.

Continue interview requires unfinished interview status and recognized flow version, with no terminal rejected/hired state. Re-fetch candidate applications immediately before navigating to its existing v2/preflight or legacy route; a stale completed card cannot restart an interview. Completed application detail has no continuation button. The underlying interview endpoint independently enforces ownership/state. No new interview session or application is created from this page.

## Verification

Nine Node logic/transport tests; three Python scope/real WSGI tests for persisted events and candidate isolation. Isolated Chromium cases cover sorting, search/status filters, factual and undated timeline, no internal content, no restart, stale-status revalidation, access denial, errors and mobile layouts. Synthetic test data is not live staging verification. Existing broader report/sync browser failure remains a separate release blocker. No deployment or live login/Google validation is claimed.
