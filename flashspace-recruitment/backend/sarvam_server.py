"""Explicit Sarvam staging entry point. Cloudflare/proxy entry points unchanged."""
from .server import AI, APIError
from .durable_server import DurableInterviewApp
from .sarvam_provider import SarvamProvider


class SarvamAI(AI):
    def __init__(self):
        # Reuse question, quote, score and fairness guardrails, not Cloudflare auth.
        self.provider = SarvamProvider(APIError)

    def evaluate(self, role, answers):
        report = super().evaluate(role, answers)
        report['provider'] = 'sarvam'
        report['rubric_version'] = 'flashspace-sarvam-v1'
        return report


def create_app():
    return DurableInterviewApp(ai=SarvamAI())
