"""Validated widget documents and reviewed profile deployment for Ultrabar Mac."""
import copy, math, json, pathlib, re, time, uuid
FORMAT='ultrabar-mac-layout/v1'
KINDS={'TIME','TIMER','WORLD_TIME','APPS','WEATHER','SOUNDSCAPE'}
MAX_WIDGETS=24

def text(value,label,maximum=64):
 if not isinstance(value,str) or not value.strip() or len(value)>maximum:raise ValueError(f'{label} must contain 1–{maximum} characters.')
 return value.strip()
def validate(doc):
 if not isinstance(doc,dict) or doc.get('format')!=FORMAT:raise ValueError('Open an Ultrabar Mac layout file (format v1).')
 if len(json.dumps(doc))>262144:raise ValueError('Layout file is too large.')
 profile_id=text(doc.get('profileId'),'Profile ID',100)
 if not re.fullmatch(r'[A-Za-z0-9_.-]+',profile_id):raise ValueError('Invalid profile ID.')
 name=text(doc.get('name'),'Layout name')
 if type(doc.get('showNames')) is not bool:raise ValueError('Show labels must be true or false.')
 items=doc.get('widgets')
 if not isinstance(items,list) or len(items)>MAX_WIDGETS:raise ValueError(f'Use at most {MAX_WIDGETS} widgets.')
 output=[];ids=set();apps=set()
 for item in items:
  if not isinstance(item,dict):raise ValueError('Invalid widget.')
  wid=text(item.get('id'),'Widget ID',100)
  if not re.fullmatch(r'[A-Za-z0-9_.-]+',wid) or wid in ids:raise ValueError('Widget IDs must be valid and unique.')
  ids.add(wid);kind=item.get('kind')
  if kind not in KINDS:raise ValueError(f'Unsupported widget type: {kind}')
  w={'id':wid,'kind':kind,'name':text(item.get('name'),'Widget label'),'duration':item.get('duration','00:25:00'),'offset':item.get('offset','+00:00'),'appId':item.get('appId','')}
  if not all(isinstance(w[k],str) for k in ('duration','offset','appId')):raise ValueError('Widget settings must be text.')
  if kind=='TIMER':
   if not re.fullmatch(r'\d{2}:[0-5]\d:[0-5]\d',w['duration']):raise ValueError('Timer duration must use HH:MM:SS.')
   h,m,s=map(int,w['duration'].split(':'))
   if not 1<=h*3600+m*60+s<=86399:raise ValueError('Timer must be between 1 second and 23:59:59.')
  if kind=='WORLD_TIME':
   if not re.fullmatch(r'[+-]\d{2}:[0-5]\d',w['offset']):raise ValueError('UTC offset must use +HH:MM or -HH:MM.')
   h,m=map(int,w['offset'][1:].split(':'))
   if h*60+m>840:raise ValueError('UTC offset must be within ±14 hours.')
  if kind=='APPS':
   if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+',w['appId']):raise ValueError('Choose an installed app for each app widget.')
   if w['appId'] in apps:raise ValueError('Add each app launcher only once.')
   apps.add(w['appId'])
  if kind=='SOUNDSCAPE':w['soundId']=text(item.get('soundId'),'Sound selection',150)
  if kind=='WEATHER':
   for key,limit in [('latitude',90),('longitude',180)]:
    value=item.get(key,'')
    if not isinstance(value,str) or len(value)>30:raise ValueError('Weather coordinates must be decimal numbers.')
    try:number=float(value)
    except ValueError:raise ValueError('Enter both weather coordinates.')
    if not math.isfinite(number) or abs(number)>limit:raise ValueError(f'{key.title()} must be within ±{limit}.')
    w[key]=value.strip()
  output.append(w)
 return {'format':FORMAT,'profileId':profile_id,'name':name,'showNames':doc['showNames'],'widgets':output}
def sample():
 def item(kind,name,**kw):return dict(id=str(uuid.uuid4()),kind=kind,name=name,duration='00:25:00',offset='+00:00',appId='',**kw)
 return {'format':FORMAT,'profileId':'ultrabar-mac-widgets-'+uuid.uuid4().hex[:12],'name':'My desk','showNames':True,'widgets':[item('TIME','Local time'),item('TIMER','Focus'),item('WORLD_TIME','UTC')]}
def wire_widget(w,catalogue):
 out={'id':'mac.widget.'+w['id'],'name':w['name'],'type':w['kind'],'param':{}}
 if w['kind']=='TIMER':out['param']={'time':w['duration']}
 if w['kind']=='WORLD_TIME':out['param']={'offset':w['offset']}
 if w['kind']=='WEATHER':out['param']={'lat':w['latitude'],'lon':w['longitude']}
 if w['kind']=='SOUNDSCAPE':
  entry=next((a for a in catalogue if a.get('id')==w['soundId'] and a.get('type')=='SOUNDSCAPE'),None)
  if not entry:raise ValueError('Choose a sound available on this Ultrabar.')
  out['param']={'id':w['soundId']}
 if w['kind']=='APPS':
  entry=next((a for a in catalogue if a.get('id')==w['appId'] and a.get('type')=='APPS' and a.get('last') is True),None)
  if not entry:raise ValueError(f'App launcher “{w["name"]}” is not available in the current device catalogue.')
  out['id']=w['appId']
  if isinstance(entry.get('icon'),str):out['icon']=entry['icon']
 return out

def sound_catalogue(client):
 rows=client.request(1205,'sc.other')
 if not isinstance(rows,list):raise RuntimeError('Unexpected sound catalogue response.')
 result=[]
 for row in rows:
  if row.get('type')!='SOUND_SCAPE':continue
  for component in row.get('components',[]):
   for option in component.get('options',[]):
    if isinstance(option.get('value'),str) and isinstance(option.get('label'),str):
     result.append({'id':option['value'],'name':option['label'],'type':'SOUNDSCAPE','last':True})
 return result

def profile_identity(profiles):return sorted((p.get('value'),p.get('label')) for p in profiles)
def changed_since_deploy(current,observed):
 """Profile IDs whose device-reported row differs from the row read back after this app's last verified deploy.

 The device exposes only profile-list metadata, so this catches external edits (for example from another
 companion app) only when that metadata changes. Missing records mean no evidence either way.
 Boolean fields are ignored: they can be state markers (active/default) that flip on a normal profile switch."""
 def stable(row):return {k:v for k,v in row.items() if not isinstance(v,bool)}
 seen={r.get('value'):stable(r) for r in observed or [] if isinstance(r,dict)}
 return {r.get('value') for r in current if r.get('value') in seen and stable(r)!=seen[r.get('value')]}
class WidgetService:
 def __init__(self,client,state_dir,save):self.client=client;self.directory=pathlib.Path(state_dir);self.save=save;self.review=None
 def load(self):
  p=self.directory/'widget-layout.json'
  return {'document':validate(json.loads(p.read_text())) if p.exists() else sample(),'saved':p.exists()}
 def save_document(self,doc):
  doc=validate(doc);self.save(self.directory/'widget-layout.json',doc);return doc
 def prepare(self,doc):
  self.review=None
  doc=validate(doc)
  if not doc['widgets']:raise ValueError('Add at least one widget before deploying.')
  current=self.client.request(30710,{})
  catalogue=self.client.request(1002,'sys.widget.apps')
  if not isinstance(current,list) or not isinstance(catalogue,list):raise RuntimeError('Unexpected response from the Ultrabar.')
  if any(w['kind']=='SOUNDSCAPE' for w in doc['widgets']):catalogue=catalogue+sound_catalogue(self.client)
  ledgerpath=self.directory/'widget-deployments.json'
  ledger=json.loads(ledgerpath.read_text()) if ledgerpath.exists() else {}
  known=[];changed=set()
  if ledger.get('host')==self.client.host:
   # Only retain definitions which the app previously sent, whose IDs and names still match.
   current_pairs=set(profile_identity(current))
   known=[copy.deepcopy(p) for p in ledger.get('profiles',[]) if (p.get('id'),p.get('name')) in current_pairs]
   changed=changed_since_deploy(current,ledger.get('observed'))&{p.get('id') for p in known}
  previous=next((p for p in known if p.get('id')==doc['profileId']),{})
  profile=copy.deepcopy(previous)
  profile.update(id=doc['profileId'],name=doc['name'],showName=doc['showNames'],isDefault=True,widget=[wire_widget(w,catalogue) for w in doc['widgets']])
  profile.setdefault('module',[])
  payload=[]
  for p in known:
   if p.get('id')!=profile['id']:p['isDefault']=False;payload.append(p)
  payload.append(profile)
  known_ids={p['id'] for p in known}
  unavailable=[p for p in current if p.get('value') not in known_ids]
  replaced=[p.get('label',p.get('value','Profile')) for p in unavailable]
  changed_names=[p['name'] for p in known if p.get('id') in changed]
  reviewid=uuid.uuid4().hex
  plan={'reviewId':reviewid,'host':self.client.host,'generation':self.client.generation,'created':time.monotonic(),'expected':current,'payload':payload,'document':doc,'previousKnown':known,'unavailable':unavailable,'changed':changed_names}
  self.review=plan
  return {'reviewId':reviewid,'profileName':doc['name'],'widgetCount':len(doc['widgets']),'replacedProfiles':replaced,'keptProfiles':[p['name'] for p in known if p['id']!=profile['id']],'updatingKnown':bool(previous),'profilesAfter':[p['name'] for p in payload],'changedProfiles':changed_names,'needsReplacement':bool(unavailable or changed_names),'summary':'Gateway registration will not be changed. Local definitions will be used for app-managed profiles; external edits are detected only when they change the reported profile-list metadata.'}
 def apply(self,args):
  plan=self.review
  if not plan or args.get('reviewId')!=plan['reviewId']:raise ValueError('Review the layout again before applying.')
  if args.get('confirmed') is not True:raise ValueError('Confirm the reviewed deployment first.')
  if plan['unavailable'] and args.get('confirmReplace') is not True:raise ValueError('Confirm replacement of profiles whose layouts cannot be read.')
  if plan.get('changed') and args.get('confirmReplace') is not True:raise ValueError('Confirm overwriting profiles that changed on the device since this app last deployed them.')
  if time.monotonic()-plan['created']>300 or self.client.host!=plan['host'] or self.client.generation!=plan['generation']:raise ValueError('This review expired or the connection changed. Review again.')
  current=self.client.request(30710,{})
  if profile_identity(current)!=profile_identity(plan['expected']):raise RuntimeError('Saved profiles changed since review. Nothing was written; review again.')
  self.review=None # A potentially non-idempotent device write is never retried automatically.
  record={'host':plan['host'],'profiles':plan['payload'],'previousKnown':plan['previousKnown'],'unavailableBefore':plan['unavailable'],'document':plan['document'],'stage':'prepared','note':'Unknown original layouts were not read and cannot be restored from this record.'}
  recordpath=self.directory/'backups'/f'widgets-{time.time_ns()}.json';self.save(recordpath,record)
  try:self.client.request(1108,plan['payload'])
  except Exception as e:
   record['stage']='write-outcome-unknown';self.save(recordpath,record)
   raise RuntimeError('The profile write was not confirmed. The device may have changed; do not retry blindly. '+str(e))
  record['stage']='acknowledged';self.save(recordpath,record)
  # Persist the exact acknowledged definitions before the separate activation step.
  self.save(self.directory/'widget-deployments.json',{'host':plan['host'],'profiles':plan['payload']})
  if not plan.get('skipDocumentSave'):self.save_document(plan['document'])
  try:
   self.client.request(1103,plan['document']['profileId'])
   after=self.client.request(30710,{})
   expected=sorted((p['id'],p['name']) for p in plan['payload'])
   if profile_identity(after)!=expected:raise RuntimeError('Saved profile names do not match the deployment.')
  except Exception as e:raise RuntimeError('Layout write was acknowledged and saved locally, but activation or profile-list verification failed: '+str(e))
  # Remember what the device reported, so later reviews can flag edits made by other tools.
  ids={p['id'] for p in plan['payload']}
  self.save(self.directory/'widget-deployments.json',{'host':plan['host'],'profiles':plan['payload'],'observed':[r for r in after if r.get('value') in ids]})
  record['stage']='profile-list-verified';self.save(recordpath,record)
  return {'profiles':after,'profileId':plan['document']['profileId'],'message':'Layout saved; profile list verified. Check the Ultrabar display—the device does not support widget read-back.'}
