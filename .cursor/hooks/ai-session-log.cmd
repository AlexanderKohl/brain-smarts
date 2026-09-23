@echo off
setlocal EnableExtensions
rem Thin Windows launcher for the portable Cursor hook writer.
rem Prefer hooks.json "python shared/skills/..." when python is on PATH.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python "%~dp0..\..\shared\skills\ai-session-log\scripts\cursor_hook_writer.py"
exit /b %ERRORLEVEL%
