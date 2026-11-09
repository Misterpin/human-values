from pathlib import Path
import sys,json,shutil,datetime,hashlib
source,destination,payload=sys.argv[1:]
src=Path(source);root=Path(__file__).resolve().parents[1];dst=root/Path(destination)
if not dst.resolve().is_relative_to((root/'images').resolve()):raise ValueError('Destination outside images')
dst.parent.mkdir(parents=True,exist_ok=True)
if not dst.exists():shutil.copy2(src,dst)
meta=json.loads(payload);meta.update({'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(dst.read_bytes()).hexdigest()})
dst.with_suffix('.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
print('saved',meta['value_id'],meta['number'])
