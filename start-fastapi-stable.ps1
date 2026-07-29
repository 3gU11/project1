$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$env:GO_SANDBOX_URL = 'http://127.0.0.1:3001'
$env:UVICORN_HOST = '0.0.0.0'
$env:UVICORN_PORT = '8000'
$env:UVICORN_RELOAD = 'false'
$env:UVICORN_LOG_LEVEL = 'info'
$env:UVICORN_WORKERS = '1'

$pythonCandidates = @(
  (Join-Path $root '.venv312\Scripts\python.exe'),
  (Join-Path $root '.venv\Scripts\python.exe')
)

$python = $null
foreach ($candidate in $pythonCandidates) {
  if (Test-Path -LiteralPath $candidate) {
    $python = $candidate
    break
  }
}

if (-not $python) {
  $python = (Get-Command python.exe -ErrorAction Stop).Source
}

& $python -m uvicorn api.main:app --host $env:UVICORN_HOST --port $env:UVICORN_PORT --log-level $env:UVICORN_LOG_LEVEL
