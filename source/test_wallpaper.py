import base64, struct, unittest, urllib.request, urllib.error, zlib
import wallpaper

def png():
 def chunk(t,d):return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d))
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1424,280,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x12\x40\x40'*1424)*280))+chunk(b'IEND',b'')

class Tests(unittest.TestCase):
 def test_dimensions_and_size_validation(self):
  data=png();self.assertEqual(wallpaper.image_bytes(base64.b64encode(data).decode()),data)
  for bad in ['not an image',base64.b64encode(b'not a png').decode(),'a'*(wallpaper.MAX_IMAGE*4//3+5),base64.b64encode(data[:16]+struct.pack('>I',9000)+data[20:]).decode()]:
   with self.assertRaises(ValueError):wallpaper.image_bytes(bad)
 def test_only_exact_image_path_is_served(self):
  t=wallpaper.ImageTransfer('127.0.0.1','127.0.0.1',png())
  try:
   url=t.start()
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url+'/../pairing.json')
   self.assertFalse(t.fetched.is_set())
   with urllib.request.urlopen(url) as r:self.assertEqual(r.read(),png())
   self.assertTrue(t.fetched.wait(1))
  finally:t.close()
 def test_other_clients_cannot_fetch(self):
  t=wallpaper.ImageTransfer('127.0.0.1','192.0.2.10',png())
  try:
   url=t.start()
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url)
   self.assertFalse(t.fetched.is_set())
  finally:t.close()
 def test_preview_payload_and_no_settings_write(self):
  class Sock:
   def getsockname(self):return ('127.0.0.1',1234)
  class Client:
   sock=Sock();host='127.0.0.1';generation=1
   def send(self,obj):
    self.sent=obj
    with urllib.request.urlopen(obj['data']['url']) as r:self.data=r.read()
  c=Client();result=wallpaper.show(c,base64.b64encode(png()).decode())
  self.assertEqual(c.sent['act'],30742);self.assertEqual(c.sent['data']['mediaType'],'IMAGE');self.assertEqual(c.data,png());self.assertIn('transferred',result)
if __name__=='__main__':unittest.main()
