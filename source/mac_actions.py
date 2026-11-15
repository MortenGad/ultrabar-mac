"""Locally approved app launchers shared by LineOS panels and physical keys."""
import copy,json,pathlib,plistlib,re,subprocess,threading,time,uuid
import widgets
GESTURES={'singleClick','doubleClick','longPress'}
DOT=268435457;KNOB=268435458

def app_path(value):
 if not isinstance(value,str) or not value.startswith('/'):raise ValueError('Choose a Mac application.')
 p=pathlib.Path(value).resolve()
 if p.suffix.lower()!='.app' or not p.is_dir():raise ValueError('Choose an existing .app application.')
 try:info=plistlib.loads((p/'Contents/Info.plist').read_bytes())
 except Exception:raise ValueError('This is not a valid Mac app bundle.')
 if info.get('CFBundlePackageType')!='APPL':raise ValueError('Choose an application bundle.')
 return str(p)

def validate(d):
 if not isinstance(d,dict):raise ValueError('Invalid action configuration.')
 actions=d.get('actions',[]);bindings=d.get('bindings',[])
 if not isinstance(actions,list) or not 1<=len(actions)<=12:raise ValueError('Choose between 1 and 12 apps.')
 out=[];ids=set()
 for a in actions:
  aid=widgets.text(a.get('id'),'Action ID',80)
  if not re.fullmatch('[A-Za-z0-9_-]+',aid) or aid in ids:raise ValueError('Action IDs must be unique.')
  ids.add(aid);out.append({'id':aid,'name':widgets.text(a.get('name'),'Button label',32),'path':app_path(a.get('path'))})
 if not isinstance(bindings,list) or len(bindings)>40:raise ValueError('Invalid physical bindings.')
 bound=[];seen=set()
 for b in bindings:
  sn=widgets.text(b.get('serial'),'Module serial',100);product=b.get('productId');key=b.get('keyCode');gesture=b.get('gesture')
  if type(product)!=int or product not in (DOT,KNOB) or type(key)!=int or key not in range(0,256) or gesture not in GESTURES or b.get('actionId') not in ids:raise ValueError('Invalid physical button assignment.')
  identity=(sn,key,gesture)
  if identity in seen:raise ValueError('A physical gesture can only have one action.')
  seen.add(identity);bound.append({'serial':sn,'productId':product,'keyCode':key,'gesture':gesture,'actionId':b['actionId']})
 return {'actions':out,'bindings':bound,'profileName':widgets.text(d.get('profileName','Mac buttons'),'Panel name')}

def parameter(aid):return {'output':10,'payload':{'app':'ultrabar-mac','actionId':aid}}
def button(a):return {'id':'mac.button.'+a['id'],'name':a['name'],'type':'PC_CONTROL','spanSize':1,'param':parameter(a['id'])}
def scene(a):
 return {'id':'mac.scene.'+a['id'],'name':a['name'],'type':'MANUAL','enabled':True,'show':False,'actions':[{'id':'1','name':a['name'],'type':'PC_CONTROL','values':[{'id':'1','value':parameter(a['id'])}]}]}

def modules_for(config,previous,available):
 result=copy.deepcopy(previous);by_id={a['id']:a for a in config['actions']}
 for b in config['bindings']:
  if not any(m.get('serialNumber')==b['serial'] and m.get('productId')==b['productId'] and m.get('available',True) for m in available):raise ValueError('An assigned module is missing. Scan modules and review again.')
  m=next((m for m in result if m.get('serialNo')==b['serial']),None)
  if m is None:m={'serialNo':b['serial'],'productId':b['productId'],'config':[] if b['productId']==DOT else {}};result.append(m)
  if b['productId']==DOT:
   if not isinstance(m['config'],list):raise ValueError('Unexpected DotKey config; no changes made.')
   key=next((k for k in m['config'] if k.get('keyCode')==b['keyCode']),None)
   if key is None:key={'keyCode':b['keyCode']};m['config'].append(key)
  else:key=m['config'].setdefault('button',{})
  key[b['gesture']]=scene(by_id[b['actionId']])
 return result

class Actions:
 def __init__(self,client,service,directory,save,emit):
  self.client=client;self.service=service;self.directory=pathlib.Path(directory);self.save=save;self.emit=emit;self.enabled=False;self.lock=threading.Lock();self.seen={};self.last={};self.review_config=None
  pref=self.directory/'mac-buttons-enabled.json'
  if pref.exists():self.enabled=json.loads(pref.read_text()).get('enabled') is True
 def set_enabled(self,value):
  self.enabled=bool(value);self.save(self.directory/'mac-buttons-enabled.json',{'enabled':self.enabled});return self.enabled
 def load(self):
  p=self.directory/'mac-actions.json'
  return json.loads(p.read_text()) if p.exists() else {'profileName':'Mac buttons','actions':[],'bindings':[]}
 def persist(self,d):
  d=validate(d);self.save(self.directory/'mac-actions.json',d);return d
 def launch(self,aid,event_id=None):
  with self.lock:
   if event_id and not self.enabled:raise RuntimeError('Mac app buttons are paused.')
   now=time.monotonic();self.seen={k:v for k,v in self.seen.items() if now-v<60}
   if event_id and event_id in self.seen:return 'Duplicate event ignored'
   config=self.load();a=next((a for a in config['actions'] if a['id']==aid),None)
   if not a:raise ValueError('This button is not an approved local action.')
   path=app_path(a['path'])
   if event_id:
    self.seen[event_id]=now
    if now-self.last.get(aid,-10)<0.7:return 'Repeated press ignored'
    self.last[aid]=now
   r=subprocess.run(['/usr/bin/open','-a',path],capture_output=True,text=True,timeout=6)
   if r.returncode:raise RuntimeError(r.stderr.strip() or 'macOS could not open the app.')
   self.emit({'event':'mac_action','message':'Opened '+a['name']});return 'Opened '+a['name']
 def handle(self,data,rid):
  if not self.enabled:raise RuntimeError('Mac app buttons are paused.')
  if not isinstance(rid,str) or not rid or len(rid)>160:raise ValueError('Invalid event ID.')
  p=data.get('payload')
  if not isinstance(p,dict) or set(p)!={'app','actionId'} or p.get('app')!='ultrabar-mac' or not isinstance(p.get('actionId'),str):raise ValueError('Unrecognised Mac action.')
  return self.launch(p['actionId'],rid)
 def prepare(self,config):
  config=validate(config);self.review_config=None
  d=widgets.sample();d.update(profileId='ultrabar-mac-buttons',name=config['profileName']);d['widgets']=d['widgets'][:1]
  r=self.service.prepare(d);plan=self.service.review
  p=next(p for p in plan['payload'] if p['id']==d['profileId'])
  # A dedicated profile: screen configuration is owned by this action editor.
  p['widget']=[{'id':'mac.button.panel','name':config['profileName'],'type':'HOT_KEY_GROUP','param':{'button':[button(a) for a in config['actions']]}}]+[button(a) for a in config['actions']]
  # Rebuilding our own bindings clears assignments removed in this editor, while keeping rotary controls.
  old=copy.deepcopy(p.get('module',[]))
  for m in old:
   if m.get('productId')==DOT:m['config']=[]
   elif m.get('productId')==KNOB:m.get('config',{}).pop('button',None)
  p['module']=modules_for(config,old,list(self.client.modules.values()))
  registered=self.client.request(30730,{}) if config['bindings'] else None
  if registered==[]:
   plan['registerGateway']={'canGateway':{'endpoints':[dict(m,name={DOT:'DotKey',KNOB:'KnobKey',268435459:'VivoCube',268435460:'SenseCube'}.get(m['productId'],'Module')) for m in self.client.modules.values() if m.get('interfaceType')=='can' and m.get('available',True)]},'meshGateway':{'endpoints':[]}}
  r['registerModules']=len(plan.get('registerGateway',{}).get('canGateway',{}).get('endpoints',[]))
  plan['skipDocumentSave']=True;plan['actionConfig']=config;self.review_config=copy.deepcopy(config)
  r.update(widgetCount=len(p['widget']),physicalBindings=len(config['bindings']),profileName=config['profileName'])
  return r
 def apply(self,args):
  plan=self.service.review
  if not plan or 'actionConfig' not in plan:raise ValueError('Review the Mac buttons first.')
  if args.get('reviewId')!=plan['reviewId'] or args.get('confirmed') is not True:raise ValueError('Confirm the reviewed Mac buttons first.')
  if (plan['unavailable'] or plan.get('changed')) and args.get('confirmReplace') is not True:raise ValueError('Confirm replacement of unknown or externally changed profiles first.')
  if time.monotonic()-plan['created']>300 or self.client.host!=plan['host'] or self.client.generation!=plan['generation']:raise ValueError('Connection changed or review expired.')
  if widgets.profile_identity(self.client.request(30710,{}))!=widgets.profile_identity(plan['expected']):raise ValueError('Profiles changed. Review again.')
  config=validate(plan['actionConfig'])
  # Save local allowlist before device writes; no app launches occur here.
  before=self.load();self.save(self.directory/'backups'/f'actions-{time.time_ns()}.json',before)
  self.persist(config)
  if plan.get('registerGateway'):
   if self.client.request(30730,{})!=[]:raise ValueError('Module registration changed. Review again.')
   record=self.directory/'backups'/f'gateway-{time.time_ns()}.json'
   self.save(record,{'host':self.client.host,'beforeRegisteredModules':[],'requested':plan['registerGateway']})
   self.client.request(30300,plan['registerGateway'])
  result=self.service.apply(args);self.set_enabled(True)
  result['message']='Mac buttons saved and activated. Tap a screen button or an assigned physical key; keep this app open.'
  return result
