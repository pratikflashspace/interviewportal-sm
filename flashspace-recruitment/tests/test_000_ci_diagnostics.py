"""Surface safe, bounded failure diagnostics when Actions log access is limited."""
import os,re,unittest

def safe(value):
    message=str(value)
    for k,v in os.environ.items():
        if any(s in k.upper() for s in ('TOKEN','SECRET','PASSWORD','DATABASE_URL','API_KEY')) and len(v)>3:message=message.replace(v,'[REDACTED]')
    message=re.sub(r'(?:postgres(?:ql)?|https?)://[^\s]+','[URL]',message)
    return message[:1800].replace('%','%25').replace('\r','%0D').replace('\n','%0A')

if os.getenv('GITHUB_ACTIONS')=='true':
    for name in ('addFailure','addError'):
        original=getattr(unittest.TextTestResult,name)
        def annotate(self,test,err,_original=original):
            print('::error title=Integration test failure::'+safe(test.id()+' — '+str(err[1])),flush=True)
            return _original(self,test,err)
        setattr(unittest.TextTestResult,name,annotate)
