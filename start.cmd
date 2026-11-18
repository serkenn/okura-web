@echo off
rem okura-web を起動する（http://127.0.0.1:8765/）。止めるときは Ctrl+C
cd /d "%~dp0"
".work\venvs\web\Scripts\python.exe" -I -X utf8 serve.py %*
