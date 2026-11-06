@echo off
chcp 65001 > NUL
set PYTHONUTF8=1
cd /d "%~dp0"
title 양식 D 가상 CoA 생성 v2 - 호주 정제사 LIMS CoA

set PY=python
where python > NUL 2>&1 || set PY=py
where %PY% > NUL 2>&1 || goto nopython

%PY% -c "import reportlab, PIL, pypdfium2" > NUL 2>&1 || (
  echo 처음 실행이라 필요한 패키지 reportlab, pillow, pypdfium2 를 설치합니다...
  %PY% -m pip install --quiet reportlab pillow pypdfium2
)

set MAT=1
set /p MAT=원자재를 고르세요. 1 = 탄산리튬, 2 = 수산화리튬 [그냥 Enter = 1]: 
set MATERIAL=li2co3
if "%MAT%"=="2" set MATERIAL=lioh
set COUNT=30
set /p COUNT=몇 장 만들까요? [그냥 Enter = 30장]: 
set NORMAL=0.6
set /p NORMAL=정상 문서 비율 0~1 [그냥 Enter = 0.6]: 
%PY% gen_D.py --material %MATERIAL% --count %COUNT% --normal-rate %NORMAL%
echo.
echo 결과는 output_D_%MATERIAL% 폴더에 있습니다.
start "" "%~dp0output_D_%MATERIAL%"
pause
exit /b

:nopython
echo [오류] 파이썬이 설치되어 있지 않습니다. https://www.python.org 에서 설치한 뒤 다시 실행하세요.
echo        설치할 때 Add python.exe to PATH 를 꼭 체크하세요.
pause
