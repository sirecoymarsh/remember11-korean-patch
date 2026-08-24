"""Append-only, pointer-safe Remember11 PC init.rp localization."""
from __future__ import annotations
import json,struct
from pathlib import Path

def load_targets(data_dir:Path,mode:str)->dict[int,dict]:
 data_dir=Path(data_dir)
 tip_name='tips-ko-base.json' if mode=='base' else 'tips-ko.json'
 rows=[]
 rows += json.loads((data_dir/tip_name).read_text(encoding='utf-8'))['mappings']
 if mode=='gestalt':
  chronology=json.loads((data_dir/'chronology-ko-pages.json').read_text(encoding='utf-8'))
  rows += [{'site':int(site,16),'target_ko':target,'kind':'chronology'} for site,target in chronology.items()]
 out={}
 for row in rows:
  site=int(row['site']);target=row['target_ko']
  if site in out and out[site]['target_ko']!=target:raise ValueError(f'init target collision at {site:#x}')
  out[site]={'site':site,'pointer':row.get('pointer'),'padding_90':int(row.get('padding_90',0)),'target_ko':target,'kind':row.get('kind','tips' if 'tip'in row else 'ui')}
 return out

def target_texts(data_dir:Path,mode:str)->list[str]:
 return [x['target_ko'] for x in load_targets(data_dir,mode).values()]

def rebuild(decoded:bytes,targets:dict[int,dict],encode_text):
 out=bytearray(decoded);cache={};audit=[]
 for site,row in sorted(targets.items()):
  if site<0 or site+4>len(decoded) or site%4:raise ValueError(f'invalid init pointer site {site:#x}')
  old=struct.unpack_from('<I',decoded,site)[0]
  if row.get('pointer') is not None and old!=int(row['pointer']):raise ValueError(f'init source pointer mismatch {site:#x}: {old:#x}!={int(row["pointer"]):#x}')
  if not (0<=old<len(decoded)):raise ValueError(f'init source pointer out of range {site:#x}->{old:#x}')
  payload=b'\x90'*row['padding_90']+encode_text(row['target_ko'])+b'\0'
  key=payload
  if key not in cache:
   cache[key]=len(out);out.extend(payload)
  new=cache[key];struct.pack_into('<I',out,site,new)
  audit.append({'site':site,'old_pointer':old,'new_pointer':new,'kind':row['kind'],'target_ko':row['target_ko'],'encoded_size':len(payload)-1})
 # Authoritative round-trip check on every modified pointer.
 for row in audit:
  ptr=struct.unpack_from('<I',out,row['site'])[0];payload=b'\x90'*targets[row['site']]['padding_90']+encode_text(row['target_ko'])
  if out[ptr:ptr+len(payload)]!=payload or out[ptr+len(payload)]!=0:raise ValueError(f'init output mismatch at {row["site"]:#x}')
 return bytes(out),{'modified_pointer_sites':len(audit),'unique_appended_strings':len(cache),'source_size':len(decoded),'output_size':len(out),'by_kind':{k:sum(x['kind']==k for x in audit) for k in sorted({x['kind'] for x in audit})},'mappings':audit}
