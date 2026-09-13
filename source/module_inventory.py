"""Combine discovery and registered state without treating scan absence as offline."""
import copy,json,pathlib

def combine(discovered,registered,known):
 states={r['serialNo']:r for r in registered if isinstance(r,dict) and isinstance(r.get('serialNo'),str)}
 fresh={r['serialNumber']:r for r in discovered if isinstance(r,dict) and isinstance(r.get('serialNumber'),str)}
 cache={r['serialNumber']:copy.deepcopy(r) for r in known if isinstance(r,dict) and isinstance(r.get('serialNumber'),str)}
 result=[]
 for sn in sorted(set(fresh)|set(states)):
  d=cache.get(sn,{'serialNumber':sn});d.update(fresh.get(sn,{}))
  d['seenInScan']=sn in fresh
  online=states.get(sn,{}).get('online')
  d['registeredOnline']=online if type(online) is bool else None
  d['status']='Online' if online is True else ('Seen in scan · reports offline' if sn in fresh and online is False else ('Seen in scan' if sn in fresh else ('Offline' if online is False else 'Status unknown')))
  d['available']=online is True or sn in fresh
  result.append(d)
 return result

def known_for(directory,host,registered):
 root=pathlib.Path(directory);p=root/'module-inventory.json';known=[]
 if p.exists():
  record=json.loads(p.read_text())
  if record.get('host')==host:known=record.get('modules',[])
 # Older versions stored descriptors only in gateway change records. Recover a
 # descriptor only when its hardware serial is registered on this live device.
 matched={r.get('serialNo') for r in registered if isinstance(r,dict)}
 ids={m.get('serialNumber') for m in known}
 for p in sorted((root/'backups').glob('gateway-*.json'),reverse=True):
  try:record=json.loads(p.read_text())
  except (ValueError,OSError):continue
  if record.get('host',host)!=host:continue
  for gateway in record.get('requested',{}).values():
   if not isinstance(gateway,dict):continue
   for m in gateway.get('endpoints',[]):
    sn=m.get('serialNumber')
    if sn in matched and sn not in ids:known.append(m);ids.add(sn)
 return known
