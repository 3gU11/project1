import requests

try:
    resp = requests.get("http://127.0.0.1:8000/api/v1/sandbox/model-types")
    print("Status code:", resp.status_code)
    data = resp.json()
    model_types = data.get("model_types", [])
    for m in model_types:
        if "FT" in m.get("model_type", ""):
            print(m)
except Exception as e:
    print("Error calling endpoint:", e)
