import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def check_once(url: str, timeout: float) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status != 200:
                return False, f"HTTP {resp.status}: {body[:200]}"
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return False, f"invalid json: {body[:200]}"
            status = str(data.get("status", "")).lower()
            if status == "ok":
                return True, "ok"
            return False, f"unexpected payload: {data}"
    except urllib.error.URLError as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check V7ex health endpoint")
    parser.add_argument("--url", default="http://127.0.0.1:8000/health")
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--interval", type=float, default=1.5)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    retries = max(1, args.retries)
    for idx in range(1, retries + 1):
        ok, msg = check_once(args.url, args.timeout)
        if ok:
            print(f"[health] PASS ({args.url})")
            return 0
        print(f"[health] attempt {idx}/{retries} failed: {msg}")
        if idx < retries:
            time.sleep(max(0.0, args.interval))
    print(f"[health] FAIL ({args.url})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
