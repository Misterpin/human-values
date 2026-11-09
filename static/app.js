const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const freshParticipant = () => 'P-' + crypto.randomUUID().slice(0, 8);
let participant = localStorage.getItem('hv-participant') || freshParticipant();
localStorage.setItem('hv-participant', participant);
let cfg, values = [], current, trial, answer = null, order = [], mode = 'rating', epoch = 0, started = 0, saving = false, participantView = false, confirmed = false;
const openGroups = new Set();
function toast(text, error = false) { $('toast').textContent = text; $('toast').classList.toggle('error', error); $('toast').hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => $('toast').hidden = true, error ? 7000 : 2800); }
async function api(path, data) { const r = await fetch(path, data ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)} : {}); const body = await r.json(); if (!r.ok) throw new Error(body.error || 'Ошибка сервера'); return body; }
function fillSelect(id, list, selected) { $(id).innerHTML = list.map(x => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join(''); if (list.some(x => x.id === selected)) $(id).value = selected; }
async function loadCatalog(initial = false) {
  cfg = await api('/api/catalog?participant=' + encodeURIComponent(participant));
  values = cfg.groups.flatMap(g => g.values.map(v => ({...v, group:g})));
  $('image-total').innerHTML = `${cfg.image_count}<span> изображений в коллекции</span>`;
  $('ready-total').textContent = `${cfg.ready_values} из 100 ценностей имеют пять изображений`;
  $('collection-progress').style.width = Math.min(100, cfg.ready_values) + '%';
  $('participant-id').value = participant; $('participant-footer').textContent = 'Участник ' + participant;
  fillSelect('criterion-select', Object.entries(cfg.criteria).map(([id,c]) => ({id,label:c.label})), $('criterion-select').value || cfg.default_criterion);
  fillSelect('context-select', cfg.contexts, $('context-select').value);
  if (initial) {
    const stored = new URLSearchParams(location.hash.slice(1)).get('value') || localStorage.getItem('hv-value');
    current = values.find(v => v.id === stored) || values[0];
    openGroups.add(current.group.id); renderNav(); selectValue(current.id);
  } else {
    current = values.find(v => v.id === current.id);
    fillSelect('definition-select', current.definitions, $('definition-select').value);
    fillSelect('formulation-select', current.formulations, $('formulation-select').value);
    $('definition-label').hidden = current.definitions.length < 2;
    $('formulation-label').hidden = current.formulations.length < 2;
    showDefinition(); showFormulation(); renderNav();
    $('photo-count').textContent = current.image_count + ' изображений';
  }
}
function renderNav() {
  const query = $('search').value.trim().toLocaleLowerCase('ru'); let found = 0;
  $('groups').innerHTML = cfg.groups.map(g => {
    const shown = g.values.filter(v => !query || (v.name + ' ' + v.id + ' ' + g.name).toLocaleLowerCase('ru').includes(query));
    if (!shown.length) return ''; found += shown.length;
    return `<details class="group" data-group="${g.id}" ${query || openGroups.has(g.id) ? 'open' : ''}><summary><span class="chevron">⌄</span><span class="group-name">${esc(g.name)}</span><span class="group-count">${g.values.length}</span></summary><div class="values">${shown.map(v => `<button class="value-nav ${current?.id === v.id ? 'active' : ''}" data-value="${v.id}" title="${esc(v.name)} · ${v.image_count} изображений"><span class="label">${esc(v.name)}</span><span class="dot ${v.image_count >= 5 ? 'ready' : v.image_count ? 'partial' : ''}"></span></button>`).join('')}</div></details>`;
  }).join('') || '<p class="no-results">Ценности не найдены</p>';
  $('nav-count').textContent = found;
  $('groups').querySelectorAll('details').forEach(el => el.addEventListener('toggle', () => el.open ? openGroups.add(el.dataset.group) : openGroups.delete(el.dataset.group)));
  $('groups').querySelectorAll('[data-value]').forEach(el => el.onclick = () => selectValue(el.dataset.value));
}
function showDefinition() {
  const d = current.definitions.find(x => x.id === $('definition-select').value);
  $('definition-text').textContent = d?.text || '';
  $('definition-source').textContent = d?.source || 'Источник не указан в конфиге';
}
function showFormulation() {
  $('value-name').textContent = current.formulations.find(x => x.id === $('formulation-select').value)?.text || current.name;
}
function selectValue(id) {
  if (saving) return;
  current = values.find(v => v.id === id); localStorage.setItem('hv-value', id); history.replaceState(null, '', '#value=' + id);
  $('value-name').textContent = current.name; $('value-id').textContent = id; $('value-category').textContent = current.group.name; $('crumb-group').textContent = current.group.name;
  $('photo-count').textContent = current.image_count + ' изображений';
  fillSelect('definition-select', current.definitions); fillSelect('formulation-select', current.formulations);
  $('definition-label').hidden = current.definitions.length < 2; $('formulation-label').hidden = current.formulations.length < 2;
  showDefinition(); showFormulation(); renderNav(); document.body.classList.remove('menu-open'); newTrial();
}
function imageMarkup(image, cls, number, zoom = true) {
  return `<div class="photo-shell ${cls}"><img src="${esc(image.url)}" alt="Изображение ${number}" draggable="false"><span class="photo-number">Изображение ${number}</span>${zoom ? `<button type="button" class="zoom-button" data-zoom="${esc(image.url)}" aria-label="Увеличить изображение ${number}">⤢</button>` : ''}</div>`;
}
function wireZoom() { $('trial').querySelectorAll('[data-zoom]').forEach(b => b.onclick = e => {e.stopPropagation(); $('large-image').src = b.dataset.zoom; $('image-dialog').showModal();}); }
function requestData() { return {participant,value_id:current.id,mode,definition_id:$('definition-select').value,formulation_id:$('formulation-select').value,criterion:$('criterion-select').value,context_id:$('context-select').value,presentation:participantView?'participant':'researcher'}; }
async function newTrial() {
  const ticket = ++epoch; trial = null; answer = null; confirmed = false; $('submit').disabled = true; $('answer-footer').hidden = true;
  document.body.classList.toggle('blind-bws', mode === 'bws');
  document.querySelectorAll('[data-mode]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.mode === mode)));
  $('instruction').textContent = cfg.paradigms[mode].instruction;
  const criterion = cfg.criteria[$('criterion-select').value];
  $('criterion-help').textContent = mode === 'bws' ? (criterion.bws_instruction || criterion.instruction) : criterion.instruction;
  $('context-help').textContent = cfg.contexts.find(c => c.id === $('context-select').value)?.text || '';
  $('context-help').hidden = !$('context-help').textContent;
  $('mode-kicker').textContent = mode === 'bws' ? 'ИНТЕРПРЕТАЦИЯ ИЗОБРАЖЕНИЯ' : cfg.criteria[$('criterion-select').value].label.toUpperCase();
  $('bws-note').hidden = mode !== 'bws'; $('trial-counter').textContent = current.response_count + ' ответов';
  if (current.image_count < cfg.paradigms[mode].min_images) {
    $('trial').innerHTML = `<div class="empty-state"><div class="empty-symbol">▧</div><h3>${current.image_count ? 'Нужно больше изображений' : 'Изображения ещё не добавлены'}</h3><p>${current.image_count ? 'Для этого режима требуется ' + cfg.paradigms[mode].min_images + ' изображений.' : 'Ценность уже есть в исследовании. Её набор изображений пока не заполнен.'}</p><code>images / ${esc(current.group.folder)} / ${esc(current.folder)}</code><p>Добавьте PNG, JPG или WebP и нажмите «Обновить коллекцию».</p></div>`; return;
  }
  $('trial').innerHTML = '<div class="empty-state"><p>Подготавливаем задание…</p></div>';
  try {
    const next = await api('/api/trial', requestData()); if (ticket !== epoch) return;
    trial = next; order = next.images.map(i => i.id); started = performance.now(); renderTrial();
    $('answer-footer').hidden = false; updateAnswer();
    $('session-status').textContent = next.cycle_complete ? 'Все варианты уже оценены. Начат новый круг.' : 'Ответ сохранится только после нажатия кнопки';
  } catch (e) { if (ticket === epoch) { $('trial').innerHTML = `<div class="empty-state"><h3>Не удалось получить задание</h3><p>${esc(e.message)}</p><button class="button" id="retry">Повторить</button></div>`; $('retry').onclick = newTrial; } }
}
function renderTrial() {
  const host = $('trial');
  if (mode === 'rating') {
    host.innerHTML = imageMarkup(trial.images[0], 'single-photo', 1) + `<div class="rating-panel"><span class="rating-anchor">Совсем<br>не соответствует</span><div class="rating-buttons" role="group" aria-label="Оценка от 1 до 5">${[1,2,3,4,5].map(n => `<button class="rating-button" data-rating="${n}" aria-label="Оценка ${n}" aria-pressed="false">${n}</button>`).join('')}</div><span class="rating-anchor">Полностью<br>соответствует</span></div>`;
    host.querySelectorAll('[data-rating]').forEach(b => b.onclick = () => { answer = Number(b.dataset.rating); host.querySelectorAll('[data-rating]').forEach(x => {x.classList.toggle('selected', x === b);x.setAttribute('aria-pressed',String(x===b));}); updateAnswer(); });
  }
  if (mode === 'pair') {
    host.innerHTML = `<div class="pair-grid">${trial.images.map((img,i) => `<button class="pair-card" data-choice="${esc(img.id)}" aria-pressed="false">${imageMarkup(img,'',i+1,false)}<span class="pair-label">Выбрать изображение ${i+1}</span></button>`).join('')}</div><div class="tie-wrap"><button class="button" data-choice="tie" aria-pressed="false">Одинаково подходят · ничья</button></div>`;
    host.querySelectorAll('[data-choice]').forEach(b => b.onclick = () => {answer=b.dataset.choice;host.querySelectorAll('[data-choice]').forEach(x => {x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});updateAnswer();});
  }
  if (mode === 'ranking') renderRanking();
  if (mode === 'bws') {
    answer = {best:null,worst:null};
    host.innerHTML = `<div class="bws-layout">${imageMarkup(trial.images[0],'bws-photo',1)}<div class="bws-options">${trial.options.map((o,i) => `<article class="bws-option"><h3>${i+1}. ${esc(o.concept)}</h3><p>${esc(o.explanation)}</p><div class="bws-choices"><label><input type="radio" name="best" data-pick="best" value="${esc(o.id)}"> Наиболее подходит</label><label><input type="radio" name="worst" data-pick="worst" value="${esc(o.id)}"> Наименее подходит</label></div></article>`).join('')}</div></div>`;
    host.querySelectorAll('[data-pick]').forEach(r => r.onchange = () => {const opposite=r.dataset.pick==='best'?'worst':'best';answer[r.dataset.pick]=r.value;if(answer[opposite]===r.value){answer[opposite]=null;host.querySelectorAll(`[data-pick="${opposite}"]`).forEach(x=>x.checked=false);}updateAnswer();});
    $('bws-note').textContent = (trial.options_source === 'dataset_definitions' ? 'Пилотный набор: четыре понятия с определениями из датасета. Собственные объяснения и состав четвёрок можно задать в конфиге. ' : 'Используется заданная в конфиге четвёрка интерпретаций. ') + 'Режим участника скрывает целевую ценность и меню.';
  }
  wireZoom();
}
function renderRanking() {
  $('trial').innerHTML = `<div class="ranking-grid">${order.map((id,i) => {const image=trial.images.find(x=>x.id===id);return `<article class="rank-card" draggable="true" data-index="${i}"><div class="rank-top"><span class="rank-pos">${i+1}</span><span>⠿</span></div>${imageMarkup(image,'',trial.images.indexOf(image)+1)}<div class="rank-controls"><button data-move="${i},-1" ${i===0?'disabled':''} aria-label="Переместить изображение на место выше">←</button><button data-move="${i},1" ${i===4?'disabled':''} aria-label="Переместить изображение на место ниже">→</button></div></article>`;}).join('')}</div><div class="rank-ends"><span>Больше соответствует</span><span>Меньше соответствует</span></div><label class="rank-confirm"><input id="rank-confirm" type="checkbox" ${confirmed?'checked':''}> Порядок проверен: от наиболее до наименее подходящего</label>`;
  $('trial').querySelectorAll('[data-move]').forEach(b=>b.onclick=()=>{const [from,delta]=b.dataset.move.split(',').map(Number);moveRank(from,from+delta);});
  $('trial').querySelectorAll('.rank-card').forEach(card=>{card.ondragstart=e=>{e.dataTransfer.setData('text/plain',card.dataset.index);card.classList.add('dragging');};card.ondragend=()=>card.classList.remove('dragging');card.ondragover=e=>e.preventDefault();card.ondrop=e=>{e.preventDefault();const from=Number(e.dataTransfer.getData('text/plain'));if(Number.isInteger(from)&&from>=0&&from<5)moveRank(from,Number(card.dataset.index));};});
  $('rank-confirm').onchange=e=>{confirmed=e.target.checked;answer=confirmed?[...order]:null;updateAnswer();};wireZoom();
}
function moveRank(from,to){const item=order.splice(from,1)[0];order.splice(to,0,item);confirmed=false;answer=null;renderRanking();updateAnswer();}
function updateAnswer(){const ready=mode==='bws'?Boolean(answer?.best&&answer?.worst&&answer.best!==answer.worst):answer!==null;$('submit').disabled=!ready||saving;$('answer-status').textContent=ready?(mode==='rating'?'Оценка '+answer+' из 5':'Ответ выбран'):'Выберите ответ';}
async function submit(){
  if(saving||!trial||$('submit').disabled)return;saving=true;updateAnswer();$('skip').disabled=true;
  try {await api('/api/response',{trial_id:trial.id,participant,answer,elapsed_ms:Math.round(performance.now()-started),presentation:participantView?'participant':'researcher'});toast('Ответ сохранён');await loadCatalog();await newTrial();}
  catch(e){toast(e.message,true);}finally{saving=false;$('skip').disabled=false;updateAnswer();}
}
$('search').oninput=renderNav;
$('refresh').onclick=async()=>{try{await loadCatalog();await newTrial();toast('Коллекция обновлена');}catch(e){toast(e.message,true);}};
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{if(saving)return;mode=b.dataset.mode;newTrial();});
$('definition-select').onchange=()=>{showDefinition();newTrial();};$('formulation-select').onchange=()=>{showFormulation();newTrial();};$('criterion-select').onchange=newTrial;$('context-select').onchange=newTrial;
$('settings-toggle').onclick=()=>$('settings-panel').hidden=!$('settings-panel').hidden;
$('menu-toggle').onclick=()=>document.body.classList.toggle('menu-open');
$('participant-view').onclick=()=>{participantView=!participantView;document.body.classList.toggle('participant-mode',participantView);$('participant-view').textContent=participantView?'Вернуться к настройке ↙':'Режим участника ↗';};
$('participant-id').onchange=async e=>{const next=e.target.value.trim();if(!/^[\p{L}\p{N}_-]{1,64}$/u.test(next)){toast('ID: буквы, цифры, дефис или подчёркивание.',true);e.target.value=participant;return;}participant=next;localStorage.setItem('hv-participant',participant);await loadCatalog();newTrial();};
$('new-participant').onclick=()=>{$('participant-id').value=freshParticipant();$('participant-id').dispatchEvent(new Event('change'));};
$('submit').onclick=submit;$('skip').onclick=()=>{if(!saving)newTrial();};$('close-dialog').onclick=()=>$('image-dialog').close();
document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)){e.preventDefault();$('search').focus();}});
loadCatalog(true).catch(e=>{toast(e.message,true);$('value-name').textContent='Не удалось загрузить исследование';});
