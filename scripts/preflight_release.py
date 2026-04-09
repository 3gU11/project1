import argparse
import os
import sys
import urllib.error
import urllib.request


def check_path(path: str, kind: str) -> tuple[bool, str]:
    if kind == "file":
        ok = os.path.isfile(path)
    else:
        ok = os.path.isdir(path)
    return ok, f"{'OK' if ok else 'MISS'} {kind}: {path}"


def check_health(url: str, timeout: float) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            ok = resp.status == 200
            return ok, f"{'OK' if ok else 'FAIL'} health: {url} (HTTP {resp.status})"
    except urllib.error.URLError as e:
        return False, f"FAIL health: {url} ({e})"
    except Exception as e:  # noqa: BLE001
        return False, f"FAIL health: {url} ({e})"


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight checks for V7ex release")
    parser.add_argument("--root", default=".")
    parser.add_argument("--health-url", default="http://127.0.0.1:8000/health")
    parser.add_argument("--health-timeout", type=float, default=2.0)
    parser.add_argument("--skip-health", action="store_true")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    checks: list[tuple[bool, str]] = []
    checks.append(check_path(os.path.join(root, ".env"), "file"))
    checks.append(check_path(os.path.join(root, "frontend", ".env.production"), "file"))
    checks.append(check_path(os.path.join(root, "frontend", "dist"), "dir"))
    checks.append(check_path(os.path.join(root, "frontend", "dist", "index.html"), "file"))

    if args.skip_health:
        checks.append((True, "SKIP health check"))
    else:
        checks.append(check_health(args.health_url, args.health_timeout))

    failed = 0
    for ok, msg in checks:
        print(msg)
        if not ok:
            failed += 1

    if failed == 0:
        print("Preflight PASS")
        return 0
    print(f"Preflight FAIL ({failed} item(s))")
    return 1


if __name__ == "__main__":
    sys.exit(main())
