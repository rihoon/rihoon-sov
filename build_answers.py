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

# (date,engine,id) 샘플 전부 보존(samples:3 측정). 에러레코드 제외
# [fix 2026-08-23] 이전엔 마지막 샘플만 남겨 카드(3샘플 합산 "1위")와 상세(미언급)가 어긋났음
groups = {}
for r in rows:
    if r.get('mentioned') is None: continue
    groups.setdefault((r['date'], r['engine'], r['id']), []).append(r)

bydate = {}
for (date, engine, qid), rs in groups.items():
    hits = [r for r in rs if r.get('mentioned')]
    ranks = [r['rank'] for r in hits if r.get('rank')]
    bydate.setdefault(date, {}).setdefault(qid, {})[engine] = {
        'mentioned': len(hits) * 2 >= len(rs) and len(hits) > 0,   # build_web_data와 동일 규칙
        'rank': min(ranks) if ranks else None,
        'hits': len(hits), 'n': len(rs),
        'samples': [{
            'mentioned': bool(r.get('mentioned')),
            'rank': r.get('rank'),
            'answer': (r.get('answer') or '')[:WEBMAX],
            'sources': r.get('sources') or [],
            'searchQueries': r.get('searchQueries') or [],
        } for r in rs],
    }

dates = sorted(bydate)
for date in dates:
    path = os.path.join(OUTDIR, date + '.json')
    json.dump(bydate[date], open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# 어떤 날짜가 풍부한 출처를 가졌는지(=신규 포맷) 표시용 인덱스
idx = {d: {'questions': len(bydate[d]),
           'withSources': sum(1 for q in bydate[d].values() for e in q.values() if any(x.get('sources') for x in e['samples']))}
       for d in dates}
json.dump({'dates': dates, 'detail': idx}, open(os.path.join(OUTDIR, 'index.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('docs/answers/ 생성: 날짜 %d개 — %s' % (len(dates), ', '.join('%s(출처%d)' % (d, idx[d]['withSources']) for d in dates)))
