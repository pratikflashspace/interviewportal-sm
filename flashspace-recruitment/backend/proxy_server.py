"""Explicit staging-only entry point; existing direct-provider entry points unchanged."""
from .server import AI, APIError
from .durable_server import DurableInterviewApp
from .workers_proxy import WorkersProxyProvider


class ProxyAI(AI):
    def __init__(self):
        # Inherit question/report validation, never initialize direct Cloudflare access.
        self.provider = WorkersProxyProvider(APIError)


def create_app():
    return DurableInterviewApp(ai=ProxyAI())
