from __future__ import annotations
import io,json,sys,struct
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).parent));from r11_images import parse,rebuild
FONT=Path(r'C:\Windows\Fonts\NotoSansKR-VF.ttf')
KEEP_LABELS={'SONY','PlayStation','SELECT','START','ANALOG','???'}
def inpaint_rectangles(im:Image.Image,blocks):
 arr=np.array(im.convert('RGBA'));mask=np.zeros(arr.shape[:2],np.uint8);h,w=mask.shape
 for b in blocks:
  if b['source_jp'] in KEEP_LABELS or b['target_ko']==b['source_jp']:continue
  x0,y0,x1,y1=[int(v) for v in b['bbox']];x0=max(0,min(w,x0));x1=max(0,min(w,x1));y0=max(0,min(h,y0));y1=max(0,min(h,y1))
  if x1>x0 and y1>y0:cv2.rectangle(mask,(x0,y0),(x1-1,y1-1),255,-1)
 # Inpaint all channels, including alpha, so source glyphs are removed rather than covered.
 out=np.empty_like(arr)
 for c in range(4):out[:,:,c]=cv2.inpaint(arr[:,:,c],mask,4,cv2.INPAINT_TELEA)
 return Image.fromarray(out,'RGBA')
def estimate_style(original,bbox):
 a=np.array(original.convert('RGBA'));h,w=a.shape[:2];x0,y0,x1,y1=[int(v) for v in bbox];x0=max(0,min(w-1,x0));x1=max(x0+1,min(w,x1));y0=max(0,min(h-1,y0));y1=max(y0+1,min(h,y1));roi=a[y0:y1,x0:x1];lum=.2126*roi[:,:,0]+.7152*roi[:,:,1]+.0722*roi[:,:,2];bg=float(np.median(lum));
 if bg>135:
  sel=roi[lum<=np.percentile(lum,20)];fill=(35,35,35,235);stroke=(240,240,240,100)
 else:
  sel=roi[lum>=np.percentile(lum,80)];fill=(220,220,220,235);stroke=(15,15,15,180)
 if len(sel):
  rgb=np.median(sel[:,:3],axis=0).astype(int);alpha=int(np.clip(np.median(sel[:,3]),150,255));fill=tuple(map(int,rgb))+(alpha,)
 return fill,stroke
def ui_font(size,weight=500):
 f=ImageFont.truetype(str(FONT),size)
 try:
  axes=f.get_variation_axes();values=[]
  for axis in axes:
   name=axis.get('name',b'')
   if isinstance(name,bytes):name=name.decode('ascii','ignore')
   value=weight if 'weight' in str(name).lower() else axis.get('default',axis['minimum'])
   values.append(max(axis['minimum'],min(axis['maximum'],value)))
  if values:f.set_variation_by_axes(values)
 except OSError:
  pass
 return f
def fit_font(text,box,max_size=36):
 x0,y0,x1,y1=box;W=max(1,x1-x0-4);H=max(1,y1-y0-2);vertical=H>W*1.45 and len(text)>1
 render='\n'.join(text) if vertical else text
 for size in range(min(max_size,max(4,H)),3,-1):
  f=ui_font(size);d=ImageDraw.Draw(Image.new('L',(2,2)));bb=d.multiline_textbbox((0,0),render,font=f,spacing=0,stroke_width=1,align='center')
  if bb[2]-bb[0]<=W and bb[3]-bb[1]<=H:return f,render,vertical
 return ui_font(4),render,vertical

def render_asset(original:Image.Image,blocks):
 cleaned=inpaint_rectangles(original,blocks)
 for b in blocks:
  if b['source_jp'] in KEEP_LABELS or b['target_ko']==b['source_jp']:continue
  x0,y0,x1,y1=[int(v) for v in b['bbox']];x0=max(0,min(cleaned.width,x0));x1=max(0,min(cleaned.width,x1));y0=max(0,min(cleaned.height,y0));y1=max(0,min(cleaned.height,y1));
  if x1<=x0 or y1<=y0:continue
  fill,stroke=estimate_style(original,(x0,y0,x1,y1));font,text,vertical=fit_font(b['target_ko'],(x0,y0,x1,y1),max_size=40)
  probe=ImageDraw.Draw(Image.new('L',(2,2)));bb=probe.multiline_textbbox((0,0),text,font=font,spacing=0,stroke_width=1,align='center');tw,th=max(1,int(round(bb[2]-bb[0]))),max(1,int(round(bb[3]-bb[1])))
  # Draw each replacement on an isolated layer. If even the 4 px font is
  # wider than the original label box, condense the rendered glyphs rather
  # than allowing them to bleed into neighbouring original artwork.
  layer=Image.new('RGBA',(max(1,tw+2),max(1,th+2)),(0,0,0,0));ld=ImageDraw.Draw(layer)
  ld.multiline_text((1-bb[0],1-bb[1]),text,font=font,fill=fill,stroke_width=1,stroke_fill=stroke,spacing=0,align='center')
  maxw=max(1,x1-x0-2);maxh=max(1,y1-y0-1)
  scale=min(1.0,maxw/layer.width,maxh/layer.height)
  if scale<1.0:
   layer=layer.resize((max(1,round(layer.width*scale)),max(1,round(layer.height*scale))),Image.Resampling.LANCZOS)
  align=b.get('align','center');tx=x0+1 if align=='left' else x1-layer.width-1 if align=='right' else x0+(x1-x0-layer.width)//2;ty=y0+(y1-y0-layer.height)//2
  # alpha_composite with an explicit destination clips to the original box
  # because the fitted layer is guaranteed to lie within it.
  cleaned.alpha_composite(layer,(int(tx),int(ty)))
 return cleaned
def full_type2(obj):
 parts=[];fw=fh=0
 for x in obj['items']:
  pr=x['prefix'];FW,_,FH,_=struct.unpack_from('<hhhh',pr,16);ox,oy,pw,ph=struct.unpack_from('<iiii',pr,108);fw=max(fw,FW,ox+pw);fh=max(fh,FH,oy+ph);parts.append((x,ox,oy,pw,ph))
 im=Image.new('RGBA',(fw,fh))
 for x,ox,oy,pw,ph in parts:im.alpha_composite(Image.open(io.BytesIO(x['png'])).convert('RGBA'),(ox,oy))
 return im,parts
def png_bytes(im):
 q=io.BytesIO();im.save(q,format='PNG',optimize=True);return q.getvalue()
def load_image_translations(root):
 merged={}
 for folder in ('image-ui','image-ui-retry'):
  for p in sorted((root/'translations'/folder).glob('packet-*.json')):
   for a in json.loads(p.read_text(encoding='utf-8'))['assets']:merged[a['filename']]=a
 return merged
def load_etc_jobs(root):
 jobs=[]
 for pp in sorted((root/'packets'/'etc-ui').glob('packet-*.json')):
  op=root/'translations'/'etc-ui'/pp.name;inp=json.loads(pp.read_text(encoding='utf-8'))['files'];assets=json.loads(op.read_text(encoding='utf-8'))['assets']
  if len(inp)!=len(assets):raise ValueError(pp)
  jobs.extend(zip(map(Path,inp),assets))
 return jobs
def build(root:Path):
 outroot=root/'ui'/'rendered';outroot.mkdir(parents=True,exist_ok=True);audit={'etc':[],'bg':[],'ev':[]}
 # ETC component sprites and rebuilt decoded BIPs
 by_bip={}
 for src,a in load_etc_jobs(root):
  im=Image.open(src).convert('RGBA');fixed=[]
  for b in a['blocks']:
   bb=b['bbox'];fixed.append({**b,'bbox':[max(0,min(im.width,bb[0])),max(0,min(im.height,bb[1])),max(0,min(im.width,bb[2])),max(0,min(im.height,bb[3]))]})
  rendered=render_asset(im,fixed);rel=src.relative_to(root/'ui'/'etc-jp');q=outroot/'etc-components'/rel;q.parent.mkdir(parents=True,exist_ok=True);rendered.save(q)
  archive=src.parent.name;index=int(src.name.split('__')[0]);by_bip.setdefault(archive,{})[index]=png_bytes(rendered);audit['etc'].append({'source':str(rel),'blocks':len(fixed),'output':str(q)})
 decoded_out=outroot/'etc-decoded';decoded_out.mkdir(parents=True,exist_ok=True)
 for archive,repls in by_bip.items():
  src=next((root/'extracted'/'etc-jp'/'decoded').glob(archive+'.*'));(decoded_out/src.name).write_bytes(rebuild(src.read_bytes(),repls))
 # BG/EV full overlay canvases, split back to original tiles, rebuild BIPs
 trans=load_image_translations(root)
 for filename,a in sorted(trans.items()):
  if not a['blocks']:continue
  kind,idxs,_=filename.split('-',2);idx=int(idxs);src=next((root/'extracted'/f'{kind}-jp'/'raw').glob(f'{idx:04d}__*'));obj=parse(src.read_bytes());full,parts=full_type2(obj);rendered=render_asset(full,a['blocks']);q=outroot/'image-canvases'/filename.replace('-jp.png','-ko.png');q.parent.mkdir(parents=True,exist_ok=True);rendered.save(q)
  repl={}
  for x,ox,oy,pw,ph in parts:repl[x['index']]=png_bytes(rendered.crop((ox,oy,ox+pw,oy+ph)))
  rawq=outroot/f'{kind}-raw'/src.name;rawq.parent.mkdir(parents=True,exist_ok=True);rawq.write_bytes(rebuild(src.read_bytes(),repl));audit[kind].append({'index':idx,'blocks':len(a['blocks']),'canvas':str(q),'raw':str(rawq)})
 (outroot/'ui-build-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:len(v) for k,v in audit.items()},ensure_ascii=False))
if __name__=='__main__':build(Path(sys.argv[1]))
