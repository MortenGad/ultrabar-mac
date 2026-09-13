"""Temporary, single-image transfer for LineOS act 30742 (not persistent wallpaper)."""
import base64, binascii, http.server, json, secrets, threading, uuid

MAX_IMAGE = 3 * 1024 * 1024

def image_bytes(encoded):
 if not isinstance(encoded,str) or len(encoded)>MAX_IMAGE*4//3+4:
  raise ValueError('Choose an image smaller than 3 MB after resizing.')
 try:data=base64.b64decode(encoded,validate=True)
 except (ValueError,binascii.Error):raise ValueError('Invalid image data.')
 if len(data)>MAX_IMAGE or len(data)<33 or data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR' or int.from_bytes(data[16:20],'big')!=1424 or int.from_bytes(data[20:24],'big')!=280:
  raise ValueError('Expected a prepared 1424 × 280 PNG image.')
 return data

class ImageTransfer:
 def __init__(self,local_ip,device_ip,data):
  self.path='/'+secrets.token_urlsafe(32)+'.png';self.fetched=threading.Event()
  owner=self
  class Handler(http.server.BaseHTTPRequestHandler):
   def do_GET(self):
    if self.client_address[0]!=device_ip or self.path!=owner.path:
     self.send_error(404);return
    self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers()
    try:self.wfile.write(data);self.wfile.flush();owner.fetched.set()
    except OSError:pass
   def log_message(self,*args):pass
   def setup(self):
    super().setup();self.connection.settimeout(3)
  self.server=http.server.ThreadingHTTPServer((local_ip,0),Handler)
  self.server.daemon_threads=True
  self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.1},daemon=True)
 def start(self):
  self.thread.start()
  return 'http://%s:%s%s'%(*self.server.server_address,self.path)
 def close(self):
  self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

def show(client,encoded):
 data=image_bytes(encoded)
 sock=client.sock
 if not sock:raise RuntimeError('Connect to the Ultrabar first.')
 generation=client.generation
 transfer=ImageTransfer(sock.getsockname()[0],client.host,data)
 try:
  url=transfer.start()
  if generation!=client.generation:raise RuntimeError('Device connection changed; try again.')
  # This firmware's preview handler has no IReply call: success is verified by image fetch.
  client.send({'id':str(uuid.uuid4()),'act':30742,'data':{'mediaType':'IMAGE','url':url}})
  if not transfer.fetched.wait(15):
   raise RuntimeError('The Ultrabar did not fetch the image. Check that both devices can communicate over Wi-Fi. No wallpaper settings were changed.')
  return 'Image transferred to the Ultrabar. Tap its screen to close the preview.'
 finally:transfer.close()
