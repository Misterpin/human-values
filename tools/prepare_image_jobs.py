from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
cfg=json.loads((root/'config/study.json').read_text()); scenes=(root/'tools/scenes.txt').read_text().splitlines();assert len(scenes)==100
variations=[
 'A candid medium-wide shot of the described scene. The action and relationships should be visible.',
 'Create a different plausible everyday situation conveying this same meaning. Use a different location and different adult characters, with a clear visible action.',
 'Create a distinct situation inspired by the scene, with a small group of adults cooperating or interacting if relevant to the value. Do not simply repeat the first composition.',
 'Create a distinct quiet close observational scene emphasizing a relevant gesture or practical action, with enough environmental context to infer its meaning.',
 'Create another plausible concrete situation expressing this value, with a different time of day and different composition. Choose a subtle ordinary moment rather than a theatrical pose.'
]
jobs=[]
for g in cfg['groups']:
 for v in g['values']:
  if int(v['id'][2:]) > 20: continue
  for n,variation in enumerate(variations,1):
   scene=scenes[int(v['id'][2:])-1]
   prompt=f'''Use case: photorealistic-natural. Generate exactly one landscape 3:2 realistic documentary photograph for a psychology research image collection. Target human value: {v['name']}. Expert definition (Russian, preserve the intended meaning, use one coherent visible situation rather than attempting to depict all clauses): {v['definitions'][0]['text']}
Visual scene seed: {scene}
This candidate's direction: {variation}
Natural plausible light, realistic textures and anatomy, ordinary contemporary surroundings. No readable text, titles, logos, watermarks, value labels, diagram, collage, advertising polish or unrelated symbolic props. Do not infer a person's moral traits from ethnicity, gender or appearance. For traditions and religious values, use a coherent respectful specific everyday context, not a mixture of stereotypes. Depict a candidate association with the value; do not present this as objectively validated. One photograph only. Candidate reference {v['id']}/{n:02d} (never write the reference in the image).'''
   jobs.append({'value_id':v['id'],'number':n,'group':g['name'],'value':v['name'],'definition_id':'dataset','definition':v['definitions'][0]['text'],'scene':scene,'variation':variation,'prompt':prompt,'output':str(Path('images')/g['folder']/v['folder']/f'{n:02d}.png'),'status':'candidate_not_validated','generator':'built-in image_gen'})
(root/'data/image_jobs.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2))
print(f'{len(jobs)} pilot image prompts prepared; no images generated.')
