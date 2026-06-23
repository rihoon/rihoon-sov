# -*- coding: utf-8 -*-
"""노션 "신제품 및 이벤트 일정" → live-schedule.json 동기화.
라이브 페이지 캘린더가 이 JSON을 읽어 일정을 표시.
토큰: 인스타컨텐츠 .env 의 NOTION_API_KEY (이 연동에 DB 공유돼 있음)."""
import re, json, os, urllib.request, datetime

ENV = r'Z:/rihoon1/자동화/[AI페어워크]인스타컨텐츠 제작/.env'
DB  = 'f218f7a9944b4db4a47bde68343d8445'
_BASE = os.path.dirname(os.path.abspath(__file__))
# GitHub Pages는 docs/ 에서 서빙 → docs/ 있으면 거기에, 없으면(로컬테스트) 옆에
OUT = os.path.join(_BASE, 'docs', 'live-schedule.json') if os.path.isdir(os.path.join(_BASE, 'docs')) else os.path.join(_BASE, 'live-schedule.json')

# 토큰: GitHub Action에선 환경변수(시크릿), 로컬에선 .env에서
tok = os.environ.get('NOTION_API_KEY')
if not tok and os.path.exists(ENV):
    m = re.search(r'NOTION_API_KEY\s*=\s*["\']?(ntn_[A-Za-z0-9_\-]+|secret_[A-Za-z0-9_\-]+)',
                  open(ENV, encoding='utf-8').read())
    tok = m.group(1) if m else None
if not tok:
    raise SystemExit('NOTION_API_KEY 없음 (환경변수 또는 .env 확인)')
H = {'Authorization': 'Bearer ' + tok, 'Notion-Version': '2022-06-28', 'Content-Type': 'application/json'}


def query():
    rows, cur = [], None
    while True:
        body = {'page_size': 100}
        if cur:
            body['start_cursor'] = cur
        req = urllib.request.Request('https://api.notion.com/v1/databases/' + DB + '/query',
                                     data=json.dumps(body).encode(), headers=H, method='POST')
        r = json.loads(urllib.request.urlopen(req, timeout=20).read())
        rows += r['results']
        if r.get('has_more'):
            cur = r['next_cursor']
        else:
            break
    return rows


def val(p):
    if not p:
        return None
    t = p['type']; v = p[t]
    if t in ('title', 'rich_text'):
        return ''.join(x.get('plain_text', '') for x in v)
    if t == 'date':
        return (v or {}).get('start')
    if t == 'select':
        return (v or {}).get('name')
    if t == 'multi_select':
        return [x['name'] for x in v]
    if t == 'url':
        return v
    return None


def reveal_window():
    """공개 가능 구간 [이번달 1일 .. 노출월 말일].
    오늘 29일 전이면 노출월=이번달, 29일부터면 노출월=다음달.
    → 그 이후 달(아직 숨길 일정)은 JSON에 아예 포함하지 않음(공개 파일 유출 방지)."""
    import calendar
    t = datetime.date.today()
    start = t.replace(day=1).isoformat()
    y, m = t.year, t.month
    if t.day >= 29:
        m += 1
        if m > 12:
            m = 1; y += 1
    end = datetime.date(y, m, calendar.monthrange(y, m)[1]).isoformat()
    return start, end


def main():
    start, end = reveal_window()
    out = []
    for row in query():
        p = row['properties']
        date = val(p.get('날짜'))
        if not date or not (start <= date[:10] <= end):
            continue
        media = val(p.get('매체')) or []
        out.append({
            'date': date[:10],
            'title': val(p.get('제목')) or '',
            'desc': val(p.get('설명')) or '',
            'sale': val(p.get('할인율')) or '',
            'media': media,
            'url': val(p.get('링크')) or '',
            'holiday': ('공휴일' in media),
        })
    out.sort(key=lambda x: x['date'])
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('총 %d건 → %s' % (len(out), OUT))
    for i in out[:10]:
        print('  ', i['date'], '|', (i['sale'] or '-'), '|', i['title'], '|', ('공휴일' if i['holiday'] else '라이브'))


if __name__ == '__main__':
    main()
