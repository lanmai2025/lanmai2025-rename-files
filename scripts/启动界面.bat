@echo off
rem 备用启动方式：直接用本机 Python 运行源码，不经过 exe
cd /d "%~dp0.."
if exist "D:\python\pythonw.exe" (
    start "" "D:\python\pythonw.exe" "src\main.py"
) else (
    start "" "pythonw.exe" "src\main.py"
)
