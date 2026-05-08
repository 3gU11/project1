$env:VITE_API_BASE_URL = '/api/v1'
$env:VITE_PROXY_TARGET = 'http://127.0.0.1:8000'
Set-Location 'D:\CURSORpj\V7STD1.0\frontend'
& 'C:\Program Files\nodejs\npm.cmd' run dev -- --host 0.0.0.0 --port 3000
