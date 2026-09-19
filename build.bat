@echo off
REM ============================================================
REM  Gera ControleEstoque.exe (arquivo unico, sem console)
REM  Requisitos: Python 3.10+ para Windows instalado
REM  Execute ESTE script no Windows, dentro da pasta do projeto.
REM ============================================================

echo [1/4] Criando ambiente virtual...
if not exist .venv (
    python -m venv .venv || goto :erro
)

echo [2/4] Instalando dependencias...
call .venv\Scripts\activate.bat || goto :erro
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q || goto :erro
pip install pyinstaller -q || goto :erro

echo [3/4] Limpando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist ControleEstoque.spec del ControleEstoque.spec

echo [4/4] Empacotando...
set ICONE=
if exist icone.ico set ICONE=--icon icone.ico

pyinstaller --noconfirm --onefile --windowed ^
    --name ControleEstoque ^
    %ICONE% ^
    main.py || goto :erro

echo.
echo ============================================
echo  Pronto: dist\ControleEstoque.exe
echo  Para gerar o instalador, compile instalador.iss no Inno Setup.
echo ============================================
pause
exit /b 0

:erro
echo.
echo *** Falha no build. Veja a mensagem acima. ***
pause
exit /b 1