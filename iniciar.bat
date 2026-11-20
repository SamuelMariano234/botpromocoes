@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente virtual nao encontrado. Crie-o e instale requirements.txt conforme README.md.
  pause
  exit /b 1
)
if not exist ".env" (
  echo Arquivo .env nao encontrado. Copie .env.example para .env e preencha as credenciais.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
  echo O bot terminou com erro. Leia a mensagem acima e o README.md.
  pause
  exit /b 1
)
endlocal
