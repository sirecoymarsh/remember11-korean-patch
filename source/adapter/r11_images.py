"""Extract and rebuild Remember11 PNG-backed BIP/T2P containers."""
from __future__ import annotations
import argparse,io,json,struct
from pathlib import Path
from PIL import Image

def align(n,a=16):return (n+a-1)&~(a-1)

def png_info(data:bytes):
 im=Image.open(io.BytesIO(data));return im.size,im.mode

def extract_type3(data:bytes):
 count=struct.unpack_from('<I',data,0)[0];pos=align((count+1)*4);items=[]
 for i in range(count):
  if data[pos:pos+4]!=b'TIM2' or data[pos+64:pos+72]!=b'PNGFILE3':
   raise ValueError(f'invalid PNGFILE3 at {pos:#x}, item {i}/{count}')
  part=struct.unpack_from('<I',data,pos+88)[0]; png_size=part-124; png_start=pos+188
  name=data[pos+92:pos+156].split(b'\0',1)[0].decode('cp932','replace')
  png=data[png_start:png_start+png_size]
  items.append({'index':i,'offset':pos,'prefix':data[pos:png_start],'png':png,'suffix':data[png_start+png_size:align(pos+64+part)],'name':name})
  pos=align(pos+64+part)
 return {'kind':'type3','count':count,'header':data[:align((count+1)*4)],'items':items,'tail':data[pos:]}

def extract_type2(data:bytes):
 marker=data.find(b'EMUARC__');
 if marker<0:raise ValueError('EMUARC__ not found')
 pos=marker+8;items=[];i=0
 while pos<len(data):
  if data[pos:pos+8]!=b'PNGFILE2':raise ValueError(f'invalid PNGFILE2 at {pos:#x}')
  part=struct.unpack_from('<I',data,pos+24)[0];png_start=pos+124;png=data[png_start:pos+part]
  name=data[pos+28:pos+92].split(b'\0',1)[0].decode('cp932','replace')
  items.append({'index':i,'offset':pos,'prefix':data[pos:png_start],'png':png,'name':name});pos+=part;i+=1
 return {'kind':'type2','count':len(items),'header':data[:marker+8],'items':items,'tail':data[pos:]}

def parse(data:bytes):
 if b'EMUARC__' in data:return extract_type2(data)
 if b'PNGFILE3' in data:return extract_type3(data)
 raise ValueError('unsupported image container')

def extract(path:Path,outdir:Path):
 obj=parse(path.read_bytes());outdir.mkdir(parents=True,exist_ok=True);manifest={'source':str(path),'kind':obj['kind'],'count':obj['count'],'items':[]}
 for x in obj['items']:
  safe=Path(x['name']).stem or f'image{x["index"]}'
  q=outdir/f'{x["index"]:03d}__{safe}.png';q.write_bytes(x['png']);size,mode=png_info(x['png']);manifest['items'].append({'index':x['index'],'name':x['name'],'file':q.name,'width':size[0],'height':size[1],'mode':mode})
 (outdir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');return manifest

def rebuild(data:bytes,replacements:dict[int,bytes]):
 obj=parse(data);out=bytearray(obj['header']);payload_base=len(out)
 for x in obj['items']:
  png=replacements.get(x['index'],x['png'])
  old_size=Image.open(io.BytesIO(x['png'])).size;new_size=Image.open(io.BytesIO(png)).size
  if new_size!=old_size:raise ValueError(f'canvas changed {x["name"]}: {old_size}->{new_size}')
  prefix=bytearray(x['prefix'])
  if obj['kind']=='type3':
   if (len(out)-payload_base)%16:raise ValueError('unaligned PNGFILE3 payload')
   struct.pack_into('<I',out,4+x['index']*4,(len(out)-payload_base)//16)
   part=124+len(png);struct.pack_into('<III',prefix,16,part,0,part);struct.pack_into('<I',prefix,88,part);unit=bytes(prefix)+png;out.extend(unit);out.extend(b'\0'*(align(len(out))-len(out)))
  else:
   # PNGFILE2/T2P stores one 28-byte descriptor per image in the header.
   # Its final DWORD is the image offset relative to the EMUARC__ payload.
   # PNG recompression changes all later positions, so rebuild that table.
   desc_offset=0xA4+x['index']*0x1C
   if desc_offset+4>payload_base:raise ValueError('PNGFILE2 descriptor table overflow')
   struct.pack_into('<I',out,desc_offset,len(out)-payload_base)
   part=124+len(png);struct.pack_into('<I',prefix,24,part);out.extend(prefix);out.extend(png)
 out.extend(obj['tail'])
 if obj['kind']=='type2':struct.pack_into('<I',out,20,len(out))
 return bytes(out)

def main():
 ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True);ex=sub.add_parser('extract');ex.add_argument('input',type=Path);ex.add_argument('output',type=Path);a=ap.parse_args()
 if a.cmd=='extract':print(json.dumps(extract(a.input,a.output),ensure_ascii=False))
if __name__=='__main__':main()
