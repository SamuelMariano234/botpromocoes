@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente virtual nao encontrado. Siga a instalacao do README.md.
  pause
  exit /b 1
)
if not exist ".env" (
  echo Arquivo .env nao encontrado.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" collector.py
if errorlevel 1 (
  echo O coletor terminou com erro. Consulte a mensagem acima.
  pause
  exit /b 1
)
endlocal
