"""Local-only Human Values image assessment. Python standard library, no API keys."""
from __future__ import annotations
import argparse, csv, hashlib, io, itertools, json, mimetypes, random, re, sqlite3, threading, time, uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote, quote

ROOT = Path(__file__).resolve().parent
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
RNG = random.SystemRandom()

def now(): return datetime.now(timezone.utc).isoformat()
def digest(data): return hashlib.sha256(data).hexdigest()
def compact(data): return json.dumps(data, ensure_ascii=False, separators=(',', ':'))

class Study:
    def __init__(self, config_path=None, db_path=None):
        self.config_path = Path(config_path or ROOT/'config/study.json').resolve()
        self.root = self.config_path.parent.parent
        self.db_override = db_path
        self.hash_cache = {}
        self.lock = threading.RLock()
        self.reload()
        with self.db() as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS trials (id TEXT PRIMARY KEY, participant TEXT NOT NULL, value_id TEXT NOT NULL, mode TEXT NOT NULL, signature TEXT NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS responses (id TEXT PRIMARY KEY, trial_id TEXT UNIQUE NOT NULL REFERENCES trials(id), answer TEXT NOT NULL, presentation TEXT NOT NULL, elapsed_ms INTEGER NOT NULL, submitted_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS trials_lookup ON trials(participant,value_id,mode,signature);
            ''')

    def reload(self):
        raw = self.config_path.read_bytes()
        version = digest(raw)
        if getattr(self, 'version', None) == version: return
        cfg = json.loads(raw)
        groups = cfg['groups']; values = {}
        if len(groups) != cfg.get('expected_groups',7): raise ValueError('В конфиге должно быть 7 групп.')
        for g in groups:
            self.check_folder(g['folder'])
            for value in g['values']:
                v = dict(value); self.check_folder(v['folder'])
                if not re.fullmatch(r'[A-Za-z0-9_-]+',v['id']) or v['id'] in values: raise ValueError('Неверный или повторяющийся ID ценности.')
                if not v.get('definitions') or any(not d.get('text','').strip() for d in v['definitions']): raise ValueError(f"Нет определения: {v['id']}")
                for key in ('definitions','formulations'):
                    if not v.get(key) or len({x['id'] for x in v[key]}) != len(v[key]): raise ValueError(f'Проверьте {key} у {v["id"]}')
                v['group_id'],v['group_name'],v['group_folder'] = g['id'],g['name'],g['folder']
                values[v['id']] = v
        if len(values) != cfg.get('expected_values',100): raise ValueError('В конфиге должно быть 100 ценностей.')
        image_root = (self.root/cfg.get('image_root','images')).resolve()
        if not image_root.is_relative_to(self.root): raise ValueError('Папка images должна находиться внутри проекта.')
        self.cfg,self.values,self.version,self.image_root = cfg,values,version,image_root
        self.db_path = Path(self.db_override or self.root/cfg.get('database','data/responses.sqlite3'))
        self.db_path.parent.mkdir(parents=True,exist_ok=True)
        for v in values.values(): self.folder(v).mkdir(parents=True,exist_ok=True)

    @staticmethod
    def check_folder(name):
        if not name or name in ('.','..') or '/' in name or '\\' in name: raise ValueError('Недопустимое имя папки в конфиге.')

    def db(self):
        con=sqlite3.connect(self.db_path,timeout=15);con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON');return con

    def folder(self,v): return self.image_root/v['group_folder']/v['folder']

    def images(self,v,hashes=False):
        result=[]
        for p in sorted(self.folder(v).iterdir()):
            if not p.is_file() or p.suffix.lower() not in EXTENSIONS or not p.resolve().is_relative_to(self.image_root): continue
            stat=p.stat(); key=(str(p),stat.st_mtime_ns,stat.st_size)
            h=self.hash_cache.get(key)
            if hashes and h is None: h=digest(p.read_bytes());self.hash_cache[key]=h
            image={'id':p.name,'url':f'/media/{v["id"]}/{quote(p.name)}?v={stat.st_mtime_ns}','bytes':stat.st_size}
            if hashes: image['sha256']=h
            result.append(image)
        return result

    def catalog(self,participant=''):
        with self.lock:
            self.reload();cfg=json.loads(compact(self.cfg))
            counts={}
            with self.db() as con:
                for row in con.execute('SELECT t.value_id,COUNT(*) n FROM responses r JOIN trials t ON t.id=r.trial_id WHERE t.participant=? GROUP BY t.value_id',(participant,)): counts[row['value_id']]=row['n']
            total=0;ready=0
            for g in cfg['groups']:
                for v in g['values']:
                    ims=self.images(self.values[v['id']]);v['image_count']=len(ims);v['response_count']=counts.get(v['id'],0);total+=len(ims);ready+=len(ims)>=5
            cfg.update({'version':self.version,'image_count':total,'ready_values':ready})
            return cfg

    def make_trial(self,data):
        with self.lock:
            self.reload()
            participant=data.get('participant','').strip()
            if not re.fullmatch(r'[\w-]{1,64}',participant): raise ValueError('ID участника: 1–64 буквы, цифры, дефис или подчёркивание.')
            v=self.values.get(data.get('value_id')); mode=data.get('mode')
            if not v or mode not in self.cfg['paradigms']: raise ValueError('Неизвестная ценность или режим.')
            definition=next((d for d in v['definitions'] if d['id']==data.get('definition_id')),None)
            formulation=next((f for f in v['formulations'] if f['id']==data.get('formulation_id')),None)
            criterion=self.cfg['criteria'].get(data.get('criterion'))
            context=next((c for c in self.cfg['contexts'] if c['id']==data.get('context_id')),None)
            if not all((definition,formulation,criterion,context)): raise ValueError('Проверьте определение, формулировку и контекст.')
            images=self.images(v,True);minimum=self.cfg['paradigms'][mode]['min_images']
            if len(images)<minimum: raise ValueError(f'Для этого режима нужно {minimum} изображений; сейчас {len(images)}.')
            signature=digest(compact([self.version,definition,formulation,data['criterion'],context,[(x['id'],x['sha256']) for x in images]]).encode())
            with self.db() as con:
                used=[json.loads(row['snapshot']) for row in con.execute('SELECT t.snapshot FROM trials t JOIN responses r ON r.trial_id=t.id WHERE t.participant=? AND t.value_id=? AND t.mode=? AND t.signature=?',(participant,v['id'],mode,signature))]
            if mode in ('rating','bws'):
                seen={s['images'][0]['id'] for s in used};candidates=[x for x in images if x['id'] not in seen]
                chosen=[RNG.choice(candidates or images)];cycle_complete=not candidates
            elif mode=='pair':
                pairs=list(itertools.combinations(images,2));seen={tuple(sorted(i['id'] for i in s['images'])) for s in used}
                candidates=[p for p in pairs if tuple(sorted(i['id'] for i in p)) not in seen]
                chosen=list(RNG.choice(candidates or pairs));RNG.shuffle(chosen);cycle_complete=not candidates
            else:
                chosen=RNG.sample(images,5);cycle_complete=bool(used)
            trial={'id':uuid.uuid4().hex,'participant':participant,'value_id':v['id'],'value_name':v['name'],'group':v['group_name'],'mode':mode,'definition':definition,'formulation':formulation,'criterion_id':data['criterion'],'criterion':criterion,'context':context,'images':chosen,'options':[],'config_version':self.version,'instruction':self.cfg['paradigms'][mode]['instruction'],'created_at':now(),'cycle_complete':cycle_complete,'presentation':data.get('presentation','researcher')}
            if mode=='bws':
                sets=[s for s in v.get('bws_option_sets',[]) if s.get('image') in (None,chosen[0]['id'])]
                if sets:
                    options=json.loads(compact(RNG.choice(sets)['options']));source='configured'
                    if len(options)!=4 or len({x['id'] for x in options})!=4 or any(not x.get('concept') or not x.get('explanation') for x in options): raise ValueError('В bws_option_sets нужны четыре разных варианта с concept и explanation.')
                else:
                    others=[x for x in self.values.values() if x['id']!=v['id']]
                    candidates=[v]+RNG.sample(others,3)
                    options=[{'id':x['id'],'concept':x['name'],'explanation':(definition['text'] if x['id']==v['id'] else x['definitions'][0]['text'])} for x in candidates];source='dataset_definitions'
                RNG.shuffle(options);trial['options']=options;trial['options_source']=source
            with self.db() as con: con.execute('INSERT INTO trials VALUES(?,?,?,?,?,?,?)',(trial['id'],participant,v['id'],mode,signature,compact(trial),trial['created_at']))
            return trial

    def answer(self,data):
        with self.db() as con:
            row=con.execute('SELECT * FROM trials WHERE id=?',(data.get('trial_id'),)).fetchone()
            if row is None: raise ValueError('Задание не найдено. Получите новое.')
            t=json.loads(row['snapshot']);a=data.get('answer');ids=[x['id'] for x in t['images']];mode=t['mode']
            if data.get('participant')!=t['participant']: raise ValueError('Задание создано для другого участника.')
            valid=False
            if mode=='rating': valid=type(a)==int and 1<=a<=5
            if mode=='pair': valid=isinstance(a,str) and a in ids+['tie']
            if mode=='ranking': valid=isinstance(a,list) and len(a)==5 and all(isinstance(x,str) for x in a) and set(a)==set(ids)
            if mode=='bws':
                opts={x['id'] for x in t['options']};valid=isinstance(a,dict) and a.get('best') in opts and a.get('worst') in opts and a['best']!=a['worst']
            if not valid: raise ValueError('Ответ неполный или не соответствует заданию.')
            elapsed=data.get('elapsed_ms',0)
            if type(elapsed)!=int or not 0<=elapsed<=86400000: raise ValueError('Некорректное время ответа.')
            presentation=data.get('presentation','researcher')
            if presentation not in ('researcher','participant'): raise ValueError('Неизвестный способ предъявления.')
            existing=con.execute('SELECT id,answer FROM responses WHERE trial_id=?',(t['id'],)).fetchone()
            if existing:
                if json.loads(existing['answer'])!=a: raise ValueError('Для этого задания уже сохранён другой ответ.')
                return {'id':existing['id'],'already_saved':True}
            rid=uuid.uuid4().hex
            con.execute('INSERT INTO responses VALUES(?,?,?,?,?,?)',(rid,t['id'],compact(a),presentation,elapsed,now()))
            return {'id':rid,'already_saved':False}

    def export(self,participant=''):
        with self.db() as con:
            sql='SELECT t.snapshot,r.id response_id,r.answer,r.presentation,r.elapsed_ms,r.submitted_at FROM responses r JOIN trials t ON r.trial_id=t.id'
            rows=con.execute(sql+(' WHERE t.participant=?' if participant else '')+' ORDER BY r.submitted_at',(participant,) if participant else ()).fetchall()
        return [dict(json.loads(r['snapshot']),response_id=r['response_id'],answer=json.loads(r['answer']),answer_presentation=r['presentation'],elapsed_ms=r['elapsed_ms'],submitted_at=r['submitted_at']) for r in rows]

class Handler(BaseHTTPRequestHandler):
    server_version='HumanValuesLab/1'
    def log_message(self,format,*args):
        if args and ('/media/' in str(args[0]) or '/api/catalog' in str(args[0])):return
        super().log_message(format,*args)
    def send(self,status,body,ctype='application/json; charset=utf-8',extra=None):
        if isinstance(body,(dict,list)):body=compact(body).encode()
        if isinstance(body,str):body=body.encode()
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        try:
            url=urlparse(self.path);path=unquote(url.path);qs=parse_qs(url.query);s=self.server.study
            if path=='/api/catalog':return self.send(200,s.catalog(qs.get('participant',[''])[0]))
            if path=='/api/export':
                rows=s.export(qs.get('participant',[''])[0]);fmt=qs.get('format',['json'])[0]
                if fmt=='json':return self.send(200,rows,extra={'Content-Disposition':'attachment; filename="human-values-responses.json"'})
                buf=io.StringIO();fields=['response_id','participant','value_id','value_name','group','mode','definition_id','definition_text','formulation','criterion','context','images_in_order','image_hashes','options_in_order','answer','presentation','elapsed_ms','created_at','submitted_at','config_version']
                w=csv.DictWriter(buf,fieldnames=fields);w.writeheader()
                for r in rows:w.writerow({'response_id':r['response_id'],'participant':r['participant'],'value_id':r['value_id'],'value_name':r['value_name'],'group':r['group'],'mode':r['mode'],'definition_id':r['definition']['id'],'definition_text':r['definition']['text'],'formulation':r['formulation']['text'],'criterion':r['criterion_id'],'context':r['context']['text'],'images_in_order':compact([i['id'] for i in r['images']]),'image_hashes':compact([i['sha256'] for i in r['images']]),'options_in_order':compact(r['options']),'answer':compact(r['answer']),'presentation':r['answer_presentation'],'elapsed_ms':r['elapsed_ms'],'created_at':r['created_at'],'submitted_at':r['submitted_at'],'config_version':r['config_version']})
                return self.send(200,'\ufeff'+buf.getvalue(),'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename="human-values-responses.csv"'})
            if path.startswith('/media/'):
                parts=path.split('/')
                if len(parts)!=4 or parts[2] not in s.values: return self.send(404,{'error':'Изображение не найдено.'})
                p=s.folder(s.values[parts[2]])/parts[3]
                if p.suffix.lower() not in EXTENSIONS or not p.resolve().is_relative_to(s.image_root) or not p.is_file():return self.send(404,{'error':'Изображение не найдено.'})
                return self.send(200,p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'image/png')
            static={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/favicon.svg':'favicon.svg'}
            if path in static:
                p=ROOT/'static'/static[path];return self.send(200,p.read_bytes(),mimetypes.guess_type(p.name)[0]+'; charset=utf-8')
            self.send(404,{'error':'Страница не найдена.'})
        except (ValueError,KeyError,TypeError) as e:self.send(400,{'error':str(e)})
        except Exception as e:print('Server error:',repr(e));self.send(500,{'error':'Не удалось прочитать данные. Проверьте конфиг и журнал сервера.'})
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            if origin and urlparse(origin).netloc!=self.headers.get('Host'):return self.send(403,{'error':'Другой источник запроса запрещён.'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(415,{'error':'Ожидается JSON.'})
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=65536:return self.send(413,{'error':'Неверный размер запроса.'})
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):raise ValueError('Ожидается объект JSON.')
            path=urlparse(self.path).path
            if path=='/api/trial':return self.send(200,self.server.study.make_trial(data))
            if path=='/api/response':return self.send(200,self.server.study.answer(data))
            self.send(404,{'error':'Неизвестная операция.'})
        except (ValueError,KeyError,TypeError) as e:self.send(400,{'error':str(e)})
        except Exception as e:print('Server error:',repr(e));self.send(500,{'error':'Ответ не сохранён. Проверьте журнал сервера и повторите отправку.'})

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--config',type=Path);args=p.parse_args()
    study=Study(args.config);server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.study=study
    print(f'Human Values · 7 групп · 100 ценностей\nLocal: http://127.0.0.1:{args.port}\nConfig: {study.config_path}\nCtrl+C — остановить сервер',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
