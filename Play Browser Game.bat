@echo off
cd /d "%~dp0"
python tools\serve_web.py
if errorlevel 1 pause
