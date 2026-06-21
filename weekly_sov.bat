@echo off
chcp 65001 >nul
cd /d C:\Users\rihoo\projects\rihoon-keywords
echo ===== 리훈 SOV 주간 자동측정 %date% %time% =====
echo [1/5] AI 엔진 측정 (Gemini/Perplexity/Claude/ChatGPT)
python sov.py
echo [2/5] 대시보드 데이터 생성
python build_web_data.py
echo [3/5] AI 출처 수집
python build_sources.py
echo [4/5] AI별 답변 전문·인용 페이지 저장
python build_answers.py
echo [5/5] 깃 푸시 (대시보드 자동 갱신)
git add docs/data.json docs/sources.json docs/answers
git commit -m "주간 SOV 자동측정 %date%"
git push
echo ===== 완료. 대시보드 1~2분 후 갱신 =====
