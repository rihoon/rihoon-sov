# 리훈 AEO SOV 자동측정 — 코어질문 × (있는 키만) AI엔진, 웹검색 켜서 실제 제품처럼 질의
# 결과: sov_results.jsonl 누적(날짜별) + 콘솔 요약표. 네이버Cue는 공개API 없어 수기.
import json, re, os, sys, time, datetime, urllib.request, urllib.error

# 1순위: 중앙 볼트(Z: RaiDrive 마운트). 스케줄러 세션에서 Z:가 안 잡히면 죽으므로
# 2순위: 스크립트 옆 로컬 폴백(sov_secrets.local.toml — .gitignore의 *.toml로 자동 제외).
SECRETS_CANDIDATES = [
    r'Z:/rihoon1/자동화/페북성과보고서 자동화/.streamlit/secrets.toml',
    os.path.join(os.path.dirname(__file__), 'sov_secrets.local.toml'),
]
CORE = os.path.join(os.path.dirname(__file__), 'sov_core.json')
OUT = os.path.join(os.path.dirname(__file__), 'sov_results.jsonl')

def _parse_toml(path):
    try:
        import tomllib
        return tomllib.load(open(path, 'rb'))
    except ImportError:
        pass
    cfg, sec = {}, None  # 최소 폴백 파서(tomllib 없는 구버전 파이썬)
    for ln in open(path, encoding='utf-8'):
        ln = ln.strip()
        m = re.match(r'\[([^\]]+)\]', ln)
        if m: sec = m.group(1); cfg[sec] = {}
        elif sec and '=' in ln and not ln.startswith('#'):
            k, v = ln.split('=', 1); cfg[sec][k.strip()] = v.strip().strip('"\'')
    return cfg

def load_secrets():
    last_err = None
    for path in SECRETS_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            cfg = _parse_toml(path)
            if cfg.get('ai'):              # [ai] 키가 실제로 있는 파일만 채택
                return cfg
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    raise FileNotFoundError(
        'secrets에서 [ai] 섹션을 못 찾음. 확인한 경로: ' + ' | '.join(SECRETS_CANDIDATES))

S = load_secrets().get('ai', {})
core = json.load(open(CORE, encoding='utf-8'))
BRAND = [b.lower() for b in core['brand_terms']]
COMP = [c.lower() for c in core['competitor_terms']]

def post(url, headers, body, timeout=90, retries=4):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', **headers})
    for attempt in range(retries):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt * 3); continue   # 3,6,12초 백오프
            raise

# --- 엔진별 호출 (웹검색 켜기). 키 없으면 None 반환 → 자동 스킵 ---
# 각 함수는 {'text': 답변전문, 'sources': [{url,title}], 'queries': [검색어]} 반환.
def _dedupe_src(srcs):
    seen, out = set(), []
    for s in srcs or []:
        u = (s.get('url') or '').strip()
        if not u or u in seen: continue
        seen.add(u); out.append({'url': u, 'title': (s.get('title') or '').strip()})
    return out

def ask_gemini(q):
    k = S.get('gemini_key')
    if not k: return None
    model = S.get('gemini_model', 'gemini-2.5-flash')
    url = 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s' % (model, k)
    body = {'contents': [{'parts': [{'text': q}]}], 'tools': [{'google_search': {}}]}
    r = post(url, {}, body)
    cand = r['candidates'][0]
    text = ''.join(p.get('text', '') for p in cand.get('content', {}).get('parts', []))
    gm = cand.get('groundingMetadata', {}) or {}
    srcs = []
    for ch in gm.get('groundingChunks', []) or []:
        w = ch.get('web') or {}
        if w.get('uri'): srcs.append({'url': w['uri'], 'title': w.get('title', '')})
    return {'text': text, 'sources': _dedupe_src(srcs), 'queries': gm.get('webSearchQueries', []) or []}

def ask_perplexity(q):
    k = S.get('perplexity_key')
    if not k: return None
    body = {'model': S.get('perplexity_model', 'sonar'), 'messages': [{'role': 'user', 'content': q}]}
    r = post('https://api.perplexity.ai/chat/completions', {'Authorization': 'Bearer ' + k}, body)
    text = r['choices'][0]['message']['content']
    srcs = []
    for sr in r.get('search_results', []) or []:
        if sr.get('url'): srcs.append({'url': sr['url'], 'title': sr.get('title', '')})
    if not srcs:
        for u in r.get('citations', []) or []:
            if isinstance(u, str): srcs.append({'url': u, 'title': ''})
    return {'text': text, 'sources': _dedupe_src(srcs), 'queries': []}

def ask_openai(q):
    k = S.get('openai_key')
    if not k: return None
    body = {'model': S.get('openai_model', 'gpt-4.1'), 'tools': [{'type': 'web_search_preview'}], 'input': q}
    r = post('https://api.openai.com/v1/responses', {'Authorization': 'Bearer ' + k}, body)
    out, srcs, queries = [], [], []
    for item in r.get('output', []):
        if item.get('type') == 'web_search_call':
            act = item.get('action') or {}
            if act.get('query'): queries.append(act['query'])
        for c in item.get('content', []) or []:
            if c.get('type') in ('output_text', 'text'):
                out.append(c.get('text', ''))
                for an in c.get('annotations', []) or []:
                    if an.get('type') == 'url_citation' and an.get('url'):
                        srcs.append({'url': an['url'], 'title': an.get('title', '')})
    text = '\n'.join(out) or json.dumps(r)[:500]
    return {'text': text, 'sources': _dedupe_src(srcs), 'queries': queries}

def ask_claude(q):
    k = S.get('anthropic_key')
    if not k: return None
    body = {'model': S.get('anthropic_model', 'claude-sonnet-4-6'), 'max_tokens': 2048,
            'tools': [{'type': 'web_search_20250305', 'name': 'web_search'}],
            'messages': [{'role': 'user', 'content': q}]}
    r = post('https://api.anthropic.com/v1/messages', {'x-api-key': k, 'anthropic-version': '2023-06-01'}, body)
    parts, srcs, queries = [], [], []
    for b in r.get('content', []) or []:
        bt = b.get('type')
        if bt == 'text':
            parts.append(b.get('text', ''))
            for ct in b.get('citations', []) or []:
                if ct.get('url'): srcs.append({'url': ct['url'], 'title': ct.get('title', '')})
        elif bt == 'server_tool_use':
            inp = b.get('input') or {}
            if inp.get('query'): queries.append(inp['query'])
        elif bt == 'web_search_tool_result':
            cont = b.get('content')
            if isinstance(cont, list):
                for w in cont:
                    if w.get('type') == 'web_search_result' and w.get('url'):
                        srcs.append({'url': w['url'], 'title': w.get('title', '')})
    return {'text': '\n'.join(parts), 'sources': _dedupe_src(srcs), 'queries': queries}

ENGINES = [('ChatGPT', ask_openai), ('Perplexity', ask_perplexity), ('Gemini', ask_gemini), ('Claude', ask_claude)]

def analyze(text):
    t = (text or '').lower()
    brand_hit = next((b for b in BRAND if b in t), None)
    comps = [c for c in COMP if c in t]
    rank = None
    if brand_hit:                                  # 리훈이 경쟁사보다 앞에 나오나(첫 등장 위치)
        bpos = t.index(brand_hit)
        rank = 1 + sum(1 for c in comps if t.index(c) < bpos)
    return {'mentioned': bool(brand_hit), 'brand_hit': brand_hit, 'rank': rank, 'competitors': comps}

def main():
    today = datetime.date.today().isoformat()
    active = [(n, f) for n, f in ENGINES if (f.__name__ == 'ask_gemini' and S.get('gemini_key')) or
              (f.__name__ == 'ask_perplexity' and S.get('perplexity_key')) or
              (f.__name__ == 'ask_openai' and S.get('openai_key')) or
              (f.__name__ == 'ask_claude' and S.get('anthropic_key'))]
    only = set(a.lower() for a in sys.argv[1:])      # 예: python sov.py perplexity claude
    if only: active = [(n, f) for n, f in active if n.lower() in only]
    if not active:
        print('⚠ 활성 엔진 없음 ([ai] 키 확인 or 인자로 준 엔진명 확인)'); return
    print('측정 엔진: %s | 질문 %d개 | %s' % (', '.join(n for n, _ in active), len(core['questions']), today))
    fout = open(OUT, 'a', encoding='utf-8')
    summary = {n: {'mention': 0, 'top1': 0} for n, _ in active}
    for qi in core['questions']:
        line = '· %-22s' % (qi['kw'])
        for name, fn in active:
            try:
                res = fn(qi['q'])
                if isinstance(res, dict):
                    ans = res.get('text', ''); srcs = res.get('sources', []); queries = res.get('queries', [])
                else:
                    ans = res or ''; srcs = []; queries = []
                a = analyze(ans)
                rec = {'date': today, 'engine': name, 'id': qi['id'], 'kw': qi['kw'], 'q': qi['q'],
                       'mentioned': a['mentioned'], 'rank': a['rank'], 'competitors': a['competitors'],
                       'answer': (ans or '')[:12000], 'sources': srcs, 'searchQueries': queries}
                fout.write(json.dumps(rec, ensure_ascii=False) + '\n'); fout.flush()
                if a['mentioned']: summary[name]['mention'] += 1
                if a['rank'] == 1: summary[name]['top1'] += 1
                mark = ('✓%s' % (a['rank'] or '?')) if a['mentioned'] else '✗'
                line += ' %s:%-4s' % (name[:4], mark)
            except Exception as e:
                line += ' %s:ERR' % name[:4]
                fout.write(json.dumps({'date': today, 'engine': name, 'id': qi['id'], 'error': str(e)[:200]}, ensure_ascii=False) + '\n'); fout.flush()
        print(line)
        time.sleep(1.5)
    n = len(core['questions'])
    print('\n=== SOV 요약 (%s) ===' % today)
    for name, _ in active:
        s = summary[name]
        print('%-11s 언급률 %2d/%d (%3d%%)  1위 %d회' % (name, s['mention'], n, round(100*s['mention']/n), s['top1']))
    print('\n네이버Cue: 공개API 없음 → 수기 측정 필요(12질문 직접 입력)')
    print('상세결과: sov_results.jsonl')

if __name__ == '__main__':
    main()
