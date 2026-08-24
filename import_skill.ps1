# ════════════════════════════════════════════
# lxmusic-batch-downloader 一键导入脚本 (PowerShell)
# 适用平台: Windows
# 用法: 双击运行此文件，或
#       .\import_skill.ps1
# ════════════════════════════════════════════

$ErrorActionPreference = "Stop"

# ── 来源目录（本脚本所在目录）──
$this_dir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# ── 目标目录：尝试常见路径 ──
$possible_destinations = @(
    "$env:USERPROFILE\.agents\skills\lxmusic-batch-downloader",
    "C:\Users\$env:USERNAME\.agents\skills\lxmusic-batch-downloader"
)

$dest = ""
foreach ($candidate in $possible_destinations) {
    if (Test-Path $candidate -PathType Container) {
        $dest = $candidate
        break
    }
}

if (-not $dest) {
    Write-Host "`n✗ 未找到目标目录！" -ForegroundColor Red
    Write-Host "请手动创建并粘贴以下路径：" -ForegroundColor Yellow
    Write-Host "   $env:USERPROFILE\.agents\skills\lxmusic-batch-downloader" -ForegroundColor Cyan
    Write-Host "`n然后再次运行此脚本，传入参数 --force <完整路径>" -ForegroundColor Yellow
    return
}

Write-Host "================================================" -ForegroundColor Green
Write-Host "🎵 洛雪音乐批量下载器 — 一键导入" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host " 来源: $($this_dir)" -ForegroundColor White
Write-Host " 目标: $dest" -ForegroundColor White
Write-Host ""

# ── 检查源目录是否有核心文件 ──
$core_files = @("SKILL.md", "lxmusic_batch_downloader.py")
$missing = @()
foreach ($f in $core_files) {
    if (-not (Test-Path (Join-Path $this_dir $f))) {
        $missing += $f
    }
}

if ($missing.Count -gt 0) {
    Write-Host "⚠️  缺少核心文件: $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host "   请确保所有文件都在同一目录下。" -ForegroundColor Yellow
    return
}

# ── 执行复制 ──
try {
    # 如果目标已存在旧版本，备份后覆盖
    $existing_items = Get-ChildItem -Path $dest -ErrorAction SilentlyContinue
    if ($existing_items.Count -gt 0) {
        $backup_name = "backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        $backup_path = Join-Path (Split-Path $dest -Parent) "${dest}_old_$backup_name"
        Copy-Item -Path $dest -Destination $backup_path -Recurse -Force
        Write-Host "✓ 已备份旧版到: $backup_path" -ForegroundColor Yellow
    }

    # 清空目标目录再写入
    Remove-Item -Path $dest\* -Recurse -Force -ErrorAction SilentlyContinue

    # 复制全部文件
    Copy-Item -Path "$this_dir\*" -Destination $dest -Recurse -Force

    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Write- Host "✅ 导入成功！" -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "  目录内容:" -ForegroundColor White
    Get-ChildItem -Path $dest | ForEach-Object {
        Write-Host "    $( ('-' * 54)[0..($_.Name.Length+2)] -join '' )" -NoNewline
        Write-Host ("{0,6}" -f $_.Length) " bytes" -ForegroundColor Gray
        Write-Host "    $($_.Name)" -ForegroundColor Cyan
    }
    Write-Host ""
    Write-Host "📖 请先阅读: $dest\README.md" -ForegroundColor Yellow
    Write-Host "🧪 测试命令: cd `"$dest`" && python lxmusic_batch_downloader.py --test" -ForegroundColor Yellow
} catch {
    Write-Host "`n✗ 导入失败: $_" -ForegroundColor Red
    Write-Host "请以管理员身份运行 PowerShell 后重试。" -ForegroundColor Yellow
}
