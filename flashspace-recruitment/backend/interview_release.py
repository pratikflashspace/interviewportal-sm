"""Release-candidate endpoints. No deployment or new provider credentials."""
import copy
import re
from .server import APIError, now
from .integrated_recordings import IntegratedApp
from .v2_endpoint import EvidenceOnlyAI

class InterviewRelease(IntegratedApp):
    def route(self,env,body):
        path=env.get('PATH_INFO','');method=env.get('REQUEST_METHOD')
        match=re.fullmatch(r'/api/recordings/([a-f0-9]{32})/abort',path)
        if match and method=='POST':
            user=self.current_user(env)
            with self.recordings.lock:
                m=self.recordings.get(match[1])
                if m['owner']!=user['id']:raise APIError(404,'Recording not found.')
                # Never remove a completed video or release its slot implicitly.
                if m['status']=='uploading':m['status']='incomplete';self.recordings.save(m)
            return {'status':m['status']},[]
        match=re.fullmatch(r'/api/v2/applications/([\w-]+)/recordings',path)
        if match and method=='GET':
            u=self.current_user(env);a=self.store.get(match[1])
            if a['user_id']!=u['id']:raise APIError(404,'Interview not found.')
            return {'recordings':[self.metadata(m) for m in self.recordings.all(a['id'])]},[]
        match=re.fullmatch(r'/api/v2/applications/([\w-]+)/continuation',path)
        if match and method=='POST':
            user=self.current_user(env);aid=match[1]
            with self.lock:
                a=self.store.get(aid);f=self.flow(aid)
                if a['user_id']!=user['id'] or not f:raise APIError(404,'Interview not found.')
                if not f['answers'] or f['pending_decision'] or f['status']!='interview' or not f['active']:
                    raise APIError(409,'This submitted turn cannot be extended. Review the saved transcript.')
                if type(body.get('version')) is not int or body['version']!=f['version']:
                    raise APIError(409,'Interview state changed. Reload before adding a continuation.')
                if body.get('event_id')!=f['answers'][-1]['event_id']:
                    raise APIError(409,'Only the most recently submitted answer can be continued.')
                if self.playback.state(aid,f['active']['id'])['deliveries']!=0:
                    raise APIError(409,'The next question has already been delivered; submitted answers cannot be edited.')
                answer=body.get('answer');old=f['answers'][-1]['answer']
                if not isinstance(answer,str) or not 1<=len(answer.strip())<=6000 or not answer.strip().startswith(old):
                    raise APIError(400,'Continuation must preserve the submitted answer and remain under 6000 characters.')
                answer=answer.strip()
                if answer!=old:
                    f=copy.deepcopy(f);f['answers'][-1]['answer']=answer;f['answers'][-1]['continued_at']=now();f['version']+=1
                    self.save_flow(a,f)
                from .v2_flow import public_flow
                return {'application_id':aid,**public_flow(f)},[]
        return super().route(env,body)

def create_app():return InterviewRelease(ai=EvidenceOnlyAI())
