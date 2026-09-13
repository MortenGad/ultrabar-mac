import copy,json,pathlib,tempfile,unittest
import widgets
from bridge import private_save
class Device:
 def __init__(self):self.host='device';self.generation=1;self.profiles=[{'value':'default','label':'Standard Mode'}];self.calls=[];self.fail=None
 def request(self,act,data):
  self.calls.append((act,copy.deepcopy(data)))
  if self.fail==act:raise RuntimeError('Connection lost')
  if act==30710:return copy.deepcopy(self.profiles)
  if act==1002:return [{'id':'com.test.app','type':'APPS','last':True,'icon':'test-icon'}]
  if act==1108:self.profiles=[{'value':p['id'],'label':p['name']} for p in data]
  return {}
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=pathlib.Path(self.tmp.name);self.c=Device();self.s=widgets.WidgetService(self.c,self.path,private_save);self.doc=widgets.sample()
 def prepare(self):return self.s.prepare(self.doc)
 def apply(self,r,**kw):return self.s.apply(dict(reviewId=r['reviewId'],confirmed=True,confirmReplace=True,**kw))
 def test_timer_wire_and_bounds(self):
  w=self.doc['widgets'][1];w['duration']='01:02:03';self.assertEqual(widgets.wire_widget(widgets.validate(self.doc)['widgets'][1],[])['param'],{'time':'01:02:03'})
  for bad in ['00:00:00','24:00:00','1:00:00','00:60:00']:
   w['duration']=bad
   with self.assertRaises(ValueError):widgets.validate(self.doc)
 def test_offsets(self):
  w=self.doc['widgets'][2]
  for good in ['+05:30','-03:30','+14:00']:
   w['offset']=good;self.assertEqual(widgets.wire_widget(widgets.validate(self.doc)['widgets'][2],[])['param'],{'offset':good})
  for bad in ['+14:01','UTC+1','+01:60']:
   w['offset']=bad
   with self.assertRaises(ValueError):widgets.validate(self.doc)
 def test_invalid_and_duplicate_widgets(self):
  for mutation in ['unsupported','duplicate']:
   d=copy.deepcopy(self.doc)
   if mutation=='unsupported':d['widgets'][0]['kind']='EXECUTE'
   else:d['widgets'][1]['id']=d['widgets'][0]['id']
   with self.assertRaises(ValueError):widgets.validate(d)
 def test_app_catalogue_required(self):
  w=self.doc['widgets'][0];w.update(kind='APPS',appId='com.test.app')
  with self.assertRaises(ValueError):widgets.wire_widget(w,[])
  r=self.prepare();out=self.s.review['payload'][0]['widget'][0];self.assertEqual(out['id'],'com.test.app');self.assertEqual(out['icon'],'test-icon')
 def test_save_roundtrip_order_and_ids(self):
  self.doc['widgets'].reverse();saved=self.s.save_document(self.doc);self.assertEqual(self.s.load()['document'],saved)
 def test_review_is_read_only(self):
  r=self.prepare();self.assertTrue(r['needsReplacement']);self.assertEqual([a for a,d in self.c.calls],[30710,1002])
 def test_explicit_replacement_required(self):
  r=self.prepare()
  with self.assertRaises(ValueError):self.s.apply({'reviewId':r['reviewId'],'confirmed':True})
  self.assertNotIn(1108,[a for a,d in self.c.calls])
 def test_stale_profiles_block(self):
  r=self.prepare();self.c.profiles.append({'value':'new','label':'New'})
  with self.assertRaises(RuntimeError):self.apply(r)
  self.assertNotIn(1108,[a for a,d in self.c.calls])
 def test_connection_and_expiry_block(self):
  for field in ['host','generation','created']:
   r=self.prepare()
   if field=='created':self.s.review[field]-=301
   elif field=='host':self.s.review[field]='other'
   else:self.s.review[field]-=1
   with self.assertRaises(ValueError):self.apply(r)
  self.assertNotIn(1108,[a for a,d in self.c.calls])
 def test_known_profiles_and_modules_preserved(self):
  p={'id':self.doc['profileId'],'name':self.doc['name'],'module':[{'id':'knob'}],'widget':[]};other={'id':'other','name':'Other','module':[],'widget':[{'type':'TIME'}]}
  private_save(self.path/'widget-deployments.json',{'host':self.c.host,'profiles':[p,other]});self.c.profiles=[{'value':x['id'],'label':x['name']} for x in [p,other]]
  r=self.prepare();self.assertFalse(r['needsReplacement']);payload=self.s.review['payload'];self.assertEqual(payload[-1]['module'],p['module']);self.assertEqual(payload[0]['widget'],other['widget'])
 def test_other_device_ledger_ignored(self):
  private_save(self.path/'widget-deployments.json',{'host':'other','profiles':[{'id':'default','name':'Standard Mode'}]});self.assertTrue(self.prepare()['needsReplacement'])
 def test_apply_once_and_no_gateway_changes(self):
  r=self.prepare();out=self.apply(r);self.assertEqual(out['profileId'],self.doc['profileId']);acts=[a for a,d in self.c.calls];self.assertEqual(acts.count(1108),1);self.assertNotIn(30300,acts);self.assertNotIn(30741,acts)
  with self.assertRaises(ValueError):self.apply(r)
 def test_failed_write_not_retried(self):
  r=self.prepare();self.c.fail=1108
  with self.assertRaisesRegex(RuntimeError,'may have changed'):self.apply(r)
  with self.assertRaises(ValueError):self.apply(r)
  self.assertEqual([a for a,d in self.c.calls].count(1108),1)
 def test_acknowledged_layout_saved_if_activation_fails(self):
  r=self.prepare();self.c.fail=1103
  with self.assertRaisesRegex(RuntimeError,'acknowledged'):self.apply(r)
  self.assertTrue((self.path/'widget-deployments.json').exists());self.assertEqual(self.s.load()['document'],widgets.validate(self.doc))
if __name__=='__main__':unittest.main()

class ExtraWidgetTests(unittest.TestCase):
 def doc(self,kind):
  d=widgets.sample();d['widgets']=[dict(d['widgets'][0],kind=kind,latitude='55.24943',longitude='9.48771',soundId='sys.app.soundscape.1')];return d
 def test_weather_wire_coordinates(self):
  w=widgets.validate(self.doc('WEATHER'))['widgets'][0]
  self.assertEqual(widgets.wire_widget(w,[])['param'],{'lat':'55.24943','lon':'9.48771'})
 def test_invalid_coordinates(self):
  for key,value in [('latitude','nan'),('latitude','inf'),('latitude','91'),('longitude','181'),('longitude',''),('latitude',True)]:
   d=self.doc('WEATHER');d['widgets'][0][key]=value
   with self.assertRaises(ValueError):widgets.validate(d)
 def test_sound_must_exist_on_device(self):
  w=widgets.validate(self.doc('SOUNDSCAPE'))['widgets'][0]
  with self.assertRaises(ValueError):widgets.wire_widget(w,[])
  self.assertEqual(widgets.wire_widget(w,[{'id':w['soundId'],'type':'SOUNDSCAPE'}])['param'],{'id':w['soundId']})
 def test_sound_parser_ignores_timer_with_same_id(self):
  class C:
   def request(self,a,d):return [{'id':'sound','type':'TIMER','components':[{'options':[{'label':'Bad','value':'bad'}]}]},{'id':'sound','type':'SOUND_SCAPE','components':[{'options':[{'label':'Rain','value':'rain'}]}]}]
  self.assertEqual(widgets.sound_catalogue(C()),[{'id':'rain','name':'Rain','type':'SOUNDSCAPE','last':True}])
 def test_new_fields_roundtrip(self):
  for kind in ['WEATHER','SOUNDSCAPE']:
   d=widgets.validate(self.doc(kind));self.assertEqual(widgets.validate(json.loads(json.dumps(d))),d)
