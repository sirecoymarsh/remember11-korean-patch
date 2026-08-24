from __future__ import annotations
import argparse,collections,hashlib,json,re,shutil,struct,sys,zipfile
from pathlib import Path

HERE=Path(__file__).parent
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def tree_sha(paths,base):
 h=hashlib.sha256();base=Path(base)
 for p in sorted((Path(x) for x in paths),key=lambda x:x.as_posix()):
  h.update(p.relative_to(base).as_posix().encode('utf-8')+b'\0')
  h.update(bytes.fromhex(sha(p)))
 return h.hexdigest()

def build(root:Path,game:Path):
 root=root.resolve();game=game.resolve();sys.path.insert(0,str(root/'adapter'))
 from r11_tools import AfsArchive,decode_wrapped,encode_wrapped
 from r11_script_pool import find_pointer_table,parse as parse_pool,rebuild as rebuild_pool
 from r11_gestalt_script import parse as parse_gestalt,rebuild as rebuild_gestalt
 from r11_font import build_font,encode_target
 from r11_exe_ui import load_catalog,target_texts as exe_target_texts,patch_executable
 from r11_init import load_targets as load_init_targets,target_texts as init_target_texts,rebuild as rebuild_init
 from build_release import translations as load_base_translations,style_dialogue

 data=root/'gestalt-analysis';src=data/'extracted'/'R11-Gestalt-v1.3.0'/'v1.3.0';src_file=src/'FILE';game_file=game/'FILE'
 full=json.loads((data/'gestalt-full-map.json').read_text(encoding='utf-8'));assert full['counts']['unresolved']==0 and len(full['strings'])==33768
 by_entry=collections.defaultdict(list)
 for row in full['strings']:by_entry[int(row['entry'])].append(row)
 for rows in by_entry.values():rows.sort(key=lambda x:int(x['string_index']))
 base_trans=load_base_translations(root)

 exe_source=src/'R11-English-Gestalt.exe';base_exe_catalog=json.loads((root/'catalog'/'exe-ui-ko.json').read_text(encoding='utf-8'))
 base_exe_catalog['source_hashes']['R11-English.exe']=sha(exe_source)
 work=root/'build'/'gestalt';work.mkdir(parents=True,exist_ok=True);exe_catalog_path=work/'exe-ui-ko-gestalt.json';exe_catalog_path.write_text(json.dumps(base_exe_catalog,ensure_ascii=False,indent=2),encoding='utf-8')
 exe_catalog=load_catalog(exe_catalog_path)

 targets=[x['target_ko'] for x in full['strings'] if x.get('target_ko') is not None]
 targets += list(base_trans.values())+exe_target_texts(exe_catalog)+init_target_texts(data,'gestalt')
 font_out=work/'FNT2626.FOP';map_out=work/'carrier-map.json'
 font_stats=build_font(root/'extracted'/'etc-en'/'decoded'/'0000__FNT2626.FOP',root/'tools'/'R11-psp-english'/'text'/'charset-tables'/'r11-orig-font-table.txt',targets,Path(r'C:\Windows\Fonts\NotoSansKR-VF.ttf'),font_out,map_out,34,font_weight=500,reference_fop=root/'extracted'/'etc-jp'/'decoded'/'0000__FNT2626.FOP')
 mapping=json.loads(map_out.read_text(encoding='utf-8'))

 archives=work/'archives'
 if archives.exists():shutil.rmtree(archives)
 archives.mkdir()
 mac=AfsArchive(src_file/'mac-en.afs');mac_repl={};script_stats=[];total_choices=0;total_strings=0
 for e in mac.entries:
  decoded=decode_wrapped(mac.raw(e.index));obj=parse_gestalt(decoded,find_pointer_table)
  if obj:
   encoded=[];rows=by_entry.get(e.index,[])
   if e.index<=154:
    if len(rows)!=len(obj['items']):raise ValueError(f'Gestalt map count mismatch entry {e.index}: {len(rows)} != {len(obj["items"])}')
    for item,row in zip(obj['items'],rows):
     if int(row['string_index'])!=item['index'] or bytes.fromhex(row['source_raw_hex'])!=item['raw']:raise ValueError(f'Gestalt source mismatch {e.index}:{item["index"]}')
     if row.get('target_ko') is None:payload=item['raw']
     else:
      target=style_dialogue(row['target_ko'],e.index,bool(obj['refs'].get(item['index'])) and item['index'] not in obj['choice_indices'])
      payload=encode_target(target,mapping)
     encoded.append(payload)
   else:
    for item in obj['items']:
     key=f'mac.afs::{e.index:04d}::{item["index"]:04d}';target=base_trans.get(key)
     if target is None:encoded.append(item['raw'])
     else:encoded.append(encode_target(style_dialogue(target,e.index,bool(obj['refs'].get(item['index'])) and item['index'] not in obj['choice_indices']),mapping))
   rebuilt=rebuild_gestalt(decoded,obj,encoded);choices=len(obj['choice_indices'])
  else:
   # Gestalt keeps the retail fixed-slot UI tables byte-for-byte compatible.
   # They are not pointer-pool scripts, so the Gestalt parser deliberately
   # returns None; use the retail parser/rebuilder instead of silently skipping
   # thousands of system, album, sound, and scene-list labels.
   obj=parse_pool(decoded)
   if not obj:continue
   encoded=[]
   for item in obj['items']:
    key=f'mac.afs::{e.index:04d}::{item["index"]:04d}';target=base_trans.get(key,item['text'])
    encoded.append(encode_target(target,mapping))
   rebuilt=rebuild_pool(decoded,encoded);choices=0
  mac_repl[e.index]=encode_wrapped(rebuilt);total_choices+=choices;total_strings+=len(obj['items'])
  script_stats.append({'entry':e.index,'mode':obj.get('mode','gestalt'),'strings':len(obj['items']),'choices':choices,'decoded_size':len(rebuilt)})
 mac_info=mac.rebuild(archives/'mac-en.afs',mac_repl)

 etc=AfsArchive(game_file/'etc.afs');etc_repl={0:encode_wrapped(font_out.read_bytes())}
 for q in (root/'ui'/'rendered'/'etc-decoded').glob('*'):etc_repl[int(q.name.split('__')[0])]=encode_wrapped(q.read_bytes())
 etc_info=etc.rebuild(archives/'etc-en.afs',etc_repl)
 bg=AfsArchive(src_file/'bg-en.afs');bg_repl={}
 for q in (root/'ui'/'rendered'/'bg-raw').glob('*'):bg_repl[int(q.name.split('__')[0])]=q.read_bytes()
 bg_info=bg.rebuild(archives/'bg-en.afs',bg_repl)
 ev=AfsArchive(game_file/'ev.afs');ev_repl={}
 for q in (root/'ui'/'rendered'/'ev-raw').glob('*'):ev_repl[int(q.name.split('__')[0])]=q.read_bytes()
 ev_info=ev.rebuild(archives/'ev-en.afs',ev_repl)
 shutil.copy2(src_file/'bgmpc-en.afs',archives/'bgmpc-en.afs');shutil.copy2(src_file/'bgmpc.afs',archives/'bgmpc.afs')

 init_dec=decode_wrapped((src_file/'init.rp').read_bytes());init_targets=load_init_targets(data,'gestalt')
 init_new,init_stats=rebuild_init(init_dec,init_targets,lambda v:encode_target(v,mapping));(archives/'init.rp').write_bytes(encode_wrapped(init_new))

 release=root/'release'/'Remember11-Korean-Gestalt'
 if release.exists():shutil.rmtree(release)
 (release/'FILE'/'movie').mkdir(parents=True)
 for q in archives.glob('*'):shutil.copy2(q,release/'FILE'/q.name)
 shutil.copy2(src_file/'movie'/'mved3.avi',release/'FILE'/'movie'/'mved3.avi')
 exe_stats=patch_executable(exe_source,release/'R11-Korean-Gestalt.exe',mapping,exe_catalog_path)

 infos={'mac':mac_info,'etc':etc_info,'bg':bg_info,'ev':ev_info}
 public={k:{**{a:b for a,b in v.items() if a!='output'},'file':f'FILE\\{k}-en.afs'}for k,v in infos.items()}
 translation_inputs={
  'gestalt_full_map_sha256':sha(data/'gestalt-full-map.json'),
  'script_pool_tree_sha256':tree_sha((root/'translations'/'script-pool').glob('packet-*.json'),root),
  'manual_overrides_sha256':sha(root/'translations'/'manual-overrides.json'),
  'executable_ui_catalog_sha256':sha(root/'catalog'/'exe-ui-ko.json'),
  'tips_sha256':sha(data/'tips-ko.json'),
  'chronology_sha256':sha(data/'chronology-ko-pages.json'),
  'ui_rendered_tree_sha256':tree_sha((p for p in (root/'ui'/'rendered').rglob('*') if p.is_file()),root),
 }
 manifest={
  'schema':'remember11.ko-gestalt-release.v1',
  'mode':'Gestalt 1.3.0 additional-content build',
  'translator_model':'Codex internal',
  'provenance':{
   'agent_model_family':'Codex / GPT-5.5',
   'codex_task_slug':'f-down-remember11-the-age-of',
   'translation_method':'Japanese-context semantic translation written by Codex internal; no external translation model or API used.',
   'translation_inputs':translation_inputs,
  },
  'translation_source':'Japanese PC scenario and Japanese PSP TIPS/chronology; English used only as the Gestalt technical carrier and as a structural boundary where the additional patch has no Japanese script payload',
  'scenario':full['counts'],
  'tips':{'tips':110,'japanese_pages':273,'pc_pages':269},
  'chronology_pages':48,
  'init_rp':init_stats,
  'font':{**font_stats,'font':Path(font_stats['font']).name},
  'script':{'entries':len(script_stats),'strings':total_strings,'choices':total_choices},
  'archives':public,
  'executable_ui':exe_stats,
  'source_hashes':{str(p.relative_to(src)):sha(p) for p in [exe_source,src_file/'mac-en.afs',src_file/'bg-en.afs',src_file/'bgmpc-en.afs',src_file/'bgmpc.afs',src_file/'init.rp',src_file/'movie'/'mved3.avi']},
  'outputs':{},
 }
 readme='''# Remember11 한국어 패치 — 게슈탈트 모드

- 게슈탈트 1.3.0의 추가 콘텐츠를 포함하는 별도 실행판입니다.
- 본편 의미는 일본어 PC 원문, 추가 TIPS·인물 정보·연표는 PSP 일본어 원문만을 번역 기준으로 삼았습니다.
- 게슈탈트 패치가 영어로만 제공하는 기술적 배열과 페이지 경계는 구조 확인에만 사용했습니다.
- 대사·선택지·TIPS·연표·메뉴·설정·시스템 UI와 이미지 UI를 한국어화했습니다.
- 선택지에는 색상 제어문자를 넣지 않아 `%000F` 같은 코드가 화면에 나타나지 않습니다.
- 대사는 PC 원판과 동일하게 밝은 글자와 어두운 외곽선을 사용하며, 강제 검정색 제어코드를 넣지 않습니다.
- 한글 글꼴은 Noto Sans KR 500을 원본 34px 전각·행간·배치에 맞춰 사용합니다.
- 이미지 UI는 원문 글자를 제거한 뒤 원래 캔버스·비율·위치 안에서 새로 만들었습니다.

## 설치
1. 원본 게임의 `R11-English.exe`, `FILE\\*-en.afs`, `FILE\\init.rp`, `FILE\\movie`를 별도 폴더에 백업합니다.
2. 이 폴더의 내용을 원본 게임 폴더에 복사합니다.
3. `R11-Korean-Gestalt.exe`를 실행합니다.

## 복원
백업한 파일을 원래 위치로 되돌리고 `R11-Korean-Gestalt.exe`를 삭제합니다. 일본어 실행 파일과 일본어 슬롯은 수정하지 않습니다.
'''
 (release/'README-KO.md').write_text(readme,encoding='utf-8')
 manifest['outputs']={str(p.relative_to(release)):sha(p) for p in release.rglob('*') if p.is_file()}
 (release/'patch-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 zip_path=root/'release'/'Remember11-Korean-Gestalt.zip'
 if zip_path.exists():zip_path.unlink()
 with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
  for q in release.rglob('*'):
   if q.is_file():z.write(q,q.relative_to(release.parent))
 zip_hash=sha(zip_path)
 (root/'release'/'Remember11-Korean-Gestalt.zip.sha256').write_text(f'{zip_hash}  {zip_path.name}\n',encoding='ascii')
 summary={'release':str(release),'zip':str(zip_path),'zip_sha256':zip_hash,'font':font_stats,'scenario':full['counts'],'init_rp':init_stats,'script_entries':script_stats}
 (work/'build-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'release':str(release),'zip':str(zip_path),'zip_sha256':summary['zip_sha256'],'strings':total_strings,'choices':total_choices,'carriers':font_stats['hangul_carriers'],'init_sites':init_stats['modified_pointer_sites']},ensure_ascii=False))

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--game',type=Path,required=True);a=ap.parse_args();build(a.root,a.game)
