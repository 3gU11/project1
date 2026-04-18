param(
  [string]$OutputZip = ""
)

$ErrorActionPreference = "Stop"

function New-Timestamp {
  return (Get-Date).ToString("yyyyMMdd_HHmmss")
}

function Invoke-RoboCopy([string]$Source, [string]$Dest, [string[]]$Args) {
  New-Item -ItemType Directory -Force -Path $Dest | Out-Null
  $cmdArgs = @($Source, $Dest) + $Args
  & robocopy @cmdArgs | Out-Null
  $code = $LASTEXITCODE
  if ($code -ge 8) { throw "robocopy failed ($code): $Source -> $Dest" }
}

function Get-CommandPath([string]$Name) {
  try { return (Get-Command $Name -ErrorAction Stop).Source } catch { return $null }
}

$stamp = New-Timestamp
$v7exRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bundleRoot = Join-Path $v7exRoot "release\update_bundle"
$staging = Join-Path $PSScriptRoot ("_staging_" + $stamp)
$outZip = $OutputZip
if (!$outZip.Trim()) { $outZip = Join-Path $PSScriptRoot ("V7ex_update_bundle_" + $stamp + ".zip") }

if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
New-Item -ItemType Directory -Force -Path $staging | Out-Null

$stageBundle = Join-Path $staging "update_bundle"
Invoke-RoboCopy $bundleRoot $stageBundle @("/E", "/XD", "package")

$pkgDir = Join-Path $stageBundle "package"
$pkgBackend = Join-Path $pkgDir "backend"
$pkgFrontend = Join-Path $pkgDir "frontend-dist"
New-Item -ItemType Directory -Force -Path $pkgBackend | Out-Null
New-Item -ItemType Directory -Force -Path $pkgFrontend | Out-Null

$npm = Get-CommandPath "npm"
if (!$npm) { throw "npm not found in PATH" }
$frontendDir = Join-Path $v7exRoot "frontend"
if (!(Test-Path -LiteralPath $frontendDir)) { throw "frontend dir not found: $frontendDir" }

Push-Location $frontendDir
try {
  & $npm "install"
  if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
  & $npm "run" "build"
  if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally {
  Pop-Location
}

$distDir = Join-Path $frontendDir "dist"
if (!(Test-Path -LiteralPath $distDir)) { throw "frontend dist not found: $distDir" }
Invoke-RoboCopy $distDir $pkgFrontend @("/E")

$backendDirs = @("api", "core", "crud", "utils", "scripts")
foreach ($d in $backendDirs) {
  $src = Join-Path $v7exRoot $d
  if (Test-Path -LiteralPath $src) {
    Invoke-RoboCopy $src (Join-Path $pkgBackend $d) @("/E", "/XD", "__pycache__")
  }
}

$backendFiles = @("__init__.py", "config.py", "database.py", "run_api.py", "requirements.txt", ".env.backend.example")
foreach ($f in $backendFiles) {
  $src = Join-Path $v7exRoot $f
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $pkgBackend $f) -Force
  }
}

$manifest = @{
  build_time = (Get-Date).ToString("s")
  package = @{
    backend = "package/backend"
    frontend_dist = "package/frontend-dist"
  }
} | ConvertTo-Json -Depth 6
Set-Content -LiteralPath (Join-Path $stageBundle "manifest.json") -Value $manifest -Encoding UTF8

if (Test-Path -LiteralPath $outZip) { Remove-Item -LiteralPath $outZip -Force }
Compress-Archive -Path $stageBundle -DestinationPath $outZip -Force

Write-Host ("[build] OK: " + $outZip)

