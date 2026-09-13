import unittest,tempfile,pathlib,plistlib,copy
from unittest.mock import patch
import mac_actions as m,widgets
from bridge import private_save
class Client:
 def __init__(self):self.host='test';self.generation=1;self.modules={'dot':{'serialNumber':'dot','productId':m.DOT,'interfaceType':'can','netId':1,'workMode':1}};self.profiles=[];self.calls=[];self.registered=[]
 def request(self,a,d):
  self.calls.append((a,d))
  if a==30710:return copy.deepcopy(self.profiles)
  if a==1002:return []
  if a==30730:return self.registered
  if a==1108:self.profiles=[{'value':p['id'],'label':p['name']} for p in d]
  return {}
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name);self.app=self.root/'Example.app';(self.app/'Contents').mkdir(parents=True);(self.app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundlePackageType':'APPL'}));self.c=Client();self.ws=widgets.WidgetService(self.c,self.root,private_save);self.s=m.Actions(self.c,self.ws,self.root,private_save,lambda x:None);self.d={'profileName':'Mac buttons','actions':[{'id':'chosen','name':'Example','path':str(self.app)}],'bindings':[]}
 def test_only_app_bundles_allowed(self):
  for bad in ['/bin/sh','https://example.com','Calculator','/missing.app']:
   with self.assertRaises(ValueError):m.app_path(bad)
 def test_safe_open_argv(self):
  self.s.persist(self.d)
  with patch.object(m.subprocess,'run') as run:
   run.return_value.returncode=0;self.s.launch('chosen');self.assertEqual(run.call_args.args[0],['/usr/bin/open','-a',str(self.app.resolve())])
 def test_device_cannot_supply_paths_or_shell(self):
  self.s.persist(self.d);self.s.enabled=True
  for payload in [{'app':'ultrabar-mac','actionId':'unknown'},{'app':'ultrabar-mac','actionId':'chosen','path':'/bin/sh'},'open Calculator']:
   with patch.object(m.subprocess,'run') as run:
    with self.assertRaises(ValueError):self.s.handle({'payload':payload},'event');run.assert_not_called()
 def test_paused_or_missing_id_does_not_launch(self):
  self.s.persist(self.d)
  with self.assertRaises(RuntimeError):self.s.handle({'payload':m.parameter('chosen')['payload']},'event')
  self.s.enabled=True
  with self.assertRaises(ValueError):self.s.handle({'payload':m.parameter('chosen')['payload']},'')
 def test_repeated_event_launches_once(self):
  self.s.persist(self.d);self.s.enabled=True
  with patch.object(m.subprocess,'run') as run:
   run.return_value.returncode=0
   for i in range(3):self.s.handle({'payload':m.parameter('chosen')['payload']},'same')
   self.assertEqual(run.call_count,1)
 def test_panel_and_physical_share_payload(self):
  a=self.d['actions'][0];self.assertEqual(m.button(a)['param'],m.scene(a)['actions'][0]['values'][0]['value'])
 def test_physical_schema_and_preserve_rotation(self):
  d=copy.deepcopy(self.d);d['bindings']=[{'serial':'knob','productId':m.KNOB,'keyCode':0,'gesture':'singleClick','actionId':'chosen'}]
  old=[{'serialNo':'knob','productId':m.KNOB,'config':{'clockwise':{'type':'PC_VOLUME'}}}]
  actual=m.modules_for(d,old,[{'serialNumber':'knob','productId':m.KNOB}]);self.assertEqual(actual[0]['config']['clockwise'],old[0]['config']['clockwise']);self.assertEqual(actual[0]['config']['button']['singleClick']['actions'][0]['type'],'PC_CONTROL');self.assertNotIn('button',old[0]['config'])
 def test_review_no_writes(self):
  self.s.prepare(self.d);self.assertNotIn(1108,[a for a,d in self.c.calls]);self.assertNotIn(30300,[a for a,d in self.c.calls])
 def test_apply_preserves_widget_draft(self):
  prior=widgets.sample();self.ws.save_document(prior);r=self.s.prepare(self.d);self.s.apply({'reviewId':r['reviewId'],'confirmed':True});self.assertEqual(self.ws.load()['document'],widgets.validate(prior));self.assertTrue(self.s.enabled)
 def test_unconfirmed_apply_does_not_save_registry(self):
  r=self.s.prepare(self.d)
  with self.assertRaises(ValueError):self.s.apply({'reviewId':r['reviewId']})
  self.assertFalse((self.root/'mac-actions.json').exists())
 def test_register_only_empty_gateway(self):
  d=copy.deepcopy(self.d);d['bindings']=[{'serial':'dot','productId':m.DOT,'keyCode':1,'gesture':'singleClick','actionId':'chosen'}]
  r=self.s.prepare(d);self.assertEqual(r['registerModules'],1);self.c.registered=[{'serialNumber':'new'}]
  with self.assertRaises(ValueError):self.s.apply({'reviewId':r['reviewId'],'confirmed':True})
  self.assertNotIn(30300,[a for a,d in self.c.calls])
