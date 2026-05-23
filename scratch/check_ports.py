import socket
import requests

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        try:
            s.connect(('127.0.0.1', port))
            return True
        except:
            return False

print("Port 3000 (Frontend) open:", check_port(3000))
print("Port 8000 (FastAPI Backend) open:", check_port(8000))
print("Port 3001 (Go Sandbox) open:", check_port(3001))

try:
    r = requests.get('http://127.0.0.1:8000/health', timeout=2)
    print("Backend health status:", r.status_code, r.text)
except Exception as e:
    print("Backend health failed:", e)
