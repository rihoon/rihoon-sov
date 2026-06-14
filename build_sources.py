# 각 질문별로 AI(Gemini 그라운딩)가 읽은 출처 문서 수집 → docs/sources.json
# 리다이렉트 URL을 실제 주소로 해석. 대시보드에서 질문마다 클릭 가능한 링크로 표시.
import json, os, re, urllib.request, time
import sov

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = json.load(open(os.path.join(HERE, 'sov_core.json'), encoding='utf-8'))
OUTDIR = os.path.join(HERE, 'docs'); os.makedirs(OUTDIR, exist_ok=True)
BRAND = [b.lower() for b in CORE['brand_terms']]
K = sov.S.get('gemini_key')

def grounded(q):
    url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=%s' % K
    body = {'contents': [{'parts': [{'text': q}]}], 'tools': [{'google_search': {}}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
    c = r['candidates'][0]; gm = c.get('groundingMetadata', {})
    txt = ''.join(p.get('text', '') for p in c['content']['parts'])
    return txt, gm.get('groundingChunks', []), gm.get('webSearchQueries', [])

def resolve(u):
    try:
        return urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=12).url
    except Exception as e:
        try: return e.url
        except Exception: return None

def kind(url):
    if 'youtube.com' in url or 'youtu.be' in url: return '유튜브'
    if 'tistory.com' in url: return '티스토리'
    if 'blog.naver' in url or 'm.blog.naver' in url: return '네이버블로그'
    if 'cafe.daum' in url or 'cafe.naver' in url: return '카페'
    if 'reddit.com' in url: return '레딧'
    if 'namu.wiki' in url: return '나무위키'
    if 'instagram.com' in url: return '인스타'
    return '웹/블로그'

out = {'questions': {}}
for q in CORE['questions']:
    try:
        txt, chunks, sqs = grounded(q['q'])
    except Exception as e:
        out['questions'][q['id']] = {'q': q['q'], 'kw': q['kw'], 'error': str(e)[:100]}; continue
    t = txt.lower()
    mentioned = any(b in t for b in BRAND)
    brands = [b for b in re.findall(r'\*\*([^*]{2,28})\*\*', txt) if not b.endswith(':') and not b.isdigit()]
    seen, sources = set(), []
    for ch in chunks:
        w = ch.get('web', {}); ru = resolve(w.get('uri', ''))
        if not ru or ru in seen: continue
        seen.add(ru)
        sources.append({'kind': kind(ru), 'title': w.get('title', ''), 'url': ru})
        if len(sources) >= 8: break
        time.sleep(0.05)
    out['questions'][q['id']] = {'q': q['q'], 'kw': q['kw'], 'line': q['line'],
                                 'mentioned': mentioned, 'searchQueries': sqs[:6],
                                 'brands': brands[:8], 'sources': sources}
    print('%-22s 리훈%s 출처%d개' % (q['kw'], '✓' if mentioned else '✗', len(sources)))
    time.sleep(0.3)

json.dump(out, open(os.path.join(OUTDIR, 'sources.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('→ docs/sources.json 저장 (질문 %d개)' % len(out['questions']))
