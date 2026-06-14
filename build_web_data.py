# sov_results.jsonl → web/data.json (공개안전 집계본). 실행: python build_web_data.py
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = json.load(open(os.path.join(HERE, 'sov_core.json'), encoding='utf-8'))
WEB = os.path.join(HERE, 'docs'); os.makedirs(WEB, exist_ok=True)
ENGINES = ['Gemini', 'Perplexity', 'Claude', 'ChatGPT', '네이버Cue']  # 표시 순서(네이버=수기)

rows = []
for l in open(os.path.join(HERE, 'sov_results.jsonl'), encoding='utf-8'):
    try: rows.append(json.loads(l))
    except Exception: pass

# (date,engine,id) 최신값, 에러 제외
seen = {}
for r in rows:
    if r.get('mentioned') is None: continue
    seen[(r['date'], r['engine'], r['id'])] = r
meas = list(seen.values())
dates = sorted({r['date'] for r in meas})
if not dates:
    json.dump({'updated': None, 'questions': []}, open(os.path.join(WEB, 'data.json'), 'w', encoding='utf-8')); raise SystemExit('데이터 없음')
latest = dates[-1]

def hangul(s): return bool(re.search('[가-힣]', str(s)))
qmap = {q['id']: q for q in CORE['questions']}

questions = []
for q in CORE['questions']:
    i = q['id']
    eng = {}
    comps, won, ment, nmeas = [], False, False, 0
    for e in ENGINES:
        r = seen.get((latest, e, i))
        if not r:
            eng[e] = None; continue
        nmeas += 1
        m = bool(r['mentioned']); rk = r.get('rank')
        eng[e] = {'m': m, 'rank': rk}
        if m: ment = True
        if rk == 1: won = True
        if not m:
            for c in (r.get('competitors') or []):
                if hangul(c) and c not in comps: comps.append(c)
    verdict = 'win1' if won else ('win' if ment else ('hole' if nmeas else 'none'))
    questions.append({'q': q['q'], 'kw': q['kw'], 'line': q['line'], 'verdict': verdict,
                      'engines': eng, 'competitors': comps[:5]})

# 추세: 날짜별 전체 언급률 + 엔진별
trend = []
for d in dates:
    day = [r for r in meas if r['date'] == d]
    rate = round(100 * sum(1 for r in day if r['mentioned']) / len(day)) if day else 0
    by = {}
    for e in ENGINES:
        de = [r for r in day if r['engine'] == e]
        if de: by[e] = round(100 * sum(1 for r in de if r['mentioned']) / len(de))
    trend.append({'date': d, 'rate': rate, 'byEngine': by})

cur = [r for r in meas if r['date'] == latest]
measured_q = len({r['id'] for r in cur})
won_q = sum(1 for q in questions if q['verdict'] in ('win1', 'win'))
top1_q = sum(1 for q in questions if q['verdict'] == 'win1')
measured_engines = sorted({r['engine'] for r in cur})

out = {
    'updated': latest,
    'engines': ENGINES,
    'measuredEngines': measured_engines,
    'engineNote': {'ChatGPT': '충전 반영 대기', '네이버Cue': '공개 API 없음 · 수기'},
    'summary': {'measuredQuestions': measured_q, 'won': won_q, 'top1': top1_q, 'holes': measured_q - won_q},
    'questions': questions,
    'trend': trend,
}
json.dump(out, open(os.path.join(WEB, 'data.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('web/data.json 생성: 질문%d · 추천%d(1위%d) · 공백%d · 엔진%s' % (measured_q, won_q, top1_q, measured_q - won_q, measured_engines))
