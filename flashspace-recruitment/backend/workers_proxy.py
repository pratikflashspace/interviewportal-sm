"""Opt-in Workers AI proxy. No direct-account fallback or credential logging."""
import base64
import json
import os
import re
import time
from urllib import request, error

ENDPOINT = 'https://pool-a-pratik-ai.yasasv.workers.dev/v1/run'
LLM_MODEL = '@cf/zai-org/glm-4.7-flash'
STT_MODEL = '@cf/openai/whisper-large-v3-turbo'
TTS_MODEL = '@cf/myshell-ai/melotts'
MODELS = frozenset((LLM_MODEL, STT_MODEL, TTS_MODEL))
MAX_RESPONSE = 16 * 1024 * 1024
MAX_AUDIO = 2 * 1024 * 1024


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward proxy credentials to another URL, even on same host.
        return None


class WorkersProxyProvider:
    def __init__(self, error_type):
        self.error_type = error_type
        self.url = os.getenv('PRATIK_WORKERS_AI_URL', ENDPOINT).strip()
        self.token = os.getenv('PRATIK_WORKERS_AI_TOKEN', '').strip()
        self.model = LLM_MODEL
        if self.url != ENDPOINT:
            raise error_type(503, 'The approved Workers AI proxy endpoint is required.')
        if not self.token or any(c.isspace() for c in self.token):
            raise error_type(503, 'Configure a rotated Workers AI proxy token securely in Render.')
        self.opener = request.build_opener(NoRedirect())

    def run(self, model, payload, audio=False):
        E = self.error_type
        if model not in MODELS:
            raise E(400, 'Unsupported proxy model.')
        if not isinstance(payload, dict):
            raise E(400, 'Invalid proxy input.')
        body = json.dumps({'model': model, 'input': payload}).encode()
        req = request.Request(self.url, data=body, method='POST', headers={
            'Authorization': 'Bearer ' + self.token,
            'Content-Type': 'application/json',
            'Accept': 'audio/mpeg, application/json' if audio else 'application/json',
        })
        for attempt in range(2):
            try:
                # At most two attempts with 25s socket timeout and 1s backoff.
                # Socket timeout is NOT a total wall-clock deadline.
                with self.opener.open(req, timeout=25) as response:
                    mime = response.headers.get('Content-Type', '').split(';')[0].lower()
                    raw = response.read(MAX_RESPONSE + 1)
                break
            except error.HTTPError as exc:
                status = exc.code
                exc.close()
                if status in (429, 503) and attempt == 0:
                    time.sleep(1)
                    continue
                if status in (401, 403):
                    message = 'Workers AI proxy access denied. Check the rotated token and proxy permissions.'
                elif status in (429, 503):
                    message = 'Workers AI proxy is busy. Retry later; no further automatic retries were made.'
                else:
                    message = 'Workers AI proxy request failed. Ask the operator to check service status.'
                raise E(502, message) from None
            except (error.URLError, TimeoutError, OSError):
                # No retry on ambiguous transport errors: inference may have run.
                raise E(502, 'Workers AI proxy did not respond. Retry later.') from None
        if len(raw) > MAX_RESPONSE:
            raise E(502, 'Workers AI proxy response exceeded the size limit.')
        if audio and mime in ('audio/mpeg', 'audio/mp3', 'application/octet-stream'):
            return self._mp3(raw)
        try:
            envelope = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise E(502, 'Workers AI proxy returned unreadable output.') from None
        if not isinstance(envelope, dict) or envelope.get('success') is False or envelope.get('errors') or envelope.get('error'):
            raise E(502, 'Workers AI proxy reported an inference error.')
        result = envelope.get('result', envelope)
        if isinstance(result, dict) and (result.get('error') or result.get('errors') or result.get('success') is False):
            raise E(502, 'Workers AI proxy reported an inference error.')
        if audio:
            encoded = result.get('audio') if isinstance(result, dict) else result
            try:
                if not isinstance(encoded, str):
                    raise ValueError()
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError):
                raise E(502, 'Workers AI proxy returned no playable audio.') from None
            return self._mp3(data)
        return result

    def _mp3(self, data):
        if not data or not (data.startswith(b'ID3') or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224)):
            raise self.error_type(502, 'Workers AI proxy returned invalid MP3 audio.')
        return data

    def structured(self, system, payload, name, schema):
        result = self.run(self.model, {
            'messages': [
                {'role': 'system', 'content': system + ' Return ONLY valid JSON matching this schema: ' + json.dumps(schema)},
                {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
            ],
            'max_tokens': 1800, 'temperature': 0.1, 'stream': False,
        })
        value = result.get('response') if isinstance(result, dict) else None
        if isinstance(result, dict) and 'choices' in result:
            choices = result['choices']
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                raise self.error_type(502, 'Workers AI proxy returned incomplete structured output.')
            choice = choices[0]
            message = choice.get('message')
            if choice.get('finish_reason') != 'stop' or not isinstance(message, dict) or message.get('refusal'):
                raise self.error_type(502, 'Workers AI proxy did not complete its structured response.')
            value = message.get('content')  # Never score reasoning_content or tool calls.
        if isinstance(value, str):
            value = re.sub(r'^```(?:json)?\s*|\s*```$', '', value.strip())
            try:
                value = json.loads(value)
            except ValueError:
                raise self.error_type(502, 'Workers AI proxy returned invalid structured JSON.') from None
        if not isinstance(value, dict):
            raise self.error_type(502, 'Workers AI proxy returned incomplete structured output.')
        # AI.next_question/evaluate retain strict length, score, quote and evidence validation.
        return value

    def transcribe(self, data, mime):
        if mime.split(';')[0].lower() not in ('audio/webm', 'audio/mp4', 'audio/ogg', 'audio/wav', 'audio/mpeg'):
            raise self.error_type(400, 'Unsupported audio format. Type your answer instead.')
        if not isinstance(data, bytes) or len(data) < 100 or len(data) > MAX_AUDIO:
            raise self.error_type(413, 'Use a shorter recording between 100 bytes and 2 MB, or type your answer.')
        # Supplied proxy contract uses integer audio bytes, not a browser-visible token.
        result = self.run(STT_MODEL, {'audio': list(data), 'task': 'transcribe'})
        value = result.get('text') if isinstance(result, dict) else None
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 6000:
            raise self.error_type(422, 'No usable transcript received. Record again or type your answer.')
        return {'text': value.strip()}

    def speech(self, question):
        if not isinstance(question, str) or not 1 <= len(question) <= 650:
            raise self.error_type(400, 'No valid question is available for speech.')
        return self.run(TTS_MODEL, {'prompt': question, 'lang': 'en'}, audio=True)
