import urllib.request
import urllib.error

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/v1/sandbox/rush-orders/166/return-to-sandbox',
    method='POST'
)

print('Sending request...')
try:
    urllib.request.urlopen(req)
    print('Response: 200 OK')
except urllib.error.HTTPError as e:
    print('Response status code:', e.code)
    print('Response body:', e.read().decode())
except Exception as e:
    print('Error:', e)
