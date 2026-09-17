"""Candidate profile sections inside existing profile JSON; no DDL/provider calls.
Legacy free text remains verbatim. Profile-wide optimistic version prevents lost
updates between old link editors and new sections. Recruiter UI is unchanged.
"""
import copy
import json
import re
from datetime import date
from urllib.parse import urlsplit
from .server import APIError

PATH='/api/workspace/candidate/profile'
TEXT={
 'personal':{'name':100,'phone':40,'city':120,'headline':160},
 'summary':{'summary':2000},
 'links':{'portfolio_url':1000,'linkedin_url':1000,'github_url':1000},
 'preferences':{'roles':500,'locations':500,'work_mode':30,'employment_type':60,'availability':200},
 'resume':{'resume_url':1000},
}
ENTRIES={
 'education':{'qualification':150,'institution':200,'specialization':150,'start':4,'end':4,'grade':100},
 'experience':{'title':150,'company':200,'employment_type':60,'start':7,'end':7,'responsibilities':2000,'achievements':2000},
 'projects':{'name':150,'description':2000,'contribution':2000,'technologies':500,'demo_url':1000,'repository_url':1000},
 'certifications':{'name':150,'issuer':200,'year':4,'credential_url':1000},
}
LEGACY={'education':'education','experience':'experience','projects':'projects','skills':'skills','certifications':'certifications','preferences':'preferences'}
REQUIRED={'education':['qualification','institution'],'experience':['title','company'],'projects':['name'],'certifications':['name','issuer']}

def clean_string(value,limit):
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 and c not in '\n\r\t' for c in value):
        raise APIError(400,'A profile field is invalid or too long.')
    return value.strip()

def safe_link(value):
    if not value:return value
    try:
        p=urlsplit(value)
        if p.scheme!='https' or not p.hostname or p.username or p.password or any(c.isspace() for c in value) or '\\' in value:
            raise ValueError()
        _=p.port
    except ValueError:raise APIError(400,'Use an HTTPS link without embedded credentials or spaces.') from None
    return value

def year(value):
    if value and (not re.fullmatch(r'\d{4}',value) or not 1900<=int(value)<=date.today().year+10):
        raise APIError(400,'Enter a valid four-digit year.')

def month(value):
    if value:
        if not re.fullmatch(r'\d{4}-\d{2}',value):raise APIError(400,'Enter dates as year and month.')
        try:date.fromisoformat(value+'-01')
        except ValueError:raise APIError(400,'Enter a valid year and month.') from None
        if not 1900<=int(value[:4])<=date.today().year+10:raise APIError(400,'Enter a valid year.')

def validate(section,value):
    if not isinstance(value,dict):raise APIError(400,'Invalid profile section.')
    if section in TEXT:
        spec=TEXT[section]
        if set(value)!=set(spec):raise APIError(400,'Unsupported profile fields. Email and role cannot be edited.')
        result={k:clean_string(value[k],limit) for k,limit in spec.items()}
        for k,v in result.items():
            if k.endswith('_url'):safe_link(v)
        if section=='personal' and len(result['name'])<2:raise APIError(400,'Enter a name of at least two characters.')
        if section=='preferences' and result['work_mode'] not in ('','any','remote','onsite','hybrid'):raise APIError(400,'Choose a supported work mode.')
        return result
    if section=='skills':
        if set(value)!={'items'} or not isinstance(value['items'],list) or len(value['items'])>40:raise APIError(400,'Use at most 40 skills.')
        items=[clean_string(s,80) for s in value['items']]
        if any(not s for s in items) or len({s.casefold() for s in items})!=len(items):raise APIError(400,'Skills must be non-empty and unique.')
        return {'items':items}
    if section not in ENTRIES:raise APIError(400,'Unsupported profile section.')
    allowed={'items','no_experience'} if section=='experience' else {'items'}
    if set(value)!=allowed or not isinstance(value['items'],list) or len(value['items'])>12:raise APIError(400,'Use at most 12 entries in a section.')
    if section=='experience' and type(value['no_experience']) is not bool:raise APIError(400,'Invalid experience choice.')
    if value.get('no_experience') and value['items']:raise APIError(400,'No experience yet cannot be selected alongside experience entries.')
    result={'items':[]}
    if section=='experience':result['no_experience']=value['no_experience']
    spec=ENTRIES[section]
    for item in value['items']:
        flags={'current'} if section in ('education','experience') else set()
        if not isinstance(item,dict) or set(item)!=set(spec)|flags:raise APIError(400,'Unsupported entry fields.')
        entry={k:clean_string(item[k],limit) for k,limit in spec.items()}
        if any(not entry[k] for k in REQUIRED[section]):raise APIError(400,'Fill the required fields or remove the empty entry.')
        for k,v in entry.items():
            if k.endswith('_url'):safe_link(v)
        if flags:
            if type(item['current']) is not bool:raise APIError(400,'Invalid current activity choice.')
            entry['current']=item['current']
            if entry['current'] and entry['end']:raise APIError(400,'Clear the end date for a current entry.')
            for key in ('start','end'):(year if section=='education' else month)(entry[key])
            if entry['start'] and entry['end'] and entry['end']<entry['start']:raise APIError(400,'End date cannot be before start date.')
        if section=='certifications':year(entry['year'])
        result['items'].append(entry)
    return result

def defaults(section,data,u):
    if section in TEXT:
        return {k:data.get(k,u['name'] if k=='name' else '') if k in ('name','phone','summary','resume_url') else '' for k in TEXT[section]}
    return {'items':[],**({'no_experience':False} if section=='experience' else {})}

def read_raw(app,u):
    with app.store.db() as db:row=db.execute('SELECT data,version FROM workspace_profiles WHERE user_id=?',(u['id'],)).fetchone()
    return (json.loads(row['data']),row['version']) if row else ({},0)

def view(app,u):
    data,version=read_raw(app,u);stored=data.get('_candidate_sections',{})
    sections={k:copy.deepcopy(stored.get(k,defaults(k,data,u))) for k in [*TEXT,*ENTRIES,'skills']}
    # Simple fields share source of truth with existing Profile and Resume APIs.
    for section in ('personal','summary','resume'):
        for key in sections[section]:
            if key in ('name','phone','summary','resume_url'):sections[section][key]=data.get(key,u['name'] if key=='name' else '')
    return {'role':'candidate','email':u['email'],'version':version,'sections':sections,
            'legacy':{section:data.get(key,'') for section,key in LEGACY.items()}}

def compatibility_fields(data,fields):
    """Read-only text projection for existing dashboard/recruiter consumers."""
    result=dict(fields)
    for section,value in data.get('_candidate_sections',{}).items():
        if section not in LEGACY:continue
        if section=='skills':extra=', '.join(value.get('items',[]))
        elif section=='preferences':extra='\n'.join(v for v in value.values() if isinstance(v,str) and v.strip())
        else:
            extra='\n\n'.join('\n'.join(f'{k.replace("_"," ")}: {v}' for k,v in item.items() if isinstance(v,str) and v.strip()) for item in value.get('items',[]))
            if section=='experience' and value.get('no_experience'):extra='No work experience yet (candidate supplied).'
        original=result.get(LEGACY[section],'')
        if extra:result[LEGACY[section]]=original+('\n\n' if original else '')+extra
    return result

def handle(app,env,body):
    u=app.current_user(env)
    if u['admin']:raise APIError(403,'Candidate access required.')
    if env['REQUEST_METHOD']=='GET':return view(app,u),[]
    if env['REQUEST_METHOD']!='POST':raise APIError(405,'POST required.')
    if set(body)!={'version','section','value'} or type(body['version']) is not int or body['version']<0 or not isinstance(body['section'],str):raise APIError(400,'Invalid profile update.')
    value=validate(body['section'],body['value']);section=body['section']
    app.store.quota('candidate-profile:'+u['id'],60,600)
    with app.lock:
        data,version=read_raw(app,u)
        if version!=body['version']:raise APIError(409,'Profile changed in another session. Your draft is unchanged; review the latest saved profile before retrying.')
        if section=='experience' and value.get('no_experience') and data.get('experience','').strip():raise APIError(409,'Existing experience text is preserved. Review it before choosing no experience yet.')
        updated=copy.deepcopy(data);updated.setdefault('_candidate_sections',{})[section]=value
        for key in ('name','phone','summary','resume_url'):
            if key in value:updated[key]=value[key]
        encoded=json.dumps(updated,ensure_ascii=False)
        if len(encoded.encode())>200000:raise APIError(400,'Profile is too large. Shorten section entries.')
        with app.store.db() as db:
            row=db.execute('INSERT INTO workspace_profiles(user_id,data,version) VALUES (?,?,1) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data,version=workspace_profiles.version+1 WHERE workspace_profiles.version=? RETURNING version',(u['id'],encoded,version)).fetchone()
            if not row:raise APIError(409,'Profile changed in another session. Review latest saved data before retrying.')
            if section=='personal':db.execute('UPDATE users SET name=? WHERE id=?',(value['name'],u['id']))
        return view(app,{**u,'name':updated.get('name',u['name'])}),[]
