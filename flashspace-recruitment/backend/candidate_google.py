"""Candidate-only GIS callback. No credentials, provisioning, or deployment.
Activation requires explicit environment configuration after provider validation.
Use Google's maintained verifier, never tokeninfo URLs or unverified JWT decode.
"""
import hmac
import os
import re
import secrets
import time
import uuid
from http.cookies import SimpleCookie
from .workspace_server import WorkspaceApp as ManualWorkspaceApp
from .server import APIError, digest, hash_password, now

CLIENT_ID = '705165273628-eeeh6ivo3rv28o5rkasbmv2nib3an3p1.apps.googleusercontent.com'
COOKIE = '__Host-tr_google_challenge'
BASE = '/api/auth/candidate/google'


def verify_google_credential(credential, audience):
    # Lazy imports leave manual login usable when Google is disabled.
    from google.oauth2 import id_token
    from google.auth.transport.requests import Request
    from google.auth.exceptions import TransportError
    import requests
    class BoundedRequest(Request):
        def __call__(self, *args, **kwargs):
            kwargs['timeout'] = 5
            kwargs['allow_redirects'] = False
            return super().__call__(*args, **kwargs)
    try:
        with requests.Session() as session:
            return id_token.verify_oauth2_token(credential, BoundedRequest(session=session), audience, clock_skew_in_seconds=0)
    except ValueError:
        raise APIError(401, 'Google sign-in could not be verified. Please try again.') from None
    except (TransportError, requests.RequestException):
        raise APIError(503, 'Google verification is temporarily unavailable. Use email and password or try again later.') from None


def validate_identity(claims, nonce, audience):
    if not isinstance(claims, dict):
        raise APIError(401, 'Invalid Google identity.')
    current = time.time()
    if (claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com')
            or claims.get('aud') != audience or claims.get('azp', audience) != audience
            or type(claims.get('exp')) not in (int, float) or claims['exp'] <= current
            or type(claims.get('iat')) not in (int, float) or claims['iat'] > current
            or not isinstance(claims.get('nonce'), str)
            or not hmac.compare_digest(claims['nonce'], nonce)
            or claims.get('email_verified') is not True):
        raise APIError(401, 'Google sign-in could not be verified. Please try again.')
    subject = claims.get('sub')
    email = claims.get('email')
    if (not isinstance(subject, str) or not 1 <= len(subject) <= 255
            or not isinstance(email, str) or len(email) > 254
            or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)):
        raise APIError(401, 'Invalid Google identity.')
    email = email.strip().lower()
    # For third-party email addresses Google is not authoritative. No silent
    # ownership assumption: candidate must use the manual registration flow.
    hd = claims.get('hd')
    if not email.endswith('@gmail.com') and not (isinstance(hd, str) and hd and email.rsplit('@', 1)[1] == hd.lower()):
        raise APIError(409, 'Use email and password for this account. Google email ownership needs additional verification.')
    name = claims.get('name')
    name = name.strip()[:100] if isinstance(name, str) else ''
    return subject, email, name if len(name) >= 2 else 'Candidate'


class WorkspaceApp(ManualWorkspaceApp):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with self.store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS candidate_google_identities (subject TEXT PRIMARY KEY, user_id TEXT UNIQUE NOT NULL REFERENCES users(id), created TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS candidate_google_challenges (token_hash TEXT PRIMARY KEY, expires REAL NOT NULL)')

    def google_enabled(self):
        return (self.secure and os.getenv('TEAMRECRUT_CANDIDATE_GOOGLE_ENABLED') == 'true'
                and os.getenv('GOOGLE_CLIENT_ID') == CLIENT_ID
                and os.getenv('TEAMRECRUT_GOOGLE_VERIFIED_ORIGIN') == self.origin)

    def challenge_cookie(self, token, age=300):
        return ('Set-Cookie', f'{COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={age}')

    def challenge_token(self, env):
        cookies = SimpleCookie()
        try:
            cookies.load(env.get('HTTP_COOKIE', ''))
            item = cookies.get(COOKIE)
            token = item.value if item else ''
        except Exception:
            token = ''
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise APIError(401, 'Google sign-in expired. Reload Google sign-in and try again.')
        return token

    def google_login(self, env, body):
        if set(body) != {'credential'} or not isinstance(body.get('credential'), str) or not 100 <= len(body['credential']) <= 16000:
            raise APIError(400, 'Invalid Google sign-in request.')
        token = self.challenge_token(env)
        # Atomic one-use claim before remote verification. Rejected tokens and
        # provider outages require a fresh challenge; no replay or automatic retry.
        with self.store.db() as db:
            row = db.execute('DELETE FROM candidate_google_challenges WHERE token_hash=? AND expires>? RETURNING token_hash', (digest(token), time.time())).fetchone()
        if not row:
            raise APIError(401, 'Google sign-in expired. Reload Google sign-in and try again.')
        claims = verify_google_credential(body['credential'], CLIENT_ID)
        subject, email, name = validate_identity(claims, digest(token), CLIENT_ID)
        self.store.quota('google-email:' + digest(email), 10, 600)
        if email == self.recruiter_email():
            raise APIError(403, 'Google sign-in is for candidate accounts only.')
        with self.lock, self.store.db() as db:
            linked = db.execute('SELECT users.* FROM candidate_google_identities JOIN users ON users.id=candidate_google_identities.user_id WHERE subject=?', (subject,)).fetchone()
            if linked:
                user = dict(linked)
                # Never silently change an existing identity's email or role.
                if user['admin'] or user['email'].strip().lower() != email:
                    raise APIError(403, 'This Google identity cannot access this candidate account. Contact the hiring team.')
            else:
                existing = db.execute('SELECT id FROM users WHERE LOWER(TRIM(email))=?', (email,)).fetchone()
                if existing:
                    raise APIError(409, 'Use email and password for this account. Existing accounts are not automatically linked to Google.')
                user = {'id':str(uuid.uuid4()), 'email':email, 'name':name, 'admin':0}
                # Non-recoverable random password, never returned or retained.
                db.execute('INSERT INTO users VALUES (?,?,?,?,0,?)', (user['id'], email, name, hash_password(secrets.token_urlsafe(64)), now()))
                db.execute('INSERT INTO candidate_google_identities VALUES (?,?,?)', (subject, user['id'], now()))
        return self.user_json(user), [self.session(user), self.challenge_cookie('', 0)]

    def route(self, env, body):
        path = env.get('PATH_INFO', '')
        if path not in (BASE, BASE + '/config', BASE + '/challenge'):
            return super().route(env, body)
        method = env.get('REQUEST_METHOD')
        if path.endswith('/config'):
            if method != 'GET':
                raise APIError(405, 'GET required.')
            return {'enabled':self.google_enabled()}, []
        if method != 'POST':
            raise APIError(405, 'POST required.')
        if not self.google_enabled():
            raise APIError(503, 'Google sign-in is pending configuration. Use email and password.')
        self.store.quota('google-auth-ip:' + env.get('REMOTE_ADDR', 'unknown'), 20, 600)
        existing = self.current_user({**env, 'PATH_INFO':'/api/me'}, False)
        if existing:
            raise APIError(409, 'Sign out before using another sign-in method.')
        if path.endswith('/challenge'):
            if body:
                raise APIError(400, 'Invalid challenge request.')
            token = secrets.token_urlsafe(32)
            with self.store.db() as db:
                db.execute('DELETE FROM candidate_google_challenges WHERE expires<=?', (time.time(),))
                try:
                    old = self.challenge_token(env)
                except APIError:
                    old = None
                if old:
                    db.execute('DELETE FROM candidate_google_challenges WHERE token_hash=?', (digest(old),))
                db.execute('INSERT INTO candidate_google_challenges VALUES (?,?)', (digest(token), time.time()+300))
            return {'client_id':CLIENT_ID, 'nonce':digest(token), 'expires_in':300}, [self.challenge_cookie(token)]
        return self.google_login(env, body)

    def __call__(self, env, start_response):
        def headers(status, items):
            if env.get('PATH_INFO') == '/candidate/login' and self.google_enabled():
                adjusted = []
                for key, value in items:
                    if key.lower() == 'content-security-policy':
                        value = value.replace("script-src 'self'", "script-src 'self' https://accounts.google.com/gsi/client")
                        value = value.replace("style-src 'self'", "style-src https://accounts.google.com/gsi/style 'self'")
                        value = value.replace("connect-src 'self'", "connect-src 'self' https://accounts.google.com/gsi/")
                        value += '; frame-src https://accounts.google.com/gsi/'
                    adjusted.append((key, value))
                items = adjusted + [('Cross-Origin-Opener-Policy', 'same-origin-allow-popups')]
            return start_response(status, items)
        return super().__call__(env, headers)
