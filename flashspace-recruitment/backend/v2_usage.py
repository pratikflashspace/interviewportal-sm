"""V2 pilot usage policy: no daily/seven-day call-count lockouts.

Only the integrated release opts in. Authentication, question replays, media
bounds, and provider quotas are separate and remain enforced.
"""
import logging
from .server import APIError

LOG = logging.getLogger('flashspace.voice')

class V2UsagePolicy:
    def ai_quota(self, a, kind, limit):
        answers = a.get('answers') or []
        is_v2 = kind.endswith('-v2') or (
            kind == 'evaluation' and answers and answers[0].get('flow_version') == 2)
        if not is_v2:
            return super().ai_quota(a, kind, limit)
        # New keys intentionally do not consult or erase old cumulative counters.
        # One shared application bucket prevents bypass by alternating operations.
        # Sizing: a full v2 interview costs ~2 AI calls per question (speech +
        # follow-up) plus voice-session reconnects and the intro. The largest
        # bank (design, 13 questions) needs ~30-35 calls at maximum answering
        # speed; 40 lets a fast candidate finish inside one window while the
        # 60-second reset still bounds abuse. Staged mid-interview 429s were
        # stopping real interviews at question ~7-8 (2026-09-22).
        for key, maximum, scope in (
            ('v2-burst:application:' + a['id'], 40, 'application'),
            ('v2-burst:global', 180, 'workspace'),
        ):
            try:
                self.store.quota(key, maximum, 60)
            except APIError as exc:
                if exc.status != 429:
                    raise
                LOG.warning('voice_usage_throttled scope=%s window_seconds=60', scope)
                raise APIError(429, 'Too many interview AI requests in a short time. Wait one minute before resuming.') from None
