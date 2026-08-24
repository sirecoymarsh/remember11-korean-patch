"""Parser/rebuilder for Gestalt mac-en entries whose text pool reaches EOF."""
from __future__ import annotations
import struct

def parse(data:bytes,find_pointer_table):
 info=find_pointer_table(data)
 if not info: return None
 pos=info['text_offset'];items=[]
 while pos<len(data):
  z=data.find(b'\0',pos)
  if z<0:raise ValueError('unterminated Gestalt script text pool')
  items.append({'index':len(items),'offset':pos,'end':z,'raw':data[pos:z]});pos=z+1
 if pos!=len(data):raise ValueError('Gestalt text pool end mismatch')
 starts={x['offset'] for x in items};by={x['offset']:x['index'] for x in items}
 refs={i:[(q,p) for q,p in rs if p in starts] for i,rs in info['refs'].items()}
 choices=set()
 for q in range(0,info['text_offset']-7,2):
  ptr=struct.unpack_from('<H',data,q)[0]
  if ptr in by and data[q+2:q+6]==b'\xff\xff\x01\x00':choices.add(by[ptr])
 return {'text_offset':info['text_offset'],'items':items,'refs':refs,'choice_indices':choices}

def rebuild(data:bytes,obj:dict,targets:list[bytes]):
 if len(targets)!=len(obj['items']):raise ValueError('Gestalt target count mismatch')
 prefix=bytearray(data[:obj['text_offset']]);text=bytearray();old_to_new={};cursor=obj['text_offset']
 for item,target in zip(obj['items'],targets):
  if b'\0'in target:raise ValueError(f'NUL in Gestalt target {item["index"]}')
  if cursor>0xffff:raise ValueError(f'16-bit Gestalt text offset overflow {cursor:#x}')
  old_to_new[item['offset']]=cursor;text.extend(target);text.append(0);cursor+=len(target)+1
 for q in range(0,len(prefix)-1,2):
  old=struct.unpack_from('<H',prefix,q)[0]
  if old in old_to_new:struct.pack_into('<H',prefix,q,old_to_new[old])
 return bytes(prefix)+bytes(text)
