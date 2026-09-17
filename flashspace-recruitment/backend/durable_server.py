"""Opt-in staging entry point. Existing production entry point is unchanged.

Run one worker, as required by the base app's in-process mutation lock:
    gunicorn 'backend.durable_server:create_app()' --workers 1 --threads 8
"""
import re
from .server import App, APIError, now, public_app, text
from .interview_turns import save_answer


class DurableInterviewApp(App):
    def route(self, env, body):
        path = env.get('PATH_INFO', '/')
        method = env.get('REQUEST_METHOD')
        match = re.fullmatch(r'/api/applications/([\w-]+)/answer', path)
        if method == 'POST' and match:
            user = self.current_user(env)
            with self.lock:
                saved = save_answer(self, match[1], user['id'], body, APIError, text, now)
                return public_app(saved), []
        if method == 'GET' and path in ('/api/applications', '/api/admin/applications'):
            # Do not expose a temporary standard question from a concurrent tab
            # while successful inference is about to replace it. After a process
            # restart the committed standard question is safe to serve as-is.
            with self.lock:
                return super().route(env, body)
        return super().route(env, body)


def create_app():
    return DurableInterviewApp()
