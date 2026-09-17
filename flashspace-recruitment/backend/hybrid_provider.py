"""Hybrid provider for the v2 conversational interview (approved 15 September 2026).

LLM layer (structured calls: end-of-turn decisions, follow-up selection, evidence
reports) goes to Cloudflare Workers AI via the approved proxy; realtime STT and
TTS stay on Sarvam, which is verified working on staging. No direct Cloudflare
account calls, no credential logging, no automatic provider fallback.

Every existing call site routes structured calls through self.provider.structured,
so the hybrid swaps only that one method; speech() and transcribe() stay Sarvam.
"""
import os

from .sarvam_provider import SarvamProvider
from .v2_endpoint import EvidenceOnlyAI
from .workers_proxy import ENDPOINT, WorkersProxyProvider
from .server import APIError


class HybridSarvamProvider(SarvamProvider):
    """Sarvam voice pipeline with the LLM layer routed to the Workers AI proxy."""

    def __init__(self, error_type):
        super().__init__(error_type)
        self.llm = WorkersProxyProvider(error_type)

    def structured(self, system, payload, name, schema):
        # LLM layer only: end-of-turn, follow-up choice, evidence reports.
        # speech() and transcribe() remain inherited from SarvamProvider.
        return self.llm.structured(system, payload, name, schema)


class HybridEvidenceAI(EvidenceOnlyAI):
    """Evidence-only v2 AI on the hybrid provider (Sarvam voice + proxy LLM)."""

    def __init__(self):
        self.provider = HybridSarvamProvider(APIError)


def hybrid_ai_or_evidence_only():
    """Hybrid AI when the proxy token is configured; otherwise the pure Sarvam AI.

    Keeps every entry point unchanged until the operator adds
    PRATIK_WORKERS_AI_TOKEN on Render; pure-Sarvam behaviour is preserved.
    """
    token = os.getenv('PRATIK_WORKERS_AI_TOKEN', '').strip()
    if token and os.getenv('PRATIK_WORKERS_AI_URL', ENDPOINT).strip() == ENDPOINT:
        return HybridEvidenceAI()
    return EvidenceOnlyAI()
