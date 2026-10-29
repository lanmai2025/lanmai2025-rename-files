# 只打绿色版：dist\改名工具\（界面） + dist\改名工具-命令行\（命令行）
# 用法（在仓库根目录）：pwsh -File scripts\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$py = "D:\python\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Push-Location $root
try {
    & $py -m PyInstaller --noconfirm --clean --onedir --noconsole `
        --name "改名工具" --paths "src" `
        --distpath dist --workpath build --specpath build "src\main.py"
    if ($LASTEXITCODE -ne 0) { throw "界面版打包失败" }
    & $py -m PyInstaller --noconfirm --clean --onedir --console `
        --name "改名工具-命令行" --paths "src" `
        --distpath dist --workpath build --specpath build "src\main.py"
    if ($LASTEXITCODE -ne 0) { throw "命令行版打包失败" }
    Get-ChildItem dist | Select-Object Name
}
finally {
    Pop-Location
}
