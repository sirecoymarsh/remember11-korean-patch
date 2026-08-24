from __future__ import annotations
import argparse,hashlib,json,struct,sys,zipfile
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def validate(root:Path,game:Path):
 root=root.resolve();game=game.resolve();sys.path.insert(0,str(root/'adapter'))
 from r11_tools import AfsArchive,decode_wrapped
 from r11_script_pool import find_pointer_table,parse as parse_pool
 from r11_gestalt_script import parse as parse_gestalt
 from r11_font import HEADER,encode_target
 from r11_exe_ui import validate_executable
 from r11_init import load_targets as load_init_targets
 from build_release import translations as load_base_translations
 src=root/'gestalt-analysis'/'extracted'/'R11-Gestalt-v1.3.0'/'v1.3.0';release=root/'release'/'Remember11-Korean-Gestalt';file=release/'FILE';manifest=json.loads((release/'patch-manifest.json').read_text(encoding='utf-8'))
 expected_files={'mac-en.afs','etc-en.afs','bg-en.afs','ev-en.afs','bgmpc-en.afs','bgmpc.afs','init.rp'};actual={x.name for x in file.iterdir() if x.is_file()};assert actual==expected_files,(actual,expected_files)
 assert (file/'movie'/'mved3.avi').is_file() and sha(file/'movie'/'mved3.avi')==sha(src/'FILE'/'movie'/'mved3.avi')
 mapping=json.loads((root/'build'/'gestalt'/'carrier-map.json').read_text(encoding='utf-8'));exe_cat=root/'build'/'gestalt'/'exe-ui-ko-gestalt.json';exe=validate_executable(release/'R11-Korean-Gestalt.exe',mapping,exe_cat);assert sha(release/'R11-Korean-Gestalt.exe')==manifest['executable_ui']['output_sha256']
 full=json.loads((root/'gestalt-analysis'/'gestalt-full-map.json').read_text(encoding='utf-8'));by={x['key']:x for x in full['strings']};assert len(by)==33768 and full['counts']['unresolved']==0
 smac=AfsArchive(src/'FILE'/'mac-en.afs');omac=AfsArchive(file/'mac-en.afs');assert smac.count==omac.count==171
 total=choices=black_choices=validated=relocated=fixed_ui_strings=fixed_ui_translated=0
 base_trans=load_base_translations(root)
 for e in smac.entries:
  sdec=decode_wrapped(smac.raw(e.index));odec=decode_wrapped(omac.raw(e.index));sobj=parse_gestalt(sdec,find_pointer_table);oobj=parse_gestalt(odec,find_pointer_table)
  if not sobj:
   fixed=parse_pool(sdec)
   if not fixed or fixed.get('mode')!='fixed':continue
   fixed_ui_strings+=len(fixed['items'])
   for item in fixed['items']:
    key=f'mac.afs::{e.index:04d}::{item["index"]:04d}';target=base_trans.get(key,item['text']);payload=encode_target(target,mapping)
    expected=payload+b' '*(len(item['raw'])-len(payload));actual=odec[item['offset']:item['end']]
    assert actual==expected,(e.index,item['index'])
    fixed_ui_translated+=payload!=item['raw']
   continue
  assert oobj is not None and len(sobj['items'])==len(oobj['items']);total+=len(sobj['items']);choices+=len(sobj['choice_indices'])
  oldnew={a['offset']:b['offset'] for a,b in zip(sobj['items'],oobj['items'])}
  for q in range(0,sobj['text_offset']-1,2):
   old=struct.unpack_from('<H',sdec,q)[0]
   if old in oldnew:assert struct.unpack_from('<H',odec,q)[0]==oldnew[old];relocated+=1
  for ci in sobj['choice_indices']:
   b=oobj['items'][ci];choice_raw=odec[b['offset']:b['end']];validated+=1;assert b'%' not in choice_raw;black_choices+=choice_raw.startswith(b'%C000F')
  if e.index<=154:
   for a,b in zip(sobj['items'],oobj['items']):
    row=by[f'gestalt.mac::{e.index:04d}::{a["index"]:04d}'];raw=odec[b['offset']:b['end']]
    if row.get('target_ko') is None:assert raw==a['raw']
    else:
     expected=encode_target(row['target_ko'],mapping)
     if a['index'] in sobj['choice_indices']:assert raw==expected
     else:assert raw==expected or raw==b'%C000F'+expected
 print({'choices':choices,'validated':validated,'black_choices':black_choices,'total':total});assert choices==336 and validated==336 and black_choices==0
 init_src=decode_wrapped((src/'FILE'/'init.rp').read_bytes());init_out=decode_wrapped((file/'init.rp').read_bytes());targets=load_init_targets(root/'gestalt-analysis','gestalt');kinds={}
 for site,row in targets.items():
  if row.get('pointer') is not None:assert struct.unpack_from('<I',init_src,site)[0]==int(row['pointer'])
  ptr=struct.unpack_from('<I',init_out,site)[0];expected=b'\x90'*row['padding_90']+encode_target(row['target_ko'],mapping);assert init_out[ptr:ptr+len(expected)]==expected and init_out[ptr+len(expected)]==0;kinds[row['kind']]=kinds.get(row['kind'],0)+1
 assert kinds=={'chronology':48,'tips':269},kinds
 etc=AfsArchive(file/'etc-en.afs');font=decode_wrapped(etc.raw(0));built=(root/'build'/'gestalt'/'FNT2626.FOP').read_bytes();assert font==built
 en=(root/'extracted'/'etc-en'/'decoded'/'0000__FNT2626.FOP').read_bytes();jp=(root/'extracted'/'etc-jp'/'decoded'/'0000__FNT2626.FOP').read_bytes();_,mo,_,go,gs,bs,*_=HEADER.unpack_from(en);protected=[]
 for i in range(gs//bs):
  a=go+i*bs;b=a+bs
  if en[a:b]!=jp[a:b] or en[mo+i*2:mo+i*2+2]!=jp[mo+i*2:mo+i*2+2]:protected.append(i);assert font[a:b]==en[a:b] and font[mo+i*2:mo+i*2+2]==en[mo+i*2:mo+i*2+2]
 assert protected==list(range(940,1128))
 zpath=root/'release'/'Remember11-Korean-Gestalt.zip'
 with zipfile.ZipFile(zpath)as z:assert z.testzip()is None;names=set(z.namelist());assert 'Remember11-Korean-Gestalt/R11-Korean-Gestalt.exe'in names and all(f'Remember11-Korean-Gestalt/FILE/{x}'in names for x in expected_files)
 result={'ok':True,'scenario_strings':total,'scenario_map':full['counts'],'validated_choices_without_controls':validated,'black_styled_choices':black_choices,'fixed_ui_strings':fixed_ui_strings,'fixed_ui_translated':fixed_ui_translated,'relocated_script_pointer_sites':relocated,'validated_init_pointer_sites':len(targets),'validated_init_by_kind':kinds,'carrier_glyphs':len(mapping),'protected_english_glyphs':len(protected),'executable_ui':exe,'zip':str(zpath),'zip_sha256':sha(zpath),'zip_size':zpath.stat().st_size}
 (root/'build'/'gestalt'/'release-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));return result

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--game',type=Path,required=True);a=ap.parse_args();validate(a.root,a.game)
