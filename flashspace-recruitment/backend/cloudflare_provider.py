"""Cloudflare Workers AI REST adapter, called by Python on Render.
No Workers deployment, D1 binding, OpenAI key, or provider-native guessed URL.
"""
import base64
import json
import os
import re
from urllib import request, error, parse

DEFAULT_LLM = '@cf/meta/llama-3.1-8b-instruct-fast'
STT_MODEL = '@cf/openai/whisper-large-v3-turbo'
TTS_MODEL = '@cf/deepgram/aura-2-en'

class CloudflareProvider:
    def __init__(self, error_type):
        self.error_type=error_type
        self.account=os.getenv('CLOUDFLARE_ACCOUNT_ID','').strip()
        self.gateway=os.getenv('CLOUDFLARE_GATEWAY_ID','').strip()
        self.token=os.getenv('CLOUDFLARE_API_TOKEN','').strip()
        self.model=os.getenv('CLOUDFLARE_LLM_MODEL',DEFAULT_LLM).strip()
    def run(self,model,payload,audio=False):
        E=self.error_type
        if not re.fullmatch(r'[a-fA-F0-9]{32}',self.account) or not self.token or not self.gateway:
            raise E(503,'Configure the Cloudflare Account ID, Gateway ID and replacement API token in Render.')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',self.gateway) or not re.fullmatch(r'@cf/[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+',model):
            raise E(503,'Cloudflare Gateway ID or model configuration is invalid.')
        url=f'https://api.cloudflare.com/client/v4/accounts/{self.account}/ai/run/{model}'
        headers={'Authorization':'Bearer '+self.token,'cf-aig-gateway-id':self.gateway,
                 'cf-aig-skip-cache':'true','cf-aig-collect-log':'false',
                 'Content-Type':'application/json','Accept':'audio/mpeg, application/json' if audio else 'application/json'}
        req=request.Request(url,data=json.dumps(payload).encode(),headers=headers,method='POST')
        try:
            with request.urlopen(req,timeout=55) as response:
                mime=response.headers.get('Content-Type','').split(';')[0].lower()
                raw=response.read(16*1024*1024+1)
                if len(raw)>16*1024*1024: raise E(502,'Cloudflare response exceeded the safe size limit.')
        except error.HTTPError as exc:
            if exc.code in (401,403): message='Cloudflare access denied. Ask the owner to check Workers AI permission, gateway access and model billing for the replacement token.'
            elif exc.code==429: message='Cloudflare AI rate or usage limit reached. Your saved progress is safe; try later.'
            else: message=f'Cloudflare AI returned HTTP {exc.code}. Retry later or check the configured model.'
            raise E(502,message) from None
        except (error.URLError,TimeoutError,OSError):
            raise E(502,'Cloudflare AI did not respond in time. Your saved progress is safe; retry later.') from None
        if audio and mime in ('audio/mpeg','audio/mp3','application/octet-stream'):
            if not raw:raise E(502,'Cloudflare generated empty audio.')
            return raw
        try: envelope=json.loads(raw)
        except (ValueError,UnicodeDecodeError):raise E(502,'Cloudflare returned an unreadable response.') from None
        if not isinstance(envelope,dict) or envelope.get('success') is False or envelope.get('errors'):
            raise E(502,'Cloudflare reported an inference error. Check model access and billing.')
        result=envelope.get('result',envelope)
        if audio:
            try:
                encoded=result.get('audio') if isinstance(result,dict) else result
                if not isinstance(encoded,str):raise ValueError()
                data=base64.b64decode(encoded,validate=True)
                if not data:raise ValueError()
                return data
            except (ValueError,TypeError):raise E(502,'Cloudflare returned no playable speech audio.') from None
        return result
    def structured(self,system,payload,name,schema):
        # Provider JSON support differs by model. Prompt + strict application validation,
        # not blind trust in response_format; no paid-model automatic fallback.
        result=self.run(self.model,{'messages':[
            {'role':'system','content':system+' Return ONLY valid JSON matching this schema: '+json.dumps(schema)},
            {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
            'max_tokens':1800,'temperature':0.1})
        value=result.get('response') if isinstance(result,dict) else None
        if isinstance(value,str):
            value=re.sub(r'^```(?:json)?\s*|\s*```$','',value.strip())
            try:value=json.loads(value)
            except ValueError:raise self.error_type(502,'Cloudflare returned invalid JSON. No score or question was saved; please retry.') from None
        if not isinstance(value,dict):raise self.error_type(502,'Cloudflare response was incomplete. Please retry.')
        return value
    def transcribe(self,data,mime):
        if mime.split(';')[0].lower() not in ('audio/webm','audio/mp4','audio/ogg','audio/wav','audio/mpeg'):
            raise self.error_type(400,'Unsupported audio format. Type your answer instead.')
        result=self.run(STT_MODEL,{'audio':base64.b64encode(data).decode('ascii'),'task':'transcribe','language':'en'})
        value=result.get('text') if isinstance(result,dict) else None
        if not isinstance(value,str) or not 1<=len(value.strip())<=6000:
            raise self.error_type(422,'No usable transcript received. Record a shorter answer or type instead.')
        return {'text':value.strip()}
    def speech(self,question):
        return self.run(TTS_MODEL,{'text':question,'speaker':os.getenv('CLOUDFLARE_TTS_SPEAKER','luna'),'encoding':'mp3'},audio=True)
