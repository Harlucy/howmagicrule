<#
.SYNOPSIS
  本地规则流水线：拉上游 → 策略改写 → 去重 → 转 Clash Classic → 校验 →（可选）提交推送。

.DESCRIPTION
  等价于 GitHub Actions 的 Rule-Update + Convert，但不重跑几十个外部下载步骤：
  规则新鲜度继承上游仓库（上游 CI 每 6 小时提交 rules/*.list）。
  只在本地重建派生的 clash-rule-ad.ini 与全部 YAML，然后给出改动概览。

.EXAMPLE
  pwsh scripts/run-local.ps1
  pwsh scripts/run-local.ps1 -Push -Message "rule update"
  pwsh scripts/run-local.ps1 -NoFetch -DryRun
#>
[CmdletBinding()]
param(
    [switch]$Push,
    [switch]$NoFetch,
    [switch]$DryRun,
    [string]$Message = 'Local rule update'
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Find-Tool([string[]]$Names) {
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}

function Invoke-Step {
    param([string]$Name, [string]$Preview, [scriptblock]$Action)
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    Write-Host "   $Preview" -ForegroundColor DarkGray
    if ($DryRun) { return }
    $global:LASTEXITCODE = 0
    & $Action
    if ($global:LASTEXITCODE -ne 0) { throw "$Name 失败（exit $global:LASTEXITCODE）" }
}

$python = Find-Tool @('python', 'python3')
if (-not $python) { throw '找不到 Python 3，请安装后加入 PATH。' }

$bash = Find-Tool @('bash')
if (-not $bash) {
    $bash = @('C:\Program Files\Git\bin\bash.exe', 'C:\Program Files\Git\usr\bin\bash.exe') |
        Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $bash) { throw '找不到 bash，请安装 Git for Windows（转换脚本需要它）。' }

foreach ($required in 'config/upstream-sync.json', 'scripts/sync-upstream.py', 'scripts/validate-rules.py') {
    if (-not (Test-Path $required)) { throw "缺少文件：$required（先把同步脚本与策略提交进仓库）" }
}

if ($NoFetch) {
    Write-Host "跳过 fetch，使用已抓取的 upstream/main。" -ForegroundColor Yellow
} else {
    Invoke-Step '拉取上游' 'git fetch --no-tags upstream main' { git fetch --no-tags upstream main }
}
$upstreamHead = (git log --oneline -1 refs/remotes/upstream/main 2>$null)
Write-Host "   上游版本：$upstreamHead" -ForegroundColor DarkGray

Invoke-Step '同步上游并应用本地策略' 'python scripts/sync-upstream.py --no-fetch' {
    & $python scripts/sync-upstream.py --no-fetch
}
Invoke-Step '去重规则源' 'python scripts/normalize-rules.py' {
    & $python scripts/normalize-rules.py
}
Invoke-Step '生成 Clash Classic' 'bash scripts/convert-list-to-yaml.sh' {
    & $bash --noprofile --norc scripts/convert-list-to-yaml.sh
}
Invoke-Step '同步层回归测试' 'python scripts/test-sync-upstream.py' {
    # unittest 把进度点写到 stderr，PS 5.1 会把它当成错误流；重定向到临时文件，只在失败时回显。
    $errorLog = [IO.Path]::GetTempFileName()
    $ErrorActionPreference = 'Continue'
    & $python scripts/test-sync-upstream.py 2> $errorLog
    $code = $LASTEXITCODE
    if ($code -ne 0) { Get-Content $errorLog | Out-Host }
    Remove-Item $errorLog -Force -ErrorAction SilentlyContinue
    $ErrorActionPreference = 'Continue'
    $global:LASTEXITCODE = $code
}
Invoke-Step '规则与 INI 校验' 'python scripts/validate-rules.py' {
    & $python scripts/validate-rules.py
}

Write-Host ""
Write-Host "== 改动概览 ==" -ForegroundColor Cyan
Write-Host "   工作区改动文件：$((git status --short | Measure-Object -Line).Lines)"
$stat = git diff --stat 2>$null | Select-Object -Last 1
if ($stat) { Write-Host "   $($stat.Trim())" }
$untracked = git ls-files --others --exclude-standard
if ($untracked) {
    Write-Host "   未跟踪文件："
    $untracked | ForEach-Object { Write-Host "     $_" }
}

if (-not $Push) {
    Write-Host ""
    Write-Host "已停在提交前。确认无误后加 -Push 复跑，或自行 git add/commit。" -ForegroundColor Yellow
    exit 0
}

Invoke-Step '暂存改动' 'git add rules clash-classic clash-rule*.ini config scripts .github README.md docs' {
    git add rules clash-classic 'clash-rule*.ini' config scripts .github README.md docs
}

$global:LASTEXITCODE = 0
git diff --cached --quiet
if ($global:LASTEXITCODE -eq 0) {
    Write-Host "没有需要提交的改动。" -ForegroundColor Yellow
    exit 0
}

Invoke-Step '提交' "git commit -m `"$Message`"" { git commit -m $Message }
Invoke-Step '同步远端并推送' 'git pull --rebase origin main && git push origin main' {
    git pull --rebase origin main
    if ($global:LASTEXITCODE -eq 0) { git push origin main }
}
Write-Host ""
Write-Host "完成。" -ForegroundColor Green
exit 0