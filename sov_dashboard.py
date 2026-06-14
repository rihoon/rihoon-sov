# 리훈 AEO SOV 대시보드 — 추세(지속 성장) 중심. 실행: streamlit run sov_dashboard.py
import json, os
import pandas as pd
import streamlit as st
import altair as alt

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'sov_results.jsonl')
CORE = json.load(open(os.path.join(HERE, 'sov_core.json'), encoding='utf-8'))

st.set_page_config(page_title='리훈 AEO SOV', layout='wide')
st.title('리훈 AEO · SOV 추적')
st.caption('AI가 리훈을 추천하는 비율(언급률)의 지속 성장을 추적합니다. 목표: 빨간 칸을 초록으로, 추세선을 우상향으로.')

# --- 데이터 로드 ---
rows = []
if os.path.exists(RESULTS):
    for l in open(RESULTS, encoding='utf-8'):
        try: rows.append(json.loads(l))
        except Exception: pass
df = pd.DataFrame(rows)
if df.empty:
    st.info('아직 측정 데이터가 없습니다. `python sov.py` 를 먼저 실행하세요.'); st.stop()

# 측정 성공분만(에러 제외), 같은 (date,engine,id)는 마지막 실행값 사용
meas = df[df.get('mentioned').notna()].copy() if 'mentioned' in df else pd.DataFrame()
meas = meas.drop_duplicates(subset=['date', 'engine', 'id'], keep='last')
meas['mentioned'] = meas['mentioned'].astype(bool)
meas['top1'] = meas['rank'].apply(lambda r: r == 1 if pd.notna(r) else False)

# --- 추세선 (주인공) ---
trend = meas.groupby(['date', 'engine']).agg(
    언급률=('mentioned', lambda s: round(100 * s.mean())),
    측정수=('mentioned', 'size')).reset_index()
dates = sorted(meas['date'].unique())
latest, prev = dates[-1], (dates[-2] if len(dates) > 1 else None)

# 상단 지표
cur = meas[meas['date'] == latest]
cur_rate = round(100 * cur['mentioned'].mean())
delta = None
if prev is not None:
    pv = meas[meas['date'] == prev]
    delta = cur_rate - round(100 * pv['mentioned'].mean())
c1, c2, c3, c4 = st.columns(4)
c1.metric('통합 언급률 (최신)', '%d%%' % cur_rate, ('%+d%%p' % delta) if delta is not None else '기준선')
c2.metric('1위 차지', '%d개' % int(cur['top1'].sum()))
c3.metric('완전 공백(0)', '%d개' % int((~cur.groupby('id')['mentioned'].any()).sum()))
c4.metric('측정 엔진', '%d개' % cur['engine'].nunique())

st.subheader('① 언급률 추세 — 우상향이 목표')
if len(dates) == 1:
    st.caption('오늘은 기준선(점 1개). 다음 측정부터 선이 그려지고 성장이 보입니다.')
line = alt.Chart(trend).mark_line(point=True).encode(
    x=alt.X('date:O', title='측정일'),
    y=alt.Y('언급률:Q', title='언급률(%)', scale=alt.Scale(domain=[0, 100])),
    color=alt.Color('engine:N', title='엔진'),
    tooltip=['date', 'engine', '언급률', '측정수'])
st.altair_chart(line, use_container_width=True)

# --- 히트맵 (오늘의 구멍 진단) ---
st.subheader('② 질문 × 엔진 — 빨강이 채울 자리')
kwmap = {q['id']: q['kw'] for q in CORE['questions']}
linemap = {q['id']: q['line'] for q in CORE['questions']}
cur = cur.copy()
cur['상태'] = cur.apply(lambda r: '1위' if r['top1'] else ('언급' if r['mentioned'] else '없음'), axis=1)
cur['질문'] = cur['id'].map(kwmap)
order = [kwmap[q['id']] for q in CORE['questions']]
heat = alt.Chart(cur).mark_rect(stroke='white', strokeWidth=2).encode(
    x=alt.X('engine:N', title='엔진'),
    y=alt.Y('질문:N', title='', sort=order),
    color=alt.Color('상태:N', scale=alt.Scale(domain=['1위', '언급', '없음'], range=['#2e7d32', '#f9a825', '#e0e0e0']), title='상태'),
    tooltip=['질문', 'engine', '상태', 'rank']).properties(height=380)
st.altair_chart(heat, use_container_width=True)

# --- 승리 / 구멍 리스트 ---
col_a, col_b = st.columns(2)
agg = cur.groupby(['id']).agg(언급=('mentioned', 'any'), best=('rank', 'min')).reset_index()
agg['질문'] = agg['id'].map(kwmap); agg['제품군'] = agg['id'].map(linemap)
with col_a:
    st.subheader('🟢 이기는 질문')
    win = agg[agg['언급']].sort_values('best')
    st.dataframe(win[['질문', '제품군', 'best']].rename(columns={'best': '최고순위'}), hide_index=True, use_container_width=True)
with col_b:
    st.subheader('🔴 공백 질문 (깔 자리)')
    hole = agg[~agg['언급']]
    st.dataframe(hole[['질문', '제품군']], hide_index=True, use_container_width=True)

st.caption('데이터: sov_results.jsonl · 측정: python sov.py [엔진명...] · 네이버Cue는 수기 입력 필요')
