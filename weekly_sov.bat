@echo off
rem ASCII-only batch (Korean in .bat breaks cmd parsing on KR Windows -> weekly failures).
chcp 65001 >nul
cd /d C:\Users\rihoo\projects\rihoon-keywords

> sov_run.log echo ===== Rihoon SOV weekly run %date% %time% =====

echo [1/5] sov.py measure >> sov_run.log 2>&1
python sov.py >> sov_run.log 2>&1
if errorlevel 1 ( echo [ERROR] sov.py failed >> sov_run.log & exit /b 11 )

echo [2/5] build_web_data >> sov_run.log 2>&1
python build_web_data.py >> sov_run.log 2>&1
if errorlevel 1 ( echo [ERROR] build_web_data failed >> sov_run.log & exit /b 12 )

echo [3/5] build_sources >> sov_run.log 2>&1
python build_sources.py >> sov_run.log 2>&1
if errorlevel 1 ( echo [ERROR] build_sources failed >> sov_run.log & exit /b 13 )

echo [4/5] build_answers >> sov_run.log 2>&1
python build_answers.py >> sov_run.log 2>&1
if errorlevel 1 ( echo [ERROR] build_answers failed >> sov_run.log & exit /b 14 )

echo [5/5] git commit/push >> sov_run.log 2>&1
git add docs/data.json docs/sources.json docs/answers >> sov_run.log 2>&1
rem skip commit if nothing staged (avoid false exit 1 on no-change)
git diff --cached --quiet
if not errorlevel 1 (
  echo [INFO] no changes - skip commit/push >> sov_run.log 2>&1
  goto done
)
git commit -m "weekly SOV auto-measure %date%" >> sov_run.log 2>&1
if errorlevel 1 ( echo [ERROR] git commit failed >> sov_run.log & exit /b 15 )
git push >> sov_run.log 2>&1
if errorlevel 1 ( echo [ERROR] git push failed >> sov_run.log & exit /b 16 )

:done
echo ===== done %date% %time% ===== >> sov_run.log 2>&1
exit /b 0
