@echo off
cd /d "%~dp0"
title Build RETWEAKS EXE
where py >nul 2>&1 && (py build.py) || (python build.py)
pause
