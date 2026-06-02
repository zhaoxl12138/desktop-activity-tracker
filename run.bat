@echo off
cd /d "%~dp0src"
start "" pythonw -m daylens.main gui
