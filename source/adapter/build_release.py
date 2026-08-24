from __future__ import annotations
import argparse,hashlib,json,re,shutil,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from r11_tools import AfsArchive,decode_wrapped,encode_wrapped
from r11_script_pool import parse as parse_script,rebuild as rebuild_script,choice_string_indices
from r11_font import build_font,encode_target
from r11_exe_ui import load_catalog as load_exe_ui_catalog, target_texts as exe_ui_target_texts, patch_executable
from r11_init import load_targets as load_init_targets,target_texts as init_target_texts,rebuild as rebuild_init

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def translations(root):
 out={}
 for p in sorted(x for x in (root/'translations'/'script-pool').glob('packet-*.json') if not x.name.endswith('.ok.json')):
  for x in json.loads(p.read_text(encoding='utf-8'))['translations']:
   if x['key'] in out:raise ValueError('duplicate '+x['key'])
   out[x['key']]=x['target_ko']
 manual=root/'translations'/'manual-overrides.json'
 if manual.exists():
  for x in json.loads(manual.read_text(encoding='utf-8'))['translations']:
   if x['key'] in out:raise ValueError('manual override collides with packet translation '+x['key'])
   out[x['key']]=x['target_ko']
 return out
def complete_translation_count(root):
 expected=sum(json.loads(p.read_text(encoding='utf-8'))['count'] for p in (root/'packets'/'script-pool-200').glob('packet-*.json'))
 manual=root/'translations'/'manual-overrides.json'
 if manual.exists():expected+=json.loads(manual.read_text(encoding='utf-8'))['count']
 got=len(translations(root));return expected,got

def style_dialogue(text:str,entry:int,is_standard_dialogue:bool=True)->str:
 # Keep the PC original's default light text and dark edge treatment. Forcing
 # %C000F turns the body black while the renderer's edge pass remains dark,
 # merging both passes into the muddy double-weight text seen in Korean builds.
 return text

def build(root:Path,game:Path,allow_partial=False):
 expected,got=complete_translation_count(root)
 if got!=expected and not allow_partial:raise SystemExit(f'translations incomplete: {got}/{expected}')
 trans=translations(root);catalog=[json.loads(x) for x in (root/'catalog'/'script-pool-ja.jsonl').read_text(encoding='utf-8').splitlines()];rows={x['key']:x for x in catalog};targets=[]
 for r in catalog:
  targets.append(trans.get(r['key'],r['source_jp']))
 exe_catalog_path=root/'catalog'/'exe-ui-ko.json';exe_catalog=load_exe_ui_catalog(exe_catalog_path);targets.extend(exe_ui_target_texts(exe_catalog))
 init_data=root/'gestalt-analysis';targets.extend(init_target_texts(init_data,'base'))
 work=root/'build'/'final';work.mkdir(parents=True,exist_ok=True);font_out=work/'FNT2626.FOP';map_out=work/'carrier-map.json'
 font_stats=build_font(root/'extracted'/'etc-en'/'decoded'/'0000__FNT2626.FOP',root/'tools'/'R11-psp-english'/'text'/'charset-tables'/'r11-orig-font-table.txt',targets,Path(r'C:\Windows\Fonts\NotoSansKR-VF.ttf'),font_out,map_out,34,font_weight=500,reference_fop=root/'extracted'/'etc-jp'/'decoded'/'0000__FNT2626.FOP');mapping=json.loads(map_out.read_text(encoding='utf-8'))
 source_file=game/'FILE';archives=work/'archives'
 if archives.exists():shutil.rmtree(archives)
 archives.mkdir()
 # scripts
 mac=AfsArchive(source_file/'mac.afs');mac_repl={};script_stats=[]
 for e in mac.entries:
  dec_path=next((root/'extracted'/'mac-jp'/'decoded').glob(f'{e.index:04d}__*'));data=dec_path.read_bytes();obj=parse_script(data)
  if not obj:continue
  choice_indices=choice_string_indices(data,obj)
  encoded=[]
  for x in obj['items']:
   key=f'mac.afs::{e.index:04d}::{x["index"]:04d}';target=trans.get(key,x['text']);target=style_dialogue(target,e.index,bool(obj['refs'].get(x['index'])) and x['index'] not in choice_indices);encoded.append(encode_target(target,mapping))
  rebuilt=rebuild_script(data,encoded);mac_repl[e.index]=encode_wrapped(rebuilt);script_stats.append({'entry':e.index,'strings':len(encoded),'decoded_size':len(rebuilt)})
 mac_info=mac.rebuild(archives/'mac-en.afs',mac_repl)
 # ETC, with font and rebuilt UI BIPs
 etc=AfsArchive(source_file/'etc.afs');etc_repl={0:encode_wrapped(font_out.read_bytes())};ui_dec=root/'ui'/'rendered'/'etc-decoded'
 for q in ui_dec.glob('*'):
  idx=int(q.name.split('__')[0]);etc_repl[idx]=encode_wrapped(q.read_bytes())
 etc_info=etc.rebuild(archives/'etc-en.afs',etc_repl)
 # BG and EV are PNGFILE2 raw entries
 arc_infos={'mac':mac_info,'etc':etc_info}
 for kind in ('bg','ev'):
  arc=AfsArchive(source_file/f'{kind}.afs');repl={}
  for q in (root/'ui'/'rendered'/f'{kind}-raw').glob('*'):repl[int(q.name.split('__')[0])]=q.read_bytes()
  arc_infos[kind]=arc.rebuild(archives/f'{kind}-en.afs',repl)
 # Japanese audio baseline for the Korean English-slot carrier.
 shutil.copy2(source_file/'bgmpc.afs',archives/'bgmpc-en.afs')
 # init.rp owns the TIPS viewer and several system labels. Rebuild it
 # append-only so original tables remain intact.
 init_decoded=decode_wrapped((source_file/'init.rp').read_bytes());init_targets=load_init_targets(init_data,'base')
 init_rebuilt,init_stats=rebuild_init(init_decoded,init_targets,lambda v:encode_target(v,mapping))
 (archives/'init.rp').write_bytes(encode_wrapped(init_rebuilt))
 release=root/'release'/'Remember11-Korean';
 if release.exists():shutil.rmtree(release)
 (release/'FILE').mkdir(parents=True)
 for q in archives.glob('*-en.afs'):shutil.copy2(q,release/'FILE'/q.name)
 shutil.copy2(archives/'init.rp',release/'FILE'/'init.rp')
 exe_stats=patch_executable(game/'R11-English.exe',release/'R11-Korean.exe',mapping,exe_catalog_path)
 public_font={**font_stats,'font':Path(font_stats['font']).name}
 public_archives={}
 for kind,info in arc_infos.items():
  public_archives[kind]={k:v for k,v in info.items() if k!='output'}
  public_archives[kind]['file']=f'FILE\\{kind}-en.afs'
 manifest={'schema':'remember11.ko-release.v3','source_game':'Remember11 PC JP/EN baseline (bound by hashes below)','translation_source':'Japanese mac.afs, Japanese visual assets, and Japanese R11.exe UI strings, and Japanese PSP TIPS; English fallback only where the Japanese build itself stores an English presentation line','slot':'English technical carrier; Japanese slot preserved','translations':{'expected':expected,'built':got},'font':public_font,'archives':public_archives,'init_rp':init_stats,'runtime_repairs':['PNGFILE3 rebuilt item-offset table','PNGFILE2 rebuilt descriptor-offset table and container length','all aligned 16-bit physical-string pointers relocated, including bare choice pointers','one leading opaque-black %C000F control on normal Korean dialogue only; choice strings contain no color/control prefix','English transient/floating glyph bank 0x8640-0x86FC preserved (188 glyphs)','localized .rdata2 UI carrier pool with rebound pointers','rebuilt native PE MENU and DIALOG resources','append-only init.rp TIPS/system string relocation','raster UI source glyphs removed by bounded inpainting and recreated at original canvases and annotated positions'], 'executable_ui':exe_stats,'source_hashes':{str(p.relative_to(game)):sha(p) for p in [game/'R11-English.exe',source_file/'mac.afs',source_file/'etc.afs',source_file/'bg.afs',source_file/'ev.afs',source_file/'bgmpc.afs',source_file/'init.rp']},'outputs':{str(p.relative_to(release)):sha(p) for p in release.rglob('*') if p.is_file()}}
 (release/'patch-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 readme='''# Remember11 한국어 패치

- 대사와 UI는 일본어 원문과 일본어 이미지 자산을 의미 기준으로 사용했습니다.
- 일본어판 데이터 자체에 영어로 저장된 엔딩 표시문만 허용된 영어 fallback으로 번역했습니다.
- 기술적으로 기존 영어 슬롯(`*-en.afs`)을 한국어 슬롯으로 교체하며, `R11-Korean.exe`의 메뉴·설정·시스템 문구도 한국어화했습니다. 일본어 실행 파일과 일본어 슬롯은 그대로 유지됩니다.
- 선택지 렌더러는 색상 제어문자를 글자로 표시하므로, 선택지에는 색상 제어문자를 넣지 않았습니다.
- TIPS와 관련 시스템 문자열은 PSP 일본어 원문을 기준으로 `init.rp`를 새로 구성했습니다.
- 원본 게임 폴더에 이 패키지의 내용을 복사한 뒤 `R11-Korean.exe`를 실행하십시오.
- 기존 영어판 파일을 보존하려면 `R11-English.exe`, `FILE\*-en.afs`, `FILE\init.rp`를 먼저 별도 폴더에 백업하십시오.
'''
 (release/'README-KO.md').write_text(readme,encoding='utf-8')
 zip_path=root/'release'/'Remember11-Korean.zip'
 if zip_path.exists():zip_path.unlink()
 with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
  for q in release.rglob('*'):
   if q.is_file():z.write(q,q.relative_to(release.parent))
 (root/'build'/'final'/'build-summary.json').write_text(json.dumps({'release':str(release),'zip':str(zip_path),'manifest':manifest,'script_entries':script_stats},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'release':str(release),'zip':str(zip_path),'translations':got,'carriers':font_stats['hangul_carriers']},ensure_ascii=False))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--game',type=Path,required=True);ap.add_argument('--allow-partial',action='store_true');a=ap.parse_args();build(a.root,a.game,a.allow_partial)
if __name__=='__main__':main()
