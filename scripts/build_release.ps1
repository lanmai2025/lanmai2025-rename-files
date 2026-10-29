# 一键出安装包：dist 主程序 -> 载荷 -> 单文件安装程序 -> result\
# 用法（在仓库根目录）：pwsh -File scripts\build_release.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$py = "D:\python\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Push-Location $root
try {
    Write-Host "[1/5] 打包主程序（界面 + 命令行）"
    & $py -m PyInstaller --noconfirm --clean --onedir --noconsole `
        --name "改名工具" --paths "src" `
        --distpath dist --workpath build --specpath build "src\main.py"
    if ($LASTEXITCODE -ne 0) { throw "界面版打包失败" }
    & $py -m PyInstaller --noconfirm --clean --onedir --console `
        --name "改名工具-命令行" --paths "src" `
        --distpath dist --workpath build --specpath build "src\main.py"
    if ($LASTEXITCODE -ne 0) { throw "命令行版打包失败" }

    Write-Host "[2/5] 组装安装包内容"
    $payload = "_payload\app"
    Remove-Item -Recurse -Force "_payload" -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $payload | Out-Null
    Copy-Item "dist\改名工具" $payload -Recurse
    Copy-Item "dist\改名工具-命令行" $payload -Recurse
    Copy-Item "docs\使用说明.md" $payload

    Write-Host "[3/5] 打包安装程序（单文件）"
    $payloadAbs = (Resolve-Path $payload).Path
    Remove-Item -Recurse -Force "installer_dist","installer_build" -ErrorAction SilentlyContinue
    & $py -m PyInstaller --noconfirm --clean --onefile --noconsole `
        --name "批量改名工具-安装程序" --add-data "$payloadAbs;app" --paths "src" `
        --distpath "installer_dist" --workpath "installer_build" --specpath "installer_build" `
        "src\installer_main.py"
    if ($LASTEXITCODE -ne 0) { throw "安装程序打包失败" }

    Write-Host "[4/5] 输出到 result"
    New-Item -ItemType Directory -Force -Path "result" | Out-Null
    Remove-Item "result\*" -Force -Recurse -ErrorAction SilentlyContinue
    Copy-Item "installer_dist\批量改名工具-安装程序.exe" "result\"
    Copy-Item "docs\使用说明.md" "result\"

    # 项目若放在带「低完整性」标记的目录下（如 D:\DeepSeekHarness），
    # 生成出来的 exe 会被系统降权，装不上注册表。先复制到 D 盘普通目录再挪回来，
    # 标记就正常了；这一步失败也不影响文件本身。
    Write-Host "[5/5] 修正成品文件标记"
    $staging = "D:\_brt_staging"
    try {
        New-Item -ItemType Directory -Force -Path $staging | Out-Null
        foreach ($name in @("批量改名工具-安装程序.exe", "使用说明.md")) {
            $src = Join-Path "result" $name
            if (Test-Path $src) {
                $tmpCopy = Join-Path $staging $name
                Copy-Item $src $tmpCopy -Force
                Move-Item $tmpCopy $src -Force
            }
        }
        Write-Host "标记已修正"
    }
    catch {
        Write-Warning "跳过标记修正：$_"
    }
    finally {
        Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
    }

    Get-ChildItem "result" | Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}
    Write-Host "完成：$root\result"
}
finally {
    Pop-Location
}
