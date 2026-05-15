Stop-Process -Name smart-scheduling-server-go -Force -ErrorAction SilentlyContinue
Set-Location server
go build -o smart-scheduling-server-go.exe .\cmd\main.go
if ($LASTEXITCODE -eq 0) {
    $env:HTTP_ADDR = ':3001'
    Start-Process -FilePath .\smart-scheduling-server-go.exe -WorkingDirectory . -RedirectStandardOutput go-launcher.out.log -RedirectStandardError go-launcher.err.log -WindowStyle Hidden
    Write-Host "Go server rebuilt and restarted."
} else {
    Write-Host "Go build failed."
}
