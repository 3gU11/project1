$env:GO_SANDBOX_URL = 'http://127.0.0.1:3001'
Set-Location 'D:\CURSORpj\V7STD1.0'
& 'D:\CURSORpj\V7STD1.0\.venv\Scripts\python.exe' -m uvicorn api.main:app --host 0.0.0.0 --port 8000
