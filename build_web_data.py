# sov_results.jsonl → web/data.json (공개안전 집계본). 실행: python build_web_data.py
import json, os, re
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = json.load(open(os.path.join(HERE, 'sov_core.json'), encoding='utf-8'))
WEB = os.path.join(HERE, 'docs'); os.makedirs(WEB, exist_ok=True)
ENGINES = ['Gemini', 'Perplexity', 'Claude', 'ChatGPT', '네이버 AI브리핑']  # 표시 순서(네이버=수기)
COMP_TERMS = CORE.get('competitor_terms', [])      # 경쟁사는 답변원문에서 '현재' 용어로 재추출(소급 반영)
COMP_NORM = {'아날로그 키퍼': '아날로그키퍼'}        # 표기 통일(띄어쓰기 변형 합치기)

rows = []
for l in open(os.path.join(HERE, 'sov_results.jsonl'), encoding='utf-8'):
    try: rows.append(json.loads(l))
    except Exception: pass

# (date,engine,id)별 샘플 '전부' 수집, 에러 제외 — 다샘플이면 과반=언급, 언급률은 샘플 평균
samples_by = {}
for r in rows:
    if r.get('mentioned') is None: continue
    samples_by.setdefault((r['date'], r['engine'], r['id']), []).append(r)

def cell_agg(rs):
    """샘플 목록 → 대표값. m=과반 언급, mrate=샘플 언급률(0~1), rank=언급 샘플 중 최선."""
    hits = [r for r in rs if r.get('mentioned')]
    ranks = [r['rank'] for r in hits if r.get('rank')]
    return {
        'm': len(hits) * 2 >= len(rs) and len(hits) > 0,
        'mrate': len(hits) / len(rs),
        'rank': min(ranks) if ranks else None,
        'n': len(rs),
        'hits': len(hits),
        'last': rs[-1],   # 출처·경쟁사 추출용 대표 레코드(마지막 샘플)
    }

seen = {k: cell_agg(rs) for k, rs in samples_by.items()}
meas = [{'date': k[0], 'engine': k[1], 'id': k[2], 'mentioned': v['m'], 'mrate': v['mrate']}
        for k, v in seen.items()]
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
        # 티스토리는 블로그별 서브도메인 → 남의 블로그는 플랫폼으로 묶고, 리훈 것만 따로(⭐) 표시
        if net.endswith('.tistory.com') and net != 'rihoon.tistory.com':
            net = 'tistory.com'
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
            c = seen.get((date, e, i))
            if not c:
                eng[e] = None; continue
            nmeas += 1
            m = c['m']; rk = c['rank']
            eng[e] = {'m': m, 'rank': rk, 'n': c['n'], 'hits': c['hits']}
            if m: ment = True
            if rk == 1 and m: won = True
            r = c['last']
            doms = set()                                  # 출처: 셀당 도메인 1회 카운트(대표 샘플)
            for s in (r.get('sources') or []):
                d = domain_of(s)
                if d and d not in doms:
                    doms.add(d); src_cnt[d] = src_cnt.get(d, 0) + 1
                    src_samp.setdefault(d, s.get('url') or '')
            if not m:                                     # 경쟁사: 리훈 없을 때만, 답변원문에서 현재 용어로 재추출
                atext = (r.get('answer') or '').lower()
                cseen = set()
                for c in COMP_TERMS:
                    if c.lower() not in atext: continue
                    name = COMP_NORM.get(c, c)
                    if not hangul(name) or name in cseen: continue
                    cseen.add(name); comp_cnt[name] = comp_cnt.get(name, 0) + 1
                    comp_kw.setdefault(name, [])
                    if q['kw'] not in comp_kw[name]: comp_kw[name].append(q['kw'])
                    if name not in comps: comps.append(name)
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

# 추세: 날짜별 전체 언급률 + 엔진별 — 다샘플은 셀별 샘플 언급률(mrate)의 평균 = "2~3회 평균값"
trend = []
for d in dates:
    day = [r for r in meas if r['date'] == d]
    rate = round(100 * sum(r['mrate'] for r in day) / len(day)) if day else 0
    by = {}
    for e in ENGINES:
        de = [r for r in day if r['engine'] == e]
        if de: by[e] = round(100 * sum(r['mrate'] for r in de) / len(de))
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
