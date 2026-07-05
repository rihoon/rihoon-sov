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
            if e.code in (429, 500, 502, 503, 529) and attempt < retries - 1:
                time.sleep(2 ** attempt * 3); continue   # 3,6,12초 백오프
            # 에러 본문까지 남겨야 원인 진단 가능 (예: Anthropic은 크레딧 부족도 400으로 옴)
            try:
                detail = e.read().decode('utf-8', 'replace')[:300]
            except Exception:
                detail = ''
            raise urllib.error.HTTPError(e.url, e.code, '%s | %s' % (e.reason, detail), e.headers, None) from None

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
    # max_uses: 질문당 웹검색 횟수 상한 → 1회 측정 비용 고정·예측 가능(비용 폭주 방지)
    body = {'model': S.get('anthropic_model', 'claude-sonnet-4-6'), 'max_tokens': 2048,
            'tools': [{'type': 'web_search_20250305', 'name': 'web_search',
                       'max_uses': int(S.get('claude_search_max', 3))}],
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

def done_today(today):
    # 같은 날 이미 '성공'(에러 아님)한 (엔진,질문)별 샘플 수 → 부족분만 호출(중복 과금 방지)
    done = {}
    if os.path.exists(OUT):
        for l in open(OUT, encoding='utf-8'):
            l = l.strip()
            if not l: continue
            try: r = json.loads(l)
            except Exception: continue
            if r.get('date') == today and r.get('mentioned') is not None and r.get('engine') and r.get('id'):
                done[(r['engine'], r['id'])] = done.get((r['engine'], r['id']), 0) + 1
    return done

def tally_today(today):
    # 오늘 성공 기록 '전체'를 (engine,id) 단위로 합쳐 엔진별 언급/1위 집계.
    # 다샘플이면 과반(≥절반)일 때 언급으로 침 — build_web_data의 집계 기준과 동일.
    cells = {}
    if os.path.exists(OUT):
        for l in open(OUT, encoding='utf-8'):
            l = l.strip()
            if not l:
                continue
            try:
                r = json.loads(l)
            except Exception:
                continue
            if r.get('date') != today or r.get('engine') is None or r.get('id') is None:
                continue
            if r.get('error') or r.get('mentioned') is None:
                continue
            cells.setdefault((r['engine'], r['id']), []).append(r)
    tal = {}
    for (eng, _id), rs in cells.items():
        s = tal.setdefault(eng, {'mention': 0, 'top1': 0})
        hits = [r for r in rs if r.get('mentioned')]
        if len(hits) * 2 >= len(rs):
            s['mention'] += 1
            if any(r.get('rank') == 1 for r in hits):
                s['top1'] += 1
    return tal


def report_job(status, message):
    """어드민 잡 모니터(job_runs)에 결과 보고. 어드민 .env 없으면 조용히 스킵."""
    try:
        env = {}
        p = r'Z:/rihoon1/자동화/리훈 종합 어드민/.env'
        if not os.path.exists(p): return
        for line in open(p, encoding='utf-8-sig'):
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1); env[k.strip()] = v.strip()
        url = env.get('NEXT_PUBLIC_SUPABASE_URL', '').rstrip('/'); key = env.get('SUPABASE_SERVICE_ROLE_KEY', '')
        if not (url and key): return
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        body = {'job_name': 'sov_weekly', 'status': status, 'message': message[:2000], 'finished_at': now}
        req = urllib.request.Request(url + '/rest/v1/job_runs', data=json.dumps(body).encode(),
                                     headers={'apikey': key, 'Authorization': 'Bearer ' + key,
                                              'Content-Type': 'application/json', 'Prefer': 'return=minimal'})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print('[job보고 실패(무시)]', e)


# 크레딧 소진 등 회복 불가 에러 신호 — 보이면 그 엔진 잔여 호출을 전부 중단(헛과금·헛대기 방지)
FATAL_SIGNS = ('credit balance', 'billing', 'quota exceeded', 'insufficient_quota', 'suspended')


def main():
    today = datetime.date.today().isoformat()
    active = [(n, f) for n, f in ENGINES if (f.__name__ == 'ask_gemini' and S.get('gemini_key')) or
              (f.__name__ == 'ask_perplexity' and S.get('perplexity_key')) or
              (f.__name__ == 'ask_openai' and S.get('openai_key')) or
              (f.__name__ == 'ask_claude' and S.get('anthropic_key'))]
    args = [a.lower() for a in sys.argv[1:]]
    force = '--force' in args                          # --force: 이미 성공한 것도 재측정(비용↑, 기본 OFF)
    only = set(a for a in args if not a.startswith('-'))   # 예: python sov.py perplexity claude
    if only: active = [(n, f) for n, f in active if n.lower() in only]
    if not active:
        print('⚠ 활성 엔진 없음 ([ai] 키 확인 or 인자로 준 엔진명 확인)'); return
    samples = max(1, int(core.get('samples', 1)))      # 질문당 반복 측정 수(sov_core.json "samples") → 평균 집계
    done = {} if force else done_today(today)          # 기본: 오늘 이미 채운 샘플만큼 건너뜀(부족분만 호출)
    if done: print('↻ 오늘 이미 성공한 샘플은 스킵 → 부족분만 측정 (전체 재측정은 --force)')
    print('측정 엔진: %s | 질문 %d개 × 샘플 %d회 | %s' % (', '.join(n for n, _ in active), len(core['questions']), samples, today))
    fout = open(OUT, 'a', encoding='utf-8')
    dead = {}                                          # 엔진명 → 사망 사유(연속 에러·크레딧 소진)
    errstreak = {}
    errors = 0
    for qi in core['questions']:
        line = '· %-22s' % (qi['kw'])
        called = False
        for name, fn in active:
            if name in dead:
                line += ' %s:DEAD' % name[:4]; continue
            need = samples - done.get((name, qi['id']), 0)
            if need <= 0:                              # 샘플 충족 → API 호출 안 함(과금 0)
                line += ' %s:skip' % name[:4]; continue
            marks = []
            for _ in range(need):
                called = True
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
                    marks.append(('✓%s' % (a['rank'] or '?')) if a['mentioned'] else '✗')
                    errstreak[name] = 0
                except Exception as e:
                    errors += 1
                    msg = str(e)
                    marks.append('ERR')
                    fout.write(json.dumps({'date': today, 'engine': name, 'id': qi['id'], 'error': msg[:300]}, ensure_ascii=False) + '\n'); fout.flush()
                    errstreak[name] = errstreak.get(name, 0) + 1
                    low = msg.lower()
                    if any(s in low for s in FATAL_SIGNS):
                        dead[name] = msg[:120]
                    elif errstreak[name] >= 3:         # 연속 3회 에러 → 이번 실행에선 포기(다음 실행이 부족분 재측정)
                        dead[name] = '연속 에러 3회: ' + msg[:100]
                    if name in dead:
                        print('\n⛔ %s 중단: %s' % (name, dead[name]))
                        break
                time.sleep(0.8)
            line += ' %s:%-4s' % (name[:4], '/'.join(marks)[:9] if marks else '-')
        print(line)
        if called: time.sleep(1.0)
    n = len(core['questions'])
    tal = tally_today(today)   # 파일 전체 재집계 → 여러 번 나눠 측정해도 합산
    print('\n=== SOV 요약 (%s) — 오늘 전체 측정 합산 (샘플 과반 기준) ===' % today)
    for name, _ in active:
        s = tal.get(name, {'mention': 0, 'top1': 0})
        pct = round(100 * s['mention'] / n) if n else 0
        print('%-11s 언급률 %2d/%d (%3d%%)  1위 %d회' % (name, s['mention'], n, pct, s['top1']))
    if dead:
        print('\n⛔ 중단된 엔진:')
        for k, v in dead.items(): print('  %s: %s' % (k, v))
    print('\n네이버Cue: 공개API 없음 → 수기 측정 필요(12질문 직접 입력)')
    print('상세결과: sov_results.jsonl')
    # 어드민 잡 모니터 보고 — 에러/중단 있으면 fail로 남겨 신호등에 뜨게
    if dead or errors:
        report_job('fail', '에러 %d건, 중단 엔진: %s' % (errors, '; '.join('%s(%s)' % kv for kv in dead.items()) or '없음'))
    else:
        report_job('success', '측정 완료 — 질문 %d × 샘플 %d' % (n, samples))

if __name__ == '__main__':
    main()
