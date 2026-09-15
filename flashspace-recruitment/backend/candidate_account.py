"""Candidate account settings. No new tables, email delivery or provisioning."""
from .candidate_google import WorkspaceApp as GoogleWorkspaceApp
from .server import APIError

class WorkspaceApp(GoogleWorkspaceApp):
    def google_account(self, user):
        with self.store.db() as db:
            return db.execute('SELECT user_id FROM candidate_google_identities WHERE user_id=?', (user['id'],)).fetchone() is not None

    def route(self, env, body):
        path=env.get('PATH_INFO','')
        if path=='/api/workspace/candidate/account':
            user=self.current_user(env)
            if env.get('REQUEST_METHOD')!='GET':raise APIError(405,'GET required.')
            google=self.google_account(user)
            return {'email':user['email'],'role':'candidate','auth_method':'google' if google else 'password','password_change_allowed':not google},[]
        if path=='/api/workspace/password' and env.get('REQUEST_METHOD')=='POST':
            user=self.current_user(env)
            if not user['admin'] and self.google_account(user):
                raise APIError(409,'This account uses Google sign-in. Manage your Google password through Google.')
        return super().route(env,body)
