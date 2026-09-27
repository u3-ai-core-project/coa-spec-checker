@echo off
cd /d "%~dp0"
title Virtual CoA Generator

if not exist "generate_coa.py" goto NOFILES
if not exist "CoA_Form.docx" goto NOFILES

rem ---- 파이썬 찾기: py 런처 먼저, 없으면 python ----
set "PY="
py --version >nul 2>nul
if not errorlevel 1 set "PY=py"
if defined PY goto HAVEPY
python --version >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto HAVEPY
goto NOPYTHON

:HAVEPY
echo.
echo  ==============================================
echo    가상 CoA 생성기
echo  ==============================================
echo.
echo  [1/3] 필요한 도구를 확인하는 중입니다...
%PY% -c "import docx" >nul 2>nul
if errorlevel 1 %PY% -m pip install python-docx
%PY% -c "import docx" >nul 2>nul
if errorlevel 1 goto PIPFAIL

echo.
set "COUNT=100"
set /p "COUNT= [2/3] 몇 장 만들까요? 숫자를 쓰고 Enter. 그냥 Enter를 누르면 100장: "
set "PDF=N"
set /p "PDF=       PDF 파일도 만들까요? Y 또는 N. 그냥 Enter를 누르면 N: "

echo.
echo  [3/3] 만드는 중입니다. 잠시만 기다려 주세요...
echo.
if /i "%PDF%"=="Y" goto WITHPDF
%PY% generate_coa.py --count %COUNT%
goto DONE

:WITHPDF
%PY% -c "import docx2pdf" >nul 2>nul
if errorlevel 1 %PY% -m pip install docx2pdf
%PY% generate_coa.py --count %COUNT% --pdf
goto DONE

:DONE
if errorlevel 1 goto RUNFAIL
echo.
echo  완료! 결과가 들어 있는 output 폴더를 엽니다.
start "" "%~dp0output"
echo.
pause
exit /b

:RUNFAIL
echo.
echo  [오류] 실행 중 문제가 생겼습니다. 이 창을 캡처해서 Claude에게 보여 주세요.
echo.
pause
exit /b

:NOFILES
echo.
echo  [오류] generate_coa.py 와 CoA_Form.docx 가 이 파일과 같은 폴더에 있어야 합니다.
echo         압축 파일을 먼저 압축 풀기 한 다음, 풀린 폴더 안에서 다시 실행하세요.
echo.
pause
exit /b

:NOPYTHON
echo.
echo  [안내] 이 컴퓨터에 파이썬이 설치되어 있지 않습니다.
echo    1. 곧 열리는 python.org 페이지에서 Download Python 버튼을 눌러 설치 파일을 받으세요.
echo    2. 설치 첫 화면 맨 아래 "Add python.exe to PATH" 에 꼭 체크한 뒤 Install Now 를 누르세요.
echo    3. 설치가 끝나면 이 파일을 다시 더블클릭하세요.
start "" "https://www.python.org/downloads/"
echo.
pause
exit /b

:PIPFAIL
echo.
echo  [오류] python-docx 설치에 실패했습니다. 인터넷 연결을 확인한 뒤 다시 실행하세요.
echo.
pause
exit /b
