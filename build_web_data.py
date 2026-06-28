# sov_results.jsonl → web/data.json (공개안전 집계본). 실행: python build_web_data.py
import json, os, re
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = json.load(open(os.path.join(HERE, 'sov_core.json'), encoding='utf-8'))
WEB = os.path.join(HERE, 'docs'); os.makedirs(WEB, exist_ok=True)
ENGINES = ['Gemini', 'Perplexity', 'Claude', 'ChatGPT', '네이버 AI브리핑']  # 표시 순서(네이버=수기)

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


def domain_of(s):
    u = (s.get('url') or ''); t = (s.get('title') or '').strip()
    if 'vertexaisearch' in u or 'grounding-api' in u:   # Gemini 리다이렉트 → title이 도메인
        return (t or u)[:50]
    try:
        net = urlparse(u).netloc.lower()
        if net.startswith('www.'): net = net[4:]
        return net or (t or u)[:50]
    except Exception:
        return (t or u)[:50]


def build_week(date):
    questions = []
    src_cnt, src_samp, comp_cnt, comp_kw = {}, {}, {}, {}
    for q in CORE['questions']:
        i = q['id']
        eng = {}
        comps, won, ment, nmeas = [], False, False, 0
        for e in ENGINES:
            r = seen.get((date, e, i))
            if not r:
                eng[e] = None; continue
            nmeas += 1
            m = bool(r['mentioned']); rk = r.get('rank')
            eng[e] = {'m': m, 'rank': rk}
            if m: ment = True
            if rk == 1: won = True
            doms = set()                                  # 출처: 답변당 도메인 1회 카운트
            for s in (r.get('sources') or []):
                d = domain_of(s)
                if d and d not in doms:
                    doms.add(d); src_cnt[d] = src_cnt.get(d, 0) + 1
                    src_samp.setdefault(d, s.get('url') or '')
            if not m:                                     # 경쟁사: 리훈 없을 때만
                cseen = set()
                for c in (r.get('competitors') or []):
                    if hangul(c) and c not in cseen:
                        cseen.add(c); comp_cnt[c] = comp_cnt.get(c, 0) + 1
                        comp_kw.setdefault(c, [])
                        if q['kw'] not in comp_kw[c]: comp_kw[c].append(q['kw'])
                        if c not in comps: comps.append(c)
        verdict = 'win1' if won else ('win' if ment else ('hole' if nmeas else 'none'))
        questions.append({'id': i, 'q': q['q'], 'kw': q['kw'], 'line': q['line'], 'verdict': verdict,
                          'engines': eng, 'competitors': comps[:5]})
    cur = [r for r in meas if r['date'] == date]
    mq = len({r['id'] for r in cur})
    won_q = sum(1 for x in questions if x['verdict'] in ('win1', 'win'))
    top1_q = sum(1 for x in questions if x['verdict'] == 'win1')
    top_sources = sorted(({'domain': d, 'n': n, 'url': src_samp.get(d, ''), 'rihoon': 'rihoon' in d.lower()}
                          for d, n in src_cnt.items()), key=lambda x: -x['n'])[:14]
    comp_rank = sorted(({'name': c, 'n': n, 'kws': comp_kw.get(c, [])[:6]} for c, n in comp_cnt.items()),
                       key=lambda x: -x['n'])[:10]
    return {
        'measuredEngines': sorted({r['engine'] for r in cur}),
        'summary': {'measuredQuestions': mq, 'won': won_q, 'top1': top1_q, 'holes': mq - won_q},
        'questions': questions,
        'topSources': top_sources,
        'competitorRank': comp_rank,
    }

weeks = {d: build_week(d) for d in dates}          # 모든 주의 질문별 상세
questions = weeks[latest]['questions']             # 하위호환: 최상위는 최신 주

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

lw = weeks[latest]
measured_q = lw['summary']['measuredQuestions']
won_q = lw['summary']['won']; top1_q = lw['summary']['top1']
measured_engines = lw['measuredEngines']

out = {
    'updated': latest,
    'engines': ENGINES,
    'measuredEngines': measured_engines,
    'engineNote': {'네이버 AI브리핑': '검색 상단 AI요약 · 수기'},
    'summary': lw['summary'],
    'questions': questions,
    'weeks': weeks,
    'trend': trend,
}
json.dump(out, open(os.path.join(WEB, 'data.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('web/data.json 생성: 주%d개 · 최신%s 질문%d · 추천%d(1위%d) · 공백%d · 엔진%s' % (
    len(weeks), latest, measured_q, won_q, top1_q, measured_q - won_q, measured_engines))
