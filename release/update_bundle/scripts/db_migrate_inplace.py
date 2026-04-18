import argparse
import os
import sys


def load_dotenv(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path or not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for raw in f.readlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                env[k] = v
    return env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--workdir", required=True)
    args = parser.parse_args()

    os.chdir(args.workdir)
    env_map = load_dotenv(args.env)
    for k, v in env_map.items():
        os.environ[k] = v

    from database import init_mysql_tables

    init_mysql_tables()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"db_migrate_inplace failed: {e}", file=sys.stderr)
        raise SystemExit(1)

