"""Direct Sarvam REST adapter. Opt-in, server-side, with no provider fallback.

Only synthetic staging data until privacy and end-to-end release gates pass.
No SDK or new dependency required. Never log credentials, audio or responses.
"""
import base64
import json
import os
import secrets
from urllib import request, error

ORIGIN = 'https://api.sarvam.ai'
CHAT_PATH = '/v1/chat/completions'
STT_PATH = '/speech-to-text'
TTS_PATH = '/text-to-speech'
LLM_MODEL = 'sarvam-105b'
STT_MODEL = 'saaras:v3'
TTS_MODEL = 'bulbul:v3'
MAX_AUDIO = 2 * 1024 * 1024
MAX_RESPONSE = 16 * 1024 * 1024
FORMATS = {'audio/webm': 'webm', 'audio/mp4': 'm4a', 'audio/ogg': 'ogg',
           'audio/wav': 'wav', 'audio/mpeg': 'mp3'}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_shape(value, schema):
    """Validate the subset used by the app's question/report schemas.

    This is not a general JSON Schema implementation. Unsupported types fail
    closed; semantic score, evidence and length checks remain in server.AI.
    """
    kind = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int}
    if kind not in types or type(value) is not types[kind]:
        raise ValueError('Invalid structured output type')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('Invalid structured output enum')
    if kind == 'object':
        props = schema.get('properties', {})
        if not set(schema.get('required', [])).issubset(value):
            raise ValueError('Missing required output')
        if schema.get('additionalProperties') is False and set(value) - set(props):
            raise ValueError('Unexpected output')
        for key, item in value.items():
            if key in props:
                validate_shape(item, props[key])
    elif kind == 'array':
        for item in value:
            validate_shape(item, schema['items'])


class SarvamProvider:
    def __init__(self, error_type):
        self.error_type = error_type
        self.model = LLM_MODEL
        self.token = os.getenv('SARVAM_API_KEY', '').strip()
        if (not self.token or not self.token.isascii()
                or any(ord(c) < 33 or ord(c) > 126 for c in self.token)
                or any(c in self.token for c in ('\"', "'"))):
            raise error_type(503, 'Configure SARVAM_API_KEY securely in staging Render; no quotes or Bearer prefix.')
        self.opener = request.build_opener(NoRedirect())

    def _send(self, path, body, content_type='application/json'):
        E = self.error_type
        if path not in (CHAT_PATH, STT_PATH, TTS_PATH):
            raise E(400, 'Unsupported Sarvam endpoint.')
        req = request.Request(ORIGIN + path, data=body, method='POST', headers={
            'api-subscription-key': self.token,
            'Content-Type': content_type,
            'Accept': 'application/json',
        })
        try:
            # One attempt only: prevents multiplying costs on ambiguous failures.
            # Socket timeout is not a total wall-clock deadline. Keep Gunicorn's
            # existing timeout and measure live latency before production.
            with self.opener.open(req, timeout=40) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except error.HTTPError as exc:
            status = exc.code
            exc.close()
            if status in (401, 403):
                message = 'Sarvam access denied. Check the staging API key and model access.'
            elif status in (402, 429):
                message = 'Sarvam credit or rate limit reached. Check usage; no automatic retry was made.'
            elif status in (400, 413, 422) and path == STT_PATH:
                message = 'Sarvam could not transcribe this recording. Try a clip under 30 seconds, or type your answer.'
            else:
                message = 'Sarvam request failed. Retry later or ask the operator to check service status.'
            raise E(502, message) from None
        except (error.URLError, TimeoutError, OSError):
            raise E(502, 'Sarvam did not respond successfully. Retry later; saved answers are retained.') from None
        if len(raw) > MAX_RESPONSE:
            raise E(502, 'Sarvam response exceeded the size limit.')
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise E(502, 'Sarvam returned unreadable output.') from None
        if not isinstance(result, dict) or result.get('error') or result.get('errors') or result.get('success') is False:
            raise E(502, 'Sarvam reported an inference error.')
        return result

    def structured(self, system, payload, name, schema):
        body = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system + ' Return ONLY JSON matching the supplied response schema.'},
                {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
            ],
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': name, 'schema': schema, 'strict': True,
            }},
            'max_tokens': 1800, 'temperature': 0.1, 'reasoning_effort': None,
            'stream': False, 'n': 1,
        }
        result = self._send(CHAT_PATH, json.dumps(body).encode())
        choices = result.get('choices')
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise self.error_type(502, 'Sarvam returned incomplete structured output.')
        choice = choices[0]
        message = choice.get('message')
        if (choice.get('finish_reason') != 'stop' or not isinstance(message, dict)
                or message.get('refusal') or message.get('tool_calls')
                or not isinstance(message.get('content'), str)):
            raise self.error_type(502, 'Sarvam did not complete its structured response.')
        try:
            # Never use reasoning_content, tool calls, markdown fences or partial JSON.
            value = json.loads(message['content'])
            validate_shape(value, schema)
        except (ValueError, TypeError, KeyError, RecursionError):
            raise self.error_type(502, 'Sarvam structured output failed validation.') from None
        return value

    def transcribe(self, data, mime):
        mime = mime.split(';')[0].lower() if isinstance(mime, str) else ''
        if mime not in FORMATS:
            raise self.error_type(400, 'Unsupported audio format. Type your answer instead.')
        if not isinstance(data, bytes) or not 100 <= len(data) <= MAX_AUDIO:
            raise self.error_type(413, 'Use a short recording between 100 bytes and 2 MB, or type your answer.')
        # Size is not duration. REST is for short clips; see the staging guide.
        boundary = 'sarvam-' + secrets.token_hex(24)
        fields = {'model': STT_MODEL, 'mode': 'transcribe', 'language_code': 'unknown'}
        chunks = []
        for key, value in fields.items():
            chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode())
        chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="answer.{FORMATS[mime]}"\r\nContent-Type: {mime}\r\n\r\n').encode())
        chunks.extend([data, f'\r\n--{boundary}--\r\n'.encode()])
        result = self._send(STT_PATH, b''.join(chunks), 'multipart/form-data; boundary=' + boundary)
        transcript = result.get('transcript')
        if not isinstance(transcript, str) or not 1 <= len(transcript.strip()) <= 6000:
            raise self.error_type(422, 'No usable transcript received. Record again or type your answer.')
        return {'text': transcript.strip()}

    def speech(self, question):
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 650:
            raise self.error_type(400, 'No valid question is available for speech.')
        result = self._send(TTS_PATH, json.dumps({
            'text': question, 'language_code': 'en-IN', 'speaker': 'shubh',
            'model': TTS_MODEL, 'speech_sample_rate': 24000,
            'output_audio_codec': 'mp3', 'pace': 1.0,
        }).encode())
        audios = result.get('audios')
        try:
            if not isinstance(audios, list) or len(audios) != 1 or not isinstance(audios[0], str):
                raise ValueError()
            audio = base64.b64decode(audios[0], validate=True)
            if not (audio.startswith(b'ID3') or (len(audio) > 1 and audio[0] == 255 and audio[1] & 224 == 224)):
                raise ValueError()
        except (ValueError, TypeError):
            raise self.error_type(502, 'Sarvam returned no valid MP3 audio.') from None
        # Matches the existing WSGI audio/mpeg response contract, without a UI change.
        return audio
