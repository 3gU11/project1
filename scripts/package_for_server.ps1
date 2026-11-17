# Package the current workspace for a first-time deployment on another Windows host.
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\package_for_server.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\package_for_server.ps1 -Output D:\v8-deploy.zip -WithEnv -WithData
param(
  [string]$Output = "",
  [switch]$WithEnv,      # include .env (contains secrets; only for trusted transfer)
  [switch]$WithData,     # include data/ (contract attachments, uploads)
  [switch]$SkipBuild     # skip frontend build (use existing dist)
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Output)) {
  $stamp = Get-Date -Format 'yyyyMMdd-HHmm'
  $Output = Join-Path $repoRoot ("v8-server-" + $stamp + ".zip")
}

Write-Output "[1/4] Checking build artifacts ..."
$pcDist = Join-Path $repoRoot 'frontend\dist\index.html'
$mbDist = Join-Path $repoRoot 'frontend-mobile\dist\index.html'
if (-not $SkipBuild) {
  if (-not (Test-Path $pcDist) -or -not (Test-Path $mbDist)) {
    Write-Output "      dist not found, building frontend + frontend-mobile (needs Node.js) ..."
    Push-Location (Join-Path $repoRoot 'frontend')
    npm ci; npm run build
    Pop-Location
    Push-Location (Join-Path $repoRoot 'frontend-mobile')
    npm ci; npm run build
    Pop-Location
  } else {
    Write-Output "      dist exists. Use -SkipBuild to suppress this check, or delete dist to force rebuild."
    Write-Output "      NOTE: dist must match current source. Rebuild if source changed since last build."
  }
}
if (-not (Test-Path $pcDist)) { throw "frontend/dist/index.html missing. Build failed." }

Write-Output "[2/4] Staging files ..."
$stage = Join-Path $env:TEMP ("v8-stage-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $stage -Force | Out-Null

$excludeDirs = @(
  'node_modules', '.git', '__pycache__', '.venv', '.venv312', 'venv',
  'backups', 'artifacts', 'test-results', 'tmp-playwright-output',
  '.gocache', '.gomodcache', '.tmp-tsc', '.tmp-vitest', '.tmp-smoke', '.tmp-e2e', '.tmp-wf',
  '.idea', '.vscode'
)
if (-not $WithData) { $excludeDirs += 'data' }

$robocopyArgs = @($repoRoot, $stage, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/R:1', '/W:1',
  '/XD') + $excludeDirs + @(
  '/XF', '*.log', '*.pyc', '*.pyo', '.fullstack.pids.json', '*.tmp'
)
# robocopy exit codes 0-7 mean success
& robocopy @robocopyArgs | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }

# .env handling: never ship the dev .env unless explicitly requested
$envFile = Join-Path $stage '.env'
if (Test-Path $envFile) {
  if (-not $WithEnv) {
    Remove-Item $envFile -Force
    Write-Output "      .env excluded (use -WithEnv to include, or create it on the server from .env.example)"
  }
}

# Drop dev-only leftovers that must not run in production
foreach ($junk in @('frontend\web-launcher.out.log', 'api-launcher.out.log', 'run_fullstack.start.log')) {
  $p = Join-Path $stage $junk
  if (Test-Path $p) { Remove-Item $p -Force }
}

$total = (Get-ChildItem $stage -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Output ("      staged {0:N0} files, {1:N1} MB" -f (Get-ChildItem $stage -Recurse -File).Count, ($total / 1MB))

Write-Output "[3/4] Compressing ..."
if (Test-Path $Output) { Remove-Item $Output -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $Output -CompressionLevel Optimal
Remove-Item $stage -Recurse -Force

Write-Output "[4/4] Done."
Write-Output ("Package: {0}" -f $Output)
Write-Output ("Size:    {0:N1} MB" -f ((Get-Item $Output).Length / 1MB))
Write-Output ""
Write-Output "Next steps on the server:"
Write-Output "  1. Expand the zip to e.g. D:\v8"
Write-Output "  2. python -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
Write-Output "  3. Copy .env.example to .env and fill MYSQL_*, DB_*, V8_JWT_SECRET, GO_INTERNAL_TOKEN"
Write-Output "  4. Set CLOUD_SYNC_ENABLED=false to avoid competing with the running host"
Write-Output "  5. powershell -ExecutionPolicy Bypass -File .\run_fullstack.ps1 -PythonExe .venv\Scripts\python.exe"
