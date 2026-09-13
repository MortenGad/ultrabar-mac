"""Ultrabar Mac: local stdio bridge. Image previews use a temporary single-image LAN server."""
import hashlib, ipaddress, json, os, pathlib, queue, socket, ssl, subprocess, sys, threading, time, uuid
sys.dont_write_bytecode=True
import widgets, mac_actions, module_inventory, wallpaper
PIN = '4aa830d5fe236a41e5b8502cecd3aa5f8da742ac757bf6e319654f31d6790b93'
STATE_DIR = pathlib.Path(os.environ.get('ULTRABAR_STATE_DIR', str(pathlib.Path.home()/'Library/Application Support/Ultrabar Mac')))
PRODUCTS = {268435457:'DotKey',268435458:'KnobKey',268435459:'VivoCube',268435460:'SenseCube'}
TIMEOUTS = ['TIME_30S','TIME_1MIN','TIME_2MIN','TIME_3MIN','TIME_4MIN','TIME_5MIN','NEVER']
outlock=threading.Lock()
def emit(obj):
 with outlock: print(json.dumps(obj),flush=True)
def private_save(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 tmp=path.with_suffix('.tmp');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:json.dump(obj,f,indent=2)
 os.replace(tmp,path)
def volume(value=None):
 script='output volume of (get volume settings)' if value is None else 'set volume output volume '+str(max(0,min(100,int(value))))
 r=subprocess.run(['/usr/bin/osascript','-e',script],capture_output=True,text=True,timeout=4)
 if r.returncode:raise RuntimeError(r.stderr.strip())
 return int(r.stdout.strip()) if value is None else int(value)
class Client:
 def __init__(self):
  self.sock=None;self.pending={};self.lock=threading.Lock();self.pending_lock=threading.Lock();self.modules={};self.host='';self.bridge=False;self.generation=0
 def send(self,obj):
  with self.lock:
   if not self.sock:raise RuntimeError('Connect to the Ultrabar first.')
   self.sock.sendall((json.dumps(obj,separators=(',',':'))+'\n').encode())
 def request(self,act,data=None,timeout=14,pair=False):
  rid=str(uuid.uuid4());q=queue.Queue()
  with self.pending_lock:self.pending[rid]=q
  try:
   self.send({'id':rid,'act':act,'data':data,'timestamp':int(time.time()*1000)})
   deadline=time.monotonic()+timeout
   while True:
    r=q.get(timeout=max(.01,deadline-time.monotonic()))
    if isinstance(r,Exception):raise r
    if r.get('code')!=200:raise RuntimeError(r.get('msg') or str(r.get('data')) or 'Device rejected request')
    if pair and isinstance(r.get('data'),dict) and r['data'].get('state')==0:
     emit({'event':'status','message':'Tap Allow on the Ultrabar now.'});continue
    return r.get('data')
  except queue.Empty:raise TimeoutError('The Ultrabar did not reply in time. No write was retried.')
  finally:
   with self.pending_lock:self.pending.pop(rid,None)
 def close(self):
  self.generation+=1;s=self.sock;self.sock=None;self.bridge=False
  if s:
   try:s.shutdown(socket.SHUT_RDWR)
   except OSError:pass
   s.close()
 def connect(self,host,pair=False):
  ip=ipaddress.ip_address(host)
  if not ip.is_private or ip.is_loopback or ip.is_multicast:raise ValueError('Enter the Ultrabar’s private LAN IP address.')
  self.close();self.host=host;self.modules={};generation=self.generation
  c=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);c.check_hostname=False;c.verify_mode=ssl.CERT_NONE
  # Exact vendor certificate pin is checked BEFORE any token or app data is sent.
  s=c.wrap_socket(socket.create_connection((host,7431),4));s.settimeout(None)
  if hashlib.sha256(s.getpeercert(binary_form=True)).hexdigest()!=PIN:
   s.close();raise RuntimeError('Device certificate does not match the verified vendor certificate.')
  self.sock=s;threading.Thread(target=self.reader,args=(s,generation),daemon=True).start()
  statepath=STATE_DIR/'pairing.json';state=json.loads(statepath.read_text()) if statepath.exists() else {'client_id':str(uuid.uuid4())}
  try:
   if pair:
    private_save(statepath,state)
    data=self.request(101,{'id':state['client_id'],'name':'Ultrabar Mac'},timeout=18,pair=True)
    if not isinstance(data,dict) or not data.get('token'):raise RuntimeError('Pairing was not approved.')
    state['token']=data['token'];private_save(statepath,state)
   if not state.get('token'):raise RuntimeError('Use Pair to approve this Mac on the Ultrabar.')
   self.request(100,state['token'])
  except Exception:
   self.close();raise
  threading.Thread(target=self.heartbeat,args=(generation,),daemon=True).start()
  return self.snapshot()
 def reader(self,s,generation):
  buf=b''
  try:
   while generation==self.generation:
    block=s.recv(65536)
    if not block:raise ConnectionError('Ultrabar disconnected.')
    buf+=block
    if len(buf)>1048576:raise ValueError('Device response exceeded the size limit.')
    while b'\n' in buf:
     raw,buf=buf.split(b'\n',1)
     if not raw.strip():continue
     obj=json.loads(raw)
     with self.pending_lock:q=self.pending.get(obj.get('id'))
     if q:q.put(obj)
     elif obj.get('act')==30102 and isinstance(obj.get('data'),dict):
      d=obj['data'];sn=d.get('serialNumber')
      if sn:self.modules[sn]=d
     elif obj.get('act')==1000000:
      threading.Thread(target=self.handle_push,args=(obj,generation),daemon=True).start()
  except Exception as e:
   if generation==self.generation:
    self.sock=None;self.bridge=False
    with self.pending_lock:
     for q in self.pending.values():q.put(ConnectionError(str(e)))
    emit({'event':'disconnected','message':str(e)})
  finally:s.close()
 def heartbeat(self,generation):
  while generation==self.generation and self.sock:
   time.sleep(10)
   if generation!=self.generation:return
   try:self.send({'id':str(uuid.uuid4()),'act':20,'data':None})
   except OSError:return
 def handle_push(self,obj,generation=None):
  if generation is not None and generation!=self.generation:return
  data=obj.get('data') if isinstance(obj.get('data'),dict) else {};kind=data.get('type')
  reply={'id':obj.get('id'),'act':obj.get('act'),'timestamp':int(time.time()*1000)}
  try:
   if kind=='PC_CONTROL':
    value=actions.handle(data,str(obj.get('id') or ''))
    reply.update(code=200,data={'type':kind,'payload':value});self.send(reply);return
   if not self.bridge:raise RuntimeError('Mac volume bridge is off.')
   if kind=='GET_VOLUME':value=volume()
   elif kind=='SET_VOLUME':
    payload=data.get('payload')
    if isinstance(payload,bool) or not isinstance(payload,(int,float)) or not 0<=payload<=100:raise ValueError('Invalid volume')
    volume(payload);value=volume()
   else:raise RuntimeError('Unsupported desktop action')
   reply.update(code=200,data={'type':kind,'payload':value})
   emit({'event':'volume','value':value})
  except Exception as e:reply.update(code=255,msg=str(e))
  try:self.send(reply)
  except OSError:pass
 def snapshot(self):
  profiles=self.request(30710,{})
  apps=self.request(30740,{'type':'APP_LIST'})
  try:screen=self.request(30740,{'type':'SCREEN_SAVER'})
  except RuntimeError:screen=None
  self.refresh_modules()
  return {'host':self.host,'profiles':profiles,'apps':apps,'screen':screen,'modules':list(self.modules.values()),'widgetApps':self.request(1002,'sys.widget.apps')}
 def refresh_modules(self):
  registered=self.request(30730,{})
  if not isinstance(registered,list):raise RuntimeError('Unexpected module-state response.')
  known=module_inventory.known_for(STATE_DIR,self.host,registered)
  discovered=[m for m in self.modules.values() if m.get('seenInScan',True)]
  merged=module_inventory.combine(discovered,registered,known)
  self.modules={m['serialNumber']:m for m in merged}
  private_save(STATE_DIR/'module-inventory.json',{'host':self.host,'modules':merged})
  return merged
 def scan(self):
  self.modules={};self.request(30100,'can')
  try:time.sleep(6)
  finally:self.request(30101,'can')
  modules=self.refresh_modules();private_save(STATE_DIR/'modules.json',modules)
  return modules
 def save_screen(self,args):
  if args['lockTime'] not in TIMEOUTS:raise ValueError('Invalid timeout')
  try:before=self.request(30740,{'type':'SCREEN_SAVER'})
  except RuntimeError:before=None
  value=dict(before or {});value.update(featureEnabled=bool(args['enabled']),lockTime=args['lockTime'])
  private_save(STATE_DIR/'backups'/f'screen-{time.time_ns()}.json',{'before':before,'after':value})
  result=self.request(30741,{'type':'SCREEN_SAVER','value':value})
  if isinstance(result,dict) and result.get('success') is False:raise RuntimeError(str(result))
  actual=self.request(30740,{'type':'SCREEN_SAVER'})
  if not isinstance(actual,dict) or actual.get('featureEnabled')!=value['featureEnabled'] or actual.get('lockTime')!=value['lockTime']:raise RuntimeError('Write was acknowledged, but read-back did not match. Inspect the device before retrying.')
  return actual
 def draft(self,args):
  knob=next((d for d in self.modules.values() if d.get('productId')==268435458 and d.get('available',True)),None)
  if not knob:raise RuntimeError('Scan modules first; a KnobKey must be present.')
  name=args.get('name','Mac Volume').strip()
  if not name or len(name)>64:raise ValueError('Use a profile name of 1–64 characters.')
  config={'clockwise':{'id':'mac-volume','type':'PC_VOLUME'},'counterclockwise':{'id':'mac-volume','type':'PC_VOLUME'}}
  profile={'id':'ultrabar-mac-volume','name':name,'isDefault':True,'showName':True,'iconScale':100,'widget':[], 'module':[{'serialNo':knob['serialNumber'],'productId':'KNOB_KEY','config':config}]}
  endpoints=[]
  for d in self.modules.values():
   if not d.get('available',True):continue
   e=dict(d);e['name']=PRODUCTS.get(d['productId'],'Module');endpoints.append(e)
  return {'gateway':{'canGateway':{'endpoints':endpoints},'meshGateway':{'endpoints':[]}},'profiles':[profile]}
 def deploy(self,args):
  if args.get('confirmReplace') is not True:raise ValueError('Profile replacement requires explicit confirmation.')
  draft=self.draft(args)
  existing=self.request(30710,{})
  expected=args.get('expectedProfiles')
  if expected!=existing:raise RuntimeError('Profiles changed since review. Refresh and review again.')
  # Do not quietly delete user profiles not owned by this app.
  if any(p.get('value') not in ('default','ultrabar-mac-volume') for p in existing):raise RuntimeError('Other saved profiles exist. Full profile backup is not supported, so replacement is blocked.')
  saved=STATE_DIR/'backups'/f'deployment-{time.time_ns()}.json'
  private_save(saved,{'previousProfileNamesOnly':existing,'note':'Not a restorable backup of the original layout.','deployment':draft})
  self.request(30300,draft['gateway'])
  self.request(1108,draft['profiles'])
  self.request(1103,'ultrabar-mac-volume')
  profiles=self.request(30710,{})
  if not any(p.get('value')=='ultrabar-mac-volume' for p in profiles):raise RuntimeError('Deployment was acknowledged but profile verification failed.')
  self.bridge=True
  private_save(STATE_DIR/'last-deployment.json',draft)
  return {'profiles':profiles,'message':'Mac Volume profile saved. Volume bridge enabled; keep this app open.'}
client=Client()
widget_service=widgets.WidgetService(client,STATE_DIR,private_save)
actions=mac_actions.Actions(client,widget_service,STATE_DIR,private_save,emit)
def dispatch(cmd):
 op=cmd['op']
 if op=='wallpaper_show':return wallpaper.show(client,cmd['image'])
 if op=='actions_load':return dict(actions.load(),enabled=actions.enabled)
 if op=='actions_save':return actions.persist(cmd['config'])
 if op=='actions_test':return actions.launch(cmd['actionId'])
 if op=='actions_enabled':return actions.set_enabled(cmd['enabled'])
 if op=='actions_review':return actions.prepare(cmd['config'])
 if op=='actions_deploy':return actions.apply(cmd)
 if op=='widget_sounds':return widgets.sound_catalogue(client)
 if op=='widget_load':return widget_service.load()
 if op=='widget_validate':return widgets.validate(cmd['document'])
 if op=='widget_save':return widget_service.save_document(cmd['document'])
 if op=='widget_review':return widget_service.prepare(cmd['document'])
 if op=='widget_deploy':return widget_service.apply(cmd)
 if op=='connect':return client.connect(cmd['host'])
 if op=='pair':return client.connect(cmd['host'],True)
 if op=='refresh':return client.snapshot()
 if op=='scan':return client.scan()
 if op=='screen':return client.save_screen(cmd)
 if op=='switch':client.request(1103,cmd['profile']);return 'Profile switched.'
 if op=='draft':return client.draft(cmd)
 if op=='deploy':return client.deploy(cmd)
 if op=='bridge':client.bridge=bool(cmd['enabled']);return {'enabled':client.bridge}
 if op=='disconnect':client.close();return 'Disconnected.'
 raise ValueError('Unknown operation')
def main():
 for line in sys.stdin:
  try:
   cmd=json.loads(line);result=dispatch(cmd);emit({'ok':True,'op':cmd['op'],'result':result})
  except Exception as e:emit({'ok':False,'message':str(e)})
 client.close()
if __name__=='__main__':main()
