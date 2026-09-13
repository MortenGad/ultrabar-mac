import unittest,tempfile,pathlib,json
import module_inventory as inv
class Tests(unittest.TestCase):
 def test_knob_missing_from_scan_but_online(self):
  out=inv.combine([{'serialNumber':'vivo','productId':3}],[{'serialNo':'knob','online':True},{'serialNo':'vivo','online':False}],[{'serialNumber':'knob','productId':2}])
  by={d['serialNumber']:d for d in out};self.assertEqual(by['knob']['productId'],2);self.assertEqual(by['knob']['status'],'Online');self.assertFalse(by['knob']['seenInScan']);self.assertEqual(by['vivo']['status'],'Seen in scan · reports offline')
 def test_offline_is_not_available(self):
  out=inv.combine([],[{'serialNo':'old','online':False}],[{'serialNumber':'old','productId':2}]);self.assertFalse(out[0]['available'])
 def test_unknown_registered_module_not_guessed(self):
  out=inv.combine([],[{'serialNo':'new','online':True}],[]);self.assertNotIn('productId',out[0]);self.assertEqual(out[0]['status'],'Online')
 def test_removed_cached_device_not_presented_as_live(self):self.assertEqual(inv.combine([],[],[{'serialNumber':'old'}]),[])
 def test_cache_is_host_scoped(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);(p/'module-inventory.json').write_text(json.dumps({'host':'other','modules':[{'serialNumber':'old'}]}));self.assertEqual(inv.known_for(p,'current',[]),[])
 def test_legacy_recovery_requires_registered_serial(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);(p/'backups').mkdir();(p/'backups/gateway-1.json').write_text(json.dumps({'requested':{'canGateway':{'endpoints':[{'serialNumber':'a','productId':2},{'serialNumber':'b','productId':3}]}}}));self.assertEqual(inv.known_for(p,'current',[{'serialNo':'a','online':True}]),[{'serialNumber':'a','productId':2}])
