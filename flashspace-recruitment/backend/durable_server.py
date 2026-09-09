"""Opt-in staging entry point. Existing production entry point is unchanged.

Run one worker, as required by the base app's in-process mutation lock:
    gunicorn 'backend.durable_server:create_app()' --workers 1 --threads 8
"""
import re
from .server import App, APIError, now, public_app, text
from .interview_turns import save_answer


class DurableInterviewApp(App):
    def route(self, env, body):
        match = re.fullmatch(r'/api/applications/([\w-]+)/answer', env.get('PATH_INFO', '/'))
        if env.get('REQUEST_METHOD') == 'POST' and match:
            user = self.current_user(env)
            with self.lock:
                saved = save_answer(self, match[1], user['id'], body, APIError, text, now)
                return public_app(saved), []
        return super().route(env, body)


def create_app():
    return DurableInterviewApp()
