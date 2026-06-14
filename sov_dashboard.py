# 리훈 AEO 대시보드 — 누구나 한눈에 이해되게. 실행: streamlit run sov_dashboard.py
import json, os, re
import pandas as pd
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'sov_results.jsonl')
CORE = json.load(open(os.path.join(HERE, 'sov_core.json'), encoding='utf-8'))

st.set_page_config(page_title='리훈 AI 추천 현황', layout='wide')

# ---------- 데이터 ----------
rows = []
if os.path.exists(RESULTS):
    for l in open(RESULTS, encoding='utf-8'):
        try: rows.append(json.loads(l))
        except Exception: pass
df = pd.DataFrame(rows)
if df.empty or 'mentioned' not in df:
    st.title('리훈 AI 추천 현황'); st.info('아직 측정 데이터가 없습니다. `python sov.py` 를 먼저 실행하세요.'); st.stop()

meas = df[df['mentioned'].notna()].drop_duplicates(subset=['date', 'engine', 'id'], keep='last').copy()
meas['mentioned'] = meas['mentioned'].astype(bool)
meas['top1'] = meas['rank'].apply(lambda r: r == 1 if pd.notna(r) else False)
dates = sorted(meas['date'].unique())
latest = dates[-1]
cur = meas[meas['date'] == latest]

qmap = {q['id']: q['q'] for q in CORE['questions']}
kwmap = {q['id']: q['kw'] for q in CORE['questions']}
linemap = {q['id']: q['line'] for q in CORE['questions']}
ids = [q['id'] for q in CORE['questions']]

def hangul(s): return bool(re.search('[가-힣]', str(s)))
def q_competitors(idv):
    out = []
    for _, r in cur[cur['id'] == idv].iterrows():
        c = r['competitors']
        if isinstance(c, list): out += [x for x in c if hangul(x)]
    seen = []
    for x in out:
        if x not in seen: seen.append(x)
    return seen

def q_verdict(idv):
    sub = cur[cur['id'] == idv]
    if sub.empty: return '⚪ 미측정', 0, 0
    nment = int(sub['mentioned'].sum()); nmeas = len(sub)
    if sub['top1'].any(): return '🟢 1위로 추천', nment, nmeas
    if nment > 0: return '🟡 언급은 됨', nment, nmeas
    return '🔴 안 나옴', nment, nmeas

# ---------- 헤드라인 ----------
st.title('🔍 리훈, AI가 추천해주나?')
measured = cur['id'].nunique()
won = sum(1 for i in ids if not cur[cur['id'] == i].empty and cur[cur['id'] == i]['mentioned'].any())
top1 = sum(1 for i in ids if not cur[cur['id'] == i].empty and cur[cur['id'] == i]['top1'].any())
holes = measured - won
st.markdown('#### 사람들이 AI에게 `“○○ 추천해줘”` 물었을 때, 리훈이 답에 나오는지 추적합니다.')
st.markdown('### → 측정한 **%d개** 질문 중 **:green[%d개]** 에서 리훈이 추천됨 (그중 **%d개는 1위**), **:red[%d개]** 는 아직 안 나옴.' % (measured, won, top1, holes))
st.caption('측정일: %s · 엔진: %s' % (latest, ', '.join(sorted(cur['engine'].unique()))))

c1, c2, c3 = st.columns(3)
c1.metric('🟢 추천되는 질문', '%d개' % won)
c2.metric('🥇 1위 차지', '%d개' % top1)
c3.metric('🔴 비어있는 질문', '%d개' % holes)

with st.expander('📖 이 표 보는 법 (처음이면 클릭)'):
    st.markdown('''
- **🟢 1위로 추천** = AI가 그 질문에 리훈을 1순위로 추천함 (최고)
- **🟡 언급은 됨** = 추천 목록에 끼긴 했지만 1위는 아님
- **🔴 안 나옴** = AI가 리훈을 아예 모름 → **여기가 콘텐츠 깔 자리**
- **대신 추천되는 곳** = 리훈 자리에 AI가 추천하는 경쟁사 (이들을 이겨야 함)
- **목표**: 🔴을 🟢으로 바꾸고, 아래 추세선을 우상향으로.
''')

# ---------- 질문별 현황 (핵심) ----------
st.subheader('📋 질문별 현황 — 우리가 어디서 이기고 어디서 지나')
recs = []
for i in ids:
    v, nment, nmeas = q_verdict(i)
    comps = q_competitors(i)
    recs.append({'질문': qmap[i], '상태': v, '추천한 AI': ('%d/%d' % (nment, nmeas)) if nmeas else '-',
                 '대신 추천되는 곳': ', '.join(comps[:4]) if comps else '—', '제품군': linemap[i]})
disp = pd.DataFrame(recs).sort_values('상태')  # 🔴 위로 오게

def paint(v):
    if '🟢' in v: return 'background-color:#e8f5e9; color:#1b5e20; font-weight:700'
    if '🟡' in v: return 'background-color:#fff8e1; color:#e65100; font-weight:700'
    if '🔴' in v: return 'background-color:#ffebee; color:#b71c1c; font-weight:700'
    return 'color:#9e9e9e'
st.dataframe(disp.style.map(paint, subset=['상태']), hide_index=True, width='stretch',
             column_config={'질문': st.column_config.TextColumn(width='large'),
                            '대신 추천되는 곳': st.column_config.TextColumn(width='medium')})

# ---------- 추세 ----------
st.subheader('📈 성장 추세 — 측정할 때마다 쌓입니다')
trend = (meas.groupby('date')['mentioned'].mean() * 100).round()
trend.name = '리훈 추천 비율(%)'
st.line_chart(trend, height=240)
if len(dates) == 1:
    st.caption('오늘이 첫 측정(기준선)이라 점 하나예요. 콘텐츠 깔고 다음에 다시 측정하면, 이 선이 올라가는 게 보입니다. ← 이게 핵심.')

# ---------- 할 일 ----------
st.subheader('✅ 지금 할 일 — 비어있는 자리 채우기')
holes_q = [qmap[i] for i in ids if not cur[cur['id'] == i].empty and not cur[cur['id'] == i]['mentioned'].any()]
if holes_q:
    st.markdown('아래 질문들에서 AI가 리훈을 모릅니다. **티스토리 글 / 유튜브 롱폼**으로 이 주제 콘텐츠를 깔면 채워집니다:')
    for h in holes_q: st.markdown('- 🔴 %s' % h)
else:
    st.success('측정한 질문에 모두 리훈이 등장합니다! 이제 순위를 1위로 끌어올리는 단계예요.')

st.caption('데이터: sov_results.jsonl · 측정 갱신: python sov.py · 네이버Cue는 공개API가 없어 수기 측정')
