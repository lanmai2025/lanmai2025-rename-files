@echo off
rem 备用命令行启动方式：直接用本机 Python 运行源码
chcp 65001 >nul
cd /d "%~dp0.."
if exist "D:\python\python.exe" (
    "D:\python\python.exe" "src\main.py" %*
) else (
    python "src\main.py" %*
)
pause
