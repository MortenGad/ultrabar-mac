import unittest, tempfile, pathlib, queue, json
from unittest.mock import patch
import bridge

class FakeSocket:
 def __init__(self,blocks):self.blocks=iter(blocks)
 def recv(self,n):return next(self.blocks,b'')
 def close(self):pass
class Tests(unittest.TestCase):
 def test_fragmented_blank_and_discovery_frames(self):
  c=bridge.Client();q=queue.Queue();c.pending['r']=q
  raw=(json.dumps({'id':'r','act':100,'code':200})+'\n\n'+json.dumps({'act':30102,'data':{'serialNumber':'abc','productId':268435458}})+'\n').encode()
  with patch.object(bridge,'emit'):c.reader(FakeSocket([raw[:9],raw[9:42],raw[42:]]),0)
  self.assertEqual(q.get()['code'],200);self.assertIn('abc',c.modules)
 def test_pairing_pending_then_approved(self):
  c=bridge.Client()
  def send(obj):
   q=c.pending[obj['id']];q.put({'code':200,'data':{'state':0}});q.put({'code':200,'data':{'state':1,'token':'test'}})
  c.send=send
  with patch.object(bridge,'emit'):self.assertEqual(c.request(101,{},pair=True)['token'],'test')
  self.assertEqual(c.pending,{})
 def test_rejected_write_is_not_retried(self):
  c=bridge.Client();sent=[]
  def send(o):sent.append(o);c.pending[o['id']].put({'code':255,'msg':'denied'})
  c.send=send
  with self.assertRaisesRegex(RuntimeError,'denied'):c.request(30741,{})
  self.assertEqual(len(sent),1);self.assertFalse(c.pending)
 def test_invalid_volume_cannot_execute(self):
  c=bridge.Client();c.bridge=True;out=[];c.send=out.append
  with patch.object(bridge,'volume') as vol:
   c.handle_push({'id':'x','act':1000000,'data':{'type':'SET_VOLUME','payload':'do shell script'}})
   vol.assert_not_called();self.assertEqual(out[-1]['code'],255)
 def test_bridge_off_rejects_commands(self):
  c=bridge.Client();out=[];c.send=out.append
  with patch.object(bridge,'volume') as vol:c.handle_push({'id':'x','act':1000000,'data':{'type':'GET_VOLUME'}});vol.assert_not_called()
  self.assertEqual(out[-1]['code'],255)
 def test_volume_reply_shape(self):
  c=bridge.Client();c.bridge=True;out=[];c.send=out.append
  with patch.object(bridge,'volume',return_value=37),patch.object(bridge,'emit'):c.handle_push({'id':'x','act':1000000,'data':{'type':'GET_VOLUME'}})
  self.assertEqual(out[-1]['data'],{'type':'GET_VOLUME','payload':37});self.assertEqual(out[-1]['id'],'x')
 def test_profile_confirmation_required(self):
  c=bridge.Client()
  with patch.object(c,'request') as req:
   with self.assertRaisesRegex(ValueError,'confirmation'):c.deploy({})
   req.assert_not_called()
 def test_existing_custom_profile_protected(self):
  c=bridge.Client();c.modules={'k':{'serialNumber':'k','productId':268435458}}
  existing=[{'label':'Work','value':'work'}]
  with patch.object(c,'request',return_value=existing) as req:
   with self.assertRaisesRegex(RuntimeError,'Other saved profiles'):c.deploy({'confirmReplace':True,'expectedProfiles':existing})
   self.assertEqual(req.call_count,1)
 def test_stale_review_protected(self):
  c=bridge.Client();c.modules={'k':{'serialNumber':'k','productId':268435458}}
  with patch.object(c,'request',return_value=[{'value':'default'}]) as req:
   with self.assertRaisesRegex(RuntimeError,'changed'):c.deploy({'confirmReplace':True,'expectedProfiles':[]})
   self.assertEqual(req.call_count,1)
 def test_screen_preserves_unedited_fields_and_verifies(self):
  c=bridge.Client();before={'uri':'existing','featureEnabled':False,'lockTime':'TIME_1MIN','ver':4}
  after={**before,'featureEnabled':True,'lockTime':'TIME_2MIN'}
  with tempfile.TemporaryDirectory() as d,patch.object(bridge,'STATE_DIR',pathlib.Path(d)),patch.object(c,'request',side_effect=[before,{'success':True},after]) as req:
   self.assertEqual(c.save_screen({'enabled':True,'lockTime':'TIME_2MIN'}),after)
   self.assertEqual(req.call_args_list[1].args[1]['value']['uri'],'existing')
 def test_failed_readback_is_reported(self):
  c=bridge.Client()
  with tempfile.TemporaryDirectory() as d,patch.object(bridge,'STATE_DIR',pathlib.Path(d)),patch.object(c,'request',side_effect=[{}, {'success':True}, {}]):
   with self.assertRaisesRegex(RuntimeError,'read-back'):c.save_screen({'enabled':True,'lockTime':'TIME_2MIN'})
 def test_private_token_storage(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'pair.json';bridge.private_save(p,{'token':'test'});self.assertEqual(p.stat().st_mode & 0o777,0o600)
if __name__=='__main__':unittest.main()
