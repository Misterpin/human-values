from pathlib import Path
import csv,json,re,hashlib
ROOT=Path(__file__).resolve().parents[1]
if (ROOT/'config/study.json').exists():
 raise SystemExit('Конфиг уже существует. Сохраните его копию и уберите файл перед повторным импортом.')
rows=list(csv.DictReader((ROOT/'data/source/accepted_values.csv').open(encoding='utf-8-sig')))
def safe(s):return re.sub(r'[/\\:*?"<>|]', ' — ',s).strip().rstrip('.')
groups=[]; index={}
for r in rows:
 g=r['group_ru']
 if g not in index:
  index[g]={'id':f'g{len(groups)+1}','name':g,'folder':safe(g),'values':[]};groups.append(index[g])
 v={'id':r['value_id'],'name':r['value_ru'],'folder':safe(r['value_ru']),'definitions':[{'id':'dataset','label':'Определение из датасета','text':r['definition_ru'],'source':r['definition_source'],'origin':'dataset'}], 'formulations':[{'id':'canonical','label':'Название из датасета','text':r['value_ru']}], 'bws_option_sets':[]}
 index[g]['values'].append(v)
 (ROOT/'images'/safe(g)/safe(r['value_ru'])).mkdir(parents=True,exist_ok=True)
config={'schema_version':1,'title':'Human Values','subtitle':'Лаборатория визуальных ценностей','expected_groups':7,'expected_values':100,'image_root':'images','database':'data/responses.sqlite3','default_criterion':'association','criteria':{'association':{'label':'Ассоциация с ценностью','instruction':'Оцените, насколько изображение связано с указанной ценностью и её определением.'},'manifestation':{'label':'Проявление ценности','instruction':'Оцените, насколько изображение показывает проявление указанной ценности.'},'violation':{'label':'Нарушение ценности','instruction':'Оцените, насколько изображение показывает нарушение указанной ценности.'}},'contexts':[{'id':'unspecified','label':'Без заданного культурного контекста','text':''},{'id':'ru','label':'Современный российский контекст','text':'Рассматривайте изображение в контексте повседневной жизни в современной России.'}],'paradigms':{'rating':{'label':'Шкала 1–5','min_images':1,'instruction':'Насколько изображение соответствует заданному критерию? Выберите оценку от 1 до 5.'},'ranking':{'label':'Ранжирование пяти','min_images':5,'instruction':'Расположите пять изображений от наиболее до наименее подходящего. Перетаскивайте карточки или используйте стрелки.'},'pair':{'label':'Пара и ничья','min_images':2,'instruction':'Выберите изображение, которое лучше соответствует критерию, или отметьте ничью.'},'bws':{'label':'Лучшее / худшее','min_images':1,'instruction':'Для одного изображения выберите наиболее и наименее подходящие понятия с объяснениями из четырёх вариантов.'}},'groups':groups}
assert len(groups)==7 and sum(len(g['values']) for g in groups)==100
(ROOT/'config/study.json').write_text(json.dumps(config,ensure_ascii=False,indent=2))
print('Prepared 7 groups, 100 values, 100 definitions and image folders.')
