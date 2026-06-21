# sov_results.jsonl → docs/answers/<날짜>.json (AI별 답변 전문 + 인용 페이지 + 검색어)
# 대시보드에서 질문을 펼치면 그 주·그 질문의 AI별 답변/출처를 읽을 수 있게 함.
# 실행: python build_answers.py
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, 'docs', 'answers'); os.makedirs(OUTDIR, exist_ok=True)
WEBMAX = 9000  # 웹에 싣는 답변 최대 길이(전체 원본은 sov_results.jsonl에 보존)

rows = []
for l in open(os.path.join(HERE, 'sov_results.jsonl'), encoding='utf-8'):
    l = l.strip()
    if not l: continue
    try: rows.append(json.loads(l))
    except Exception: pass

# (date,engine,id) 최신값만, 에러레코드 제외
seen = {}
for r in rows:
    if r.get('mentioned') is None: continue
    seen[(r['date'], r['engine'], r['id'])] = r

bydate = {}
for (date, engine, qid), r in seen.items():
    bydate.setdefault(date, {}).setdefault(qid, {})[engine] = {
        'mentioned': bool(r.get('mentioned')),
        'rank': r.get('rank'),
        'answer': (r.get('answer') or '')[:WEBMAX],
        'sources': r.get('sources') or [],
        'searchQueries': r.get('searchQueries') or [],
    }

dates = sorted(bydate)
for date in dates:
    path = os.path.join(OUTDIR, date + '.json')
    json.dump(bydate[date], open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# 어떤 날짜가 풍부한 출처를 가졌는지(=신규 포맷) 표시용 인덱스
idx = {d: {'questions': len(bydate[d]),
           'withSources': sum(1 for q in bydate[d].values() for e in q.values() if e.get('sources'))}
       for d in dates}
json.dump({'dates': dates, 'detail': idx}, open(os.path.join(OUTDIR, 'index.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('docs/answers/ 생성: 날짜 %d개 — %s' % (len(dates), ', '.join('%s(출처%d)' % (d, idx[d]['withSources']) for d in dates)))
