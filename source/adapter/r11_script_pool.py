"""Parse/rebuild the complete Remember11 PC script string pools."""
from __future__ import annotations
import argparse,hashlib,json,re,struct
from pathlib import Path
CONTROL_RE=re.compile(r'%(?:TS\d{3}|T\d+|X\d{3}|C[0-9A-Fa-f]+|LC|FS|FE|TE|N|K|P|p|O)')
JP_RE=re.compile(r'[\u3040-\u30ff\u3400-\u9fff\uff01-\uff60]')

def find_pointer_table(data:bytes):
 starts=[]
 for q in range(len(data)-8):
  if data[q:q+2]!=b'\x73\x00' or struct.unpack_from('<H',data,q+4)[0]!=0:continue
  ptr=struct.unpack_from('<H',data,q+2)[0]
  if ptr>q and ptr<len(data):starts.append((q,ptr))
 if not starts:return None
 best=None
 for _,text_start in starts:
  refs={}
  for q in range(0,text_start-6):
   if data[q:q+2]!=b'\x73\x00':continue
   ptr,index=struct.unpack_from('<HH',data,q+2)
   if text_start<=ptr<len(data):refs.setdefault(index,[]).append((q,ptr))
  n=0
  while n in refs:n+=1
  if n and (best is None or n>best[0]):best=(n,text_start,refs)
 if best is None:return None
 n,text_start,refs=best
 return {'count':n,'text_offset':text_start,'refs':refs}

def _read_strings(data:bytes,start:int,end:int):
 items=[];pos=start;i=0
 while pos<end:
  z=data.find(b'\0',pos,end)
  if z<0:raise ValueError(f'unterminated text pool at {pos:#x}')
  raw=data[pos:z]
  try:text=raw.decode('cp932')
  except UnicodeDecodeError as e:raise ValueError(f'CP932 string {i} at {pos:#x}: {e}')
  items.append({'index':i,'offset':pos,'end':z,'raw':raw,'text':text});i+=1;pos=z+1
 if pos!=end:raise ValueError(f'text pool end mismatch {pos:#x}!={end:#x}')
 return items

def _longest_plain_run(data:bytes):
 runs=[];run=[];pos=0
 while pos<len(data):
  z=data.find(b'\0',pos)
  if z<0:break
  raw=data[pos:z]
  try:text=raw.decode('cp932');valid=bool(text) and all(ord(c)>=0x20 for c in text)
  except UnicodeDecodeError:text='';valid=False
  if valid:run.append({'offset':pos,'end':z,'raw':raw,'text':text})
  else:
   if run:runs.append(run);run=[]
  pos=z+1
 if run:runs.append(run)
 if not runs:return None
 run=max(runs,key=lambda x:sum(1 for y in x if JP_RE.search(y['text'])))
 if not any(JP_RE.search(x['text']) for x in run):return None
 for i,x in enumerate(run):x['index']=i
 return {'count':len(run),'text_offset':run[0]['offset'],'text_end':run[-1]['end']+1,'items':run,'refs':{},'suffix_size':len(data)-(run[-1]['end']+1),'mode':'fixed'}

def parse(data:bytes):
 info=find_pointer_table(data)
 if not info:return _longest_plain_run(data)
 # Standard retail scripts store all physical strings contiguously through a 12-byte tail.
 text_end=len(data)-12
 items=_read_strings(data,info['text_offset'],text_end)
 starts={x['offset'] for x in items}
 for index,refs in list(info['refs'].items()):
  valid=[(q,ptr) for q,ptr in refs if ptr in starts]
  if index<info['count'] and not valid:raise ValueError(f'no valid pointer for referenced string: {index}')
  info['refs'][index]=valid
 info['items']=items;info['physical_count']=len(items);info['text_end']=text_end;info['suffix_size']=12;info['mode']='relocatable'
 return info

def choice_string_indices(data:bytes,obj=None)->set[int]:
 # Choice rows use an eight-byte record: <string_ptr> FFFF 0001 <ordinal>.
 # The same physical string can also have a normal 73-opcode reference, so
 # testing only for the absence of normal references misclassifies choices.
 if obj is None:obj=parse(data)
 if not obj or obj.get('mode')!='relocatable':return set()
 by_offset={item['offset']:item['index'] for item in obj['items']}
 result=set()
 for q in range(0,obj['text_offset']-7,2):
  ptr=struct.unpack_from('<H',data,q)[0]
  if ptr in by_offset and data[q+2:q+6]==b'\xff\xff\x01\x00':
   result.add(by_offset[ptr])
 return result

def classify(text:str,entry:int)->str:
 if not text:return 'empty'
 # Pure engine identifiers and debug asset labels remain byte-identical.
 if re.fullmatch(r'[A-Za-z0-9_./@\\:+ -]+',text) and not re.search(r'\b(?:START|LOAD|SAVE|OPTION|ALBUM|MUSIC|HELP|EXIT)\b',text,re.I):return 'technical'
 if JP_RE.search(text):return 'translate'
 if re.search(r'[A-Za-z]',text):return 'translate' if entry in (155,156,157,162,163,164,165,166,167,168,169,170) else 'keep'
 return 'keep'

def catalog(decoded:Path,out:Path,stats:Path):
 rows=[];files=[]
 for path in sorted(decoded.glob('*.bin')):
  entry=int(path.name.split('__')[0]);obj=parse(path.read_bytes())
  if not obj:files.append({'entry':entry,'strings':0});continue
  files.append({'entry':entry,'strings':len(obj['items']),'referenced_strings':obj.get('count',0),'text_offset':obj['text_offset'],'text_end':obj['text_end'],'suffix_size':obj['suffix_size'],'mode':obj['mode']})
  for i,x in enumerate(obj['items']):
   rows.append({'key':f'mac.afs::{entry:04d}::{i:04d}','entry':entry,'string_index':i,'offset':x['offset'],'source_jp':x['text'],'controls':CONTROL_RE.findall(x['text']),'kind':classify(x['text'],entry),'storage':obj['mode'],'max_source_bytes':len(x['raw']) if obj['mode']=='fixed' else None,'previous_jp':obj['items'][i-1]['text'] if i else '','next_jp':obj['items'][i+1]['text'] if i+1<len(obj['items']) else '','source_sha1':hashlib.sha1(x['raw']).hexdigest()})
 out.parent.mkdir(parents=True,exist_ok=True)
 with out.open('w',encoding='utf-8',newline='\n') as f:
  for x in rows:f.write(json.dumps(x,ensure_ascii=False)+'\n')
 st={'total_strings':len(rows),'translate':sum(x['kind']=='translate' for x in rows),'keep':sum(x['kind']=='keep' for x in rows),'technical':sum(x['kind']=='technical' for x in rows),'empty':sum(x['kind']=='empty' for x in rows),'files':files}
 stats.write_text(json.dumps(st,ensure_ascii=False,indent=2),encoding='utf-8');return st

def rebuild(data:bytes,targets:list[bytes]):
 obj=parse(data)
 if not obj or len(targets)!=len(obj['items']):raise ValueError('target count mismatch')
 if obj['mode']=='fixed':
  out=bytearray(data)
  for item,target in zip(obj['items'],targets):
   if b'\0' in target:raise ValueError(f'NUL in target {item["index"]}')
   if len(target)>len(item['raw']):raise ValueError(f'fixed string overflow {item["index"]}: {len(target)}>{len(item["raw"])}')
   out[item['offset']:item['end']]=target+b' '*(len(item['raw'])-len(target))
  return bytes(out)
 prefix=bytearray(data[:obj['text_offset']]);text=bytearray();old_to_new={};offset=obj['text_offset']
 for item,target in zip(obj['items'],targets):
  if b'\0' in target:raise ValueError(f'NUL in target {item["index"]}')
  if offset>0xffff:raise ValueError(f'16-bit text offset overflow at {item["index"]}: {offset:#x}')
  old_to_new[item['offset']]=offset;text.extend(target);text.append(0);offset+=len(target)+1
 # Every aligned 16-bit value that targets the start of a physical string is
 # a relocatable script pointer. Dialogue opcodes use ``73 00 <ptr>``, while
 # choices store bare pointers in a separate table (followed by FFFF/flags).
 # Relocating only the 73-opcode form leaves choice pointers aimed inside newly
 # sized Korean strings and exposes fragments such as ``%%`` or ``K%``.
 for q in range(0,len(prefix)-1,2):
  oldptr=struct.unpack_from('<H',prefix,q)[0]
  if oldptr in old_to_new:struct.pack_into('<H',prefix,q,old_to_new[oldptr])
 return bytes(prefix)+bytes(text)+data[obj['text_end']:]

def main():
 ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='cmd',required=True);c=sp.add_parser('catalog');c.add_argument('decoded',type=Path);c.add_argument('out',type=Path);c.add_argument('stats',type=Path);a=ap.parse_args()
 if a.cmd=='catalog':print(json.dumps({k:v for k,v in catalog(a.decoded,a.out,a.stats).items() if k!='files'},ensure_ascii=False))
if __name__=='__main__':main()
