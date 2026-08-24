from __future__ import annotations
import argparse,io,json,re,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageChops
sys.path.insert(0,str(Path(__file__).parent));from r11_images import parse

def full_type2(obj):
 fw=fh=0;positions=[]
 for x in obj['items']:
  p=x['prefix'];fw0,_,fh0,_=__import__('struct').unpack_from('<hhhh',p,16);ox,oy,pw,ph=__import__('struct').unpack_from('<iiii',p,108);fw=max(fw,fw0,ox+pw);fh=max(fh,fh0,oy+ph);positions.append((ox,oy))
 im=Image.new('RGBA',(fw,fh));
 for x,pos in zip(obj['items'],positions):im.alpha_composite(Image.open(io.BytesIO(x['png'])).convert('RGBA'),pos)
 return im

def first_image(data):
 obj=parse(data)
 if obj['kind']=='type2':return full_type2(obj)
 # choose the visually dominant image in a multi-image UI archive
 ims=[Image.open(io.BytesIO(x['png'])).convert('RGBA') for x in obj['items']];return max(ims,key=lambda im:im.width*im.height)

def make_sheet(items,out):
 tw,th=240,180;cols=4;rows=(len(items)+cols-1)//cols;font=ImageFont.truetype(r'C:\Windows\Fonts\malgun.ttf',13)
 sh=Image.new('RGB',(cols*tw,rows*(th+30)),'white');d=ImageDraw.Draw(sh)
 for j,(label,im) in enumerate(items):
  im=im.copy();im.thumbnail((tw-8,th-8));x=(j%cols)*tw+(tw-im.width)//2;y=(j//cols)*(th+30)+20+(th-im.height)//2;bg=Image.new('RGB',im.size,(90,90,90));
  if im.mode=='RGBA':bg.paste(im,mask=im.getchannel('A'))
  else:bg.paste(im)
  sh.paste(bg,(x,y));d.text(((j%cols)*tw+4,(j//cols)*(th+30)+2),label,fill='black',font=font)
 out.parent.mkdir(parents=True,exist_ok=True);sh.save(out,quality=72,optimize=True)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('project',type=Path);a=ap.parse_args();root=a.project;items=[]
 # ETC Japanese image UI containers
 for p in sorted((root/'extracted'/'etc-jp'/'decoded').glob('*')):
  try:im=first_image(p.read_bytes())
  except Exception:continue
  items.append((p.name,im))
 # Japanese BG/EV entries known to contain localized text in the paired PC release
 dif=json.loads((root/'audit'/'archive_pair_diff.json').read_text(encoding='utf-8'))
 pairs={Path(x['japanese']).stem:x for x in dif['pairs']}
 for kind in ('bg','ev'):
  for rec in pairs[kind]['changed']:
   idx=rec['index'];p=next((root/'extracted'/f'{kind}-jp'/'raw').glob(f'{idx:04d}__*'));items.append((f'{kind.upper()} {p.name}',first_image(p.read_bytes())))
 make_sheet(items,root/'ui'/'audit'/'japanese-ui-contact-sheet.jpg')
 print(json.dumps({'items':len(items),'sheet':str(root/'ui'/'audit'/'japanese-ui-contact-sheet.jpg')},ensure_ascii=False))
if __name__=='__main__':main()

