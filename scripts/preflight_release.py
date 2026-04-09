import argparse
import os
import shlex
import subprocess
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


def run_connectivity_check(
    root: str,
    base_url: str,
    timeout: float,
    strict: bool,
    extra_args: str,
) -> tuple[bool, str]:
    script_path = os.path.join(root, "scripts", "connectivity_e2e_runner.py")
    if not os.path.isfile(script_path):
        return False, f"MISS file: {script_path}"
    cmd = [sys.executable, script_path, "--base-url", base_url, "--timeout", str(timeout)]
    if strict:
        cmd.append("--strict")
    if extra_args.strip():
        cmd.extend(shlex.split(extra_args))
    try:
        result = subprocess.run(cmd, cwd=root, check=False, capture_output=True, text=True)
    except Exception as e:  # noqa: BLE001
        return False, f"FAIL connectivity: {e}"

    if result.returncode == 0:
        return True, "OK connectivity: closed-loop passed"
    merged = (result.stdout or "") + "\n" + (result.stderr or "")
    merged = merged.strip()
    tail = merged[-500:] if merged else ""
    return False, f"FAIL connectivity: exit={result.returncode} {tail}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight checks for V7ex release")
    parser.add_argument("--root", default=".")
    parser.add_argument("--health-url", default="http://127.0.0.1:8000/health")
    parser.add_argument("--health-timeout", type=float, default=2.0)
    parser.add_argument("--skip-health", action="store_true")
    parser.add_argument("--run-connectivity", action="store_true")
    parser.add_argument("--connectivity-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--connectivity-timeout", type=float, default=15.0)
    parser.add_argument("--connectivity-strict", action="store_true")
    parser.add_argument("--connectivity-extra-args", default="")
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

    if args.run_connectivity:
        checks.append(
            run_connectivity_check(
                root=root,
                base_url=args.connectivity_base_url,
                timeout=args.connectivity_timeout,
                strict=args.connectivity_strict,
                extra_args=args.connectivity_extra_args,
            )
        )
    else:
        checks.append((True, "SKIP connectivity check"))

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
