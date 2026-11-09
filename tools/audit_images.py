"""Inspect saved originals and record their actual generation prompts."""
import hashlib
import json
from pathlib import Path
# Optional audit utility: uv run --with pillow python tools/audit_images.py
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
jobs = json.loads((ROOT/'data/image_jobs.json').read_text())
jobs = [j for j in jobs if int(j['value_id'][2:]) <= 20]
first = ROOT/'images/Витальные/Жизнь/01.png'
if not first.with_suffix('.json').exists():
    meta = dict(next(j for j in jobs if j['value_id']=='HV001' and j['number']==1))
    meta['prompt'] = "Create one photorealistic natural documentary photograph for a psychology research stimulus collection, landscape 3:2. Human value: Жизнь (Life). Meaning: a person's unique inner experience of being alive, life as an essential condition of human relationships. Visual scene: an adult woman in ordinary everyday clothes crouches beside her elderly father in a modest home garden, both attentively examining a newly sprouted plant, quiet candid expressions and palpable vitality. Natural daylight, lifelike texture, ordinary contemporary setting, neither advertising nor idealized glamour. One coherent photo, no collage, no writing, captions, logos, watermarks, flags, icons or value labels. Express meaning through the action and relationships, not textual clues. This is candidate HV001/01 for human evaluation, not a validated depiction."
    meta['definition_in_prompt'] = 'English summary of the supplied definition; see prompt.'
    meta['sha256'] = hashlib.sha256(first.read_bytes()).hexdigest()
    meta['generated_at'] = None
    meta['metadata_note'] = 'First pilot image; original generation time was not recorded.'
    first.with_suffix('.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))

manifest=[]
qa=ROOT/'data/qa';qa.mkdir(exist_ok=True)
for j in jobs:
    p=ROOT/j['output']
    with Image.open(p) as im:
        im.verify()
    meta=json.loads(p.with_suffix('.json').read_text())
    assert meta['sha256']==hashlib.sha256(p.read_bytes()).hexdigest(),p
    meta['output']=str(p.relative_to(ROOT))
    with Image.open(p) as im: meta['size']=list(im.size)
    manifest.append(meta)
assert len(manifest)==100 and len({m['sha256'] for m in manifest})==100
(ROOT/'data/image_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(ROOT/'data/image_jobs.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2))
# Diagnostic contact sheets only; original research images are never modified.
for page in range(4):
    sheet=Image.new('RGB',(1250,950),'white');draw=ImageDraw.Draw(sheet)
    for i,m in enumerate(manifest[page*25:(page+1)*25]):
        x=(i%5)*250;y=(i//5)*190
        with Image.open(ROOT/m['output']) as im:
            thumb=im.convert('RGB');thumb.thumbnail((246,164));sheet.paste(thumb,(x,y+20))
        draw.text((x+4,y+3),f"{m['value_id']} / {m['number']}",fill='black')
    sheet.save(qa/f'contact-{page+1}.jpg',quality=90)
print('100 readable, distinct images; 20 complete values; metadata verified.')
