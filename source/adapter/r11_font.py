"""Build the PC FNT2626.FOP with Hangul carrier glyphs."""
from __future__ import annotations
import argparse,json,re,struct
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
HEADER=struct.Struct('<8sIIIIHBBBB')
PIXEL_SHIFTS=(6,2,4,0)
# The stored 2-bit value IS the opacity level: 0 transparent .. 3 fully inked.
# Measured on the untouched Japanese font: level-3 pixels sit inside strokes
# (interior ratio 0.75) while level-1 pixels sit on stroke edges (0.18), and
# 77% of all ink is level 3. Remapping the levels inverts the antialiasing,
# which renders text as a pale body wrapped in a hard black fringe.
SS=4              # supersample factor used while rasterising
# Where the original font places full-width ink inside the 48x48 cell. The two
# metadata bytes are (left, right) in 2px units and full-width glyphs carry
# (0, 17), so the engine advances 34px and expects the ink to sit in this box.
INK_BOX=(1,8,35,42)

def parse_carriers(table_path:Path)->list[tuple[int,bytes,str]]:
 out=[]
 for line in table_path.read_text(encoding='utf-8').splitlines():
  m=re.match(r'^(\d+):\s*0x([0-9A-Fa-f]{4})\s*(.*)$',line)
  if not m: continue
  # Notes after a tab/# are metadata, not glyph characters.
  tail=m.group(3).split('#',1)[0].strip()
  char=tail.split('\t',1)[0].strip()
  idx=int(m.group(1)); code=bytes.fromhex(m.group(2))
  out.append((idx,code,char))
 return out

def decode_block(block:bytes,width=48,height=48)->Image.Image:
 im=Image.new('L',(width,height),255);px=im.load(); rowbytes=len(block)//height
 for y in range(height):
  for k,bt in enumerate(block[y*rowbytes:(y+1)*rowbytes]):
   for q,shift in enumerate(PIXEL_SHIFTS): px[k*4+q,y]=255-((bt>>shift)&3)*85
 return im

def encode_image(im:Image.Image)->bytes:
 if im.size!=(48,48): raise ValueError(im.size)
 src=im.convert('L');px=src.load();out=bytearray(0x240)
 for y in range(48):
  for k in range(12):
   bt=0
   for q,shift in enumerate(PIXEL_SHIFTS):
    level=max(0,min(3,round((255-px[k*4+q,y])/85)))
    bt |= level << shift
   out[y*12+k]=bt
 return bytes(out)

def _sized(font_path:Path,px:int,weight:int|None)->ImageFont.FreeTypeFont:
 font=ImageFont.truetype(str(font_path),px)
 if weight is None: return font
 # NotoSansKR-VF defaults to Thin (100), which falls apart at 2-bit depth.
 try:
  axes=font.get_variation_axes()
  values=[]
  for axis in axes:
   name=axis.get('name',b'')
   if isinstance(name,bytes): name=name.decode('ascii','ignore')
   value=weight if 'weight' in str(name).lower() else axis.get('default',axis['minimum'])
   values.append(max(axis['minimum'],min(axis['maximum'],value)))
  if values: font.set_variation_by_axes(values)
 except OSError:
  pass
 return font

# Median ink extent of the original full-width glyphs, in cell pixels. Hangul
# syllable extents vary far more than kanji do, so fitting the union of the set
# lets the few tallest syllables set the size and leaves every ordinary glyph
# too small for the 34px cell -- the run then reads as loose and thin.
TARGET_INK=(33.5,32.0)

class Fitter:
 """One shared size, width scale and pen origin for every glyph.

 Per-glyph bbox centring makes syllables without a batchim float and shifts
 every glyph off the advance box the engine reserves. Fitting the set once,
 then drawing all glyphs from the same baseline, keeps the run aligned and lets
 the font's own metrics centre each syllable.
 """
 def __init__(self,font_path:Path,weight:int|None,chars:str,box=INK_BOX,width_scale:float|None=None,target=TARGET_INK):
  probe=chars[::max(1,len(chars)//120)][:120] or chars
  target_w,target_h=target
  # Size follows the median ink height, not the tallest syllable.
  lo,hi=10.0,60.0
  for _ in range(14):
   size=(lo+hi)/2
   if self._median(_sized(font_path,round(size*SS),weight),probe)[1]>target_h: hi=size
   else: lo=size
  self.size=round(lo,2); self.font=_sized(font_path,round(lo*SS),weight)
  mw,mh=self._median(self.font,probe)
  # Hangul is narrower than kanji at the same optical size. Widen it to the
  # original's median width, at supersample resolution so nothing is resampled
  # after quantisation.
  self.width_scale=round(target_w/mw,4) if width_scale is None else width_scale
  self.median=(round(mw*self.width_scale,1),round(mh,1))
  bb=self._union(self.font,chars)
  w=(bb[2]-bb[0])*self.width_scale; h=bb[3]-bb[1]
  # render() scales the whole canvas horizontally, so the pen has to be placed
  # in pre-scale coordinates: ink lands at width_scale * (dx + bb[0] - 48*SS).
  left=box[0]*SS+((box[2]-box[0])*SS-w)/2
  self.dx=round(left/self.width_scale-bb[0]+48*SS)
  self.dy=round(box[1]*SS+((box[3]-box[1])*SS-h)/2-bb[1]+48*SS)
  self.union=(round(w/SS,1),round(h/SS,1))

 @staticmethod
 def _bbox(font:ImageFont.FreeTypeFont,ch:str):
  im=Image.new('L',(48*SS*3,48*SS*3),255)
  ImageDraw.Draw(im).text((48*SS,48*SS),ch,font=font,fill=0,anchor='ls')
  return Image.eval(im,lambda v:255-v).getbbox()

 @classmethod
 def _median(cls,font:ImageFont.FreeTypeFont,chars:str):
  ws,hs=[],[]
  for ch in chars:
   bb=cls._bbox(font,ch)
   if bb: ws.append((bb[2]-bb[0])/SS); hs.append((bb[3]-bb[1])/SS)
  if not ws: raise ValueError('no ink')
  ws.sort(); hs.sort()
  return ws[len(ws)//2],hs[len(hs)//2]

 @staticmethod
 def _union(font:ImageFont.FreeTypeFont,chars:str):
  probe=Image.new('L',(48*SS*3,48*SS*3),255);d=ImageDraw.Draw(probe)
  for ch in chars: d.text((48*SS,48*SS),ch,font=font,fill=0,anchor='ls')
  bb=Image.eval(probe,lambda v:255-v).getbbox()
  if bb is None: raise ValueError('no ink')
  return bb

 def render(self,ch:str)->Image.Image:
  big=Image.new('L',(48*SS,48*SS),255)
  ImageDraw.Draw(big).text((self.dx,self.dy),ch,font=self.font,fill=0,anchor='ls')
  if self.width_scale!=1.0:
   # Scale at supersample resolution, never after quantisation.
   big=big.resize((round(48*SS*self.width_scale),48*SS),Image.Resampling.LANCZOS)
   out=Image.new('L',(48*SS,48*SS),255);out.paste(big,(0,0));big=out
  # Box filter to the cell, then straight to the engine's 4 opacity levels.
  return big.resize((48,48),Image.Resampling.BOX)

def collect_unencodable(texts:list[str])->list[str]:
 chars=set()
 for text in texts:
  # formatting controls are ASCII and remain native; only unencodable visible chars need carriers.
  for ch in text:
   try: ch.encode('cp932')
   except UnicodeEncodeError: chars.add(ch)
 return sorted(chars,key=ord)

def build_font(base_fop:Path,table_path:Path,texts:list[str],font_path:Path,out_fop:Path,map_path:Path,font_size:int=34,native_texts:list[str]|None=None,font_weight:int=600,reference_fop:Path|None=None,hangul_width_scale:float|None=None,carrier_map:dict|None=None):
 data=bytearray(base_fop.read_bytes()); magic,metaoff,metasize,glyphoff,glyphsize,blocksize,magic1,w,h,magic2=HEADER.unpack_from(data)
 if (metaoff,metasize,glyphoff,blocksize,w,h)!=(0x1e,0x4000,0x5000,0x240,48,48): raise ValueError('unexpected PC FOP header')
 needed=collect_unencodable(texts); native=set()
 for text in (native_texts if native_texts is not None else texts):
  for ch in text:
   try:
    raw=ch.encode('cp932')
    if len(raw)==2:native.add(raw)
   except UnicodeEncodeError:pass
 if carrier_map is not None:
  # Reuse a previously published assignment so already-encoded text stays valid.
  missing=[ch for ch in needed if ch not in carrier_map]
  if missing: raise ValueError(f'{len(missing)} chars absent from the carrier map: {"".join(missing[:20])}')
  pairs=[(ch,carrier_map[ch]['index'],bytes.fromhex(carrier_map[ch]['code_hex'])) for ch in needed]
  stats_extra={'carrier_map_reused':True}
 else:
  carriers=parse_carriers(table_path)
  # Preserve the English patch custom glyph bank used by transient/floating
  # strings outside the ordinary dialogue pool.
  protected=set()
  if reference_fop is not None:
   ref=reference_fop.read_bytes()
   if len(ref)!=len(data): raise ValueError('reference FOP size mismatch')
   for idx in range(glyphsize//blocksize):
    a=glyphoff+idx*blocksize;b=a+blocksize
    if data[a:b]!=ref[a:b] or data[metaoff+idx*2:metaoff+idx*2+2]!=ref[metaoff+idx*2:metaoff+idx*2+2]:
     protected.add(idx)
  # Prefer undefined CP932 slots not owned by the English patch. If additional
  # capacity is required, take only unused CJK ideographs, never punctuation,
  # symbols, spacing codes, kana, or Latin extension glyphs.
  blank=[x for x in carriers if not x[2] and x[1] not in native and x[0] not in protected]
  cjk=[x for x in carriers if len(x[2])==1 and 0x3400<=ord(x[2])<=0x9FFF and x[1] not in native and x[0] not in protected]
  candidates=blank+cjk
  if len(needed)>len(candidates): raise ValueError(f'need {len(needed)} carriers, have {len(candidates)}')
  pairs=[(ch,idx,code) for ch,(idx,code,_) in zip(needed,candidates)]
  stats_extra={'carrier_map_reused':False,'protected_source_glyphs':len(protected),'blank_carriers_available':len(blank),'cjk_carriers_available':len(cjk)}
 hangul=''.join(ch for ch in needed if 0xAC00<=ord(ch)<=0xD7A3) or ''.join(needed)
 fitter=Fitter(font_path,font_weight,hangul,INK_BOX,hangul_width_scale)
 mapping={}
 for ch,idx,code in pairs:
  data[glyphoff+idx*blocksize:glyphoff+(idx+1)*blocksize]=encode_image(fitter.render(ch))
  data[metaoff+idx*2:metaoff+idx*2+2]=bytes((0,17))
  mapping[ch]={'index':idx,'code_hex':code.hex().upper()}
 out_fop.parent.mkdir(parents=True,exist_ok=True);out_fop.write_bytes(data)
 map_path.parent.mkdir(parents=True,exist_ok=True);map_path.write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding='utf-8')
 return {'hangul_carriers':len(mapping),'font':str(font_path),'fitted_size':fitter.size,'median_ink':fitter.median,'union_ink':fitter.union,'ink_box':INK_BOX,'font_weight':font_weight,'hangul_width_scale':fitter.width_scale,**stats_extra}

def encode_target(text:str,mapping:dict)->bytes:
 out=bytearray()
 for ch in text:
  if ch in mapping: out.extend(bytes.fromhex(mapping[ch]['code_hex']))
  else: out.extend(ch.encode('cp932'))
 return bytes(out)

def main():
 ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
 b=sub.add_parser('build');b.add_argument('base_fop',type=Path);b.add_argument('table',type=Path);b.add_argument('translations',type=Path);b.add_argument('out_fop',type=Path);b.add_argument('map',type=Path);b.add_argument('--font',type=Path,default=Path(r'C:\Windows\Fonts\NotoSansKR-VF.ttf'));b.add_argument('--size',type=int,default=34);b.add_argument('--weight',type=int,default=600)
 a=ap.parse_args()
 if a.cmd=='build':
  obj=json.loads(a.translations.read_text(encoding='utf-8'));texts=[x['target_ko'] for x in obj['translations']]
  print(json.dumps(build_font(a.base_fop,a.table,texts,a.font,a.out_fop,a.map,a.size,font_weight=a.weight),ensure_ascii=False))
if __name__=='__main__':main()
