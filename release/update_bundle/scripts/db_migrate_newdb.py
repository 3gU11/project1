import argparse
import os
import sys
from datetime import datetime

from sqlalchemy import create_engine, text


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


def q_ident(name: str) -> str:
    return "`" + name.replace("`", "") + "`"


def get_conn_parts(env_map: dict[str, str]) -> tuple[str, int, str, str, str]:
    host = (env_map.get("MYSQL_HOST") or os.environ.get("MYSQL_HOST") or "localhost").strip()
    port = int((env_map.get("MYSQL_PORT") or os.environ.get("MYSQL_PORT") or "3306").strip())
    user = (env_map.get("MYSQL_USER") or os.environ.get("MYSQL_USER") or "root").strip()
    password = (env_map.get("MYSQL_PASSWORD") or os.environ.get("MYSQL_PASSWORD") or "").strip()
    db = (env_map.get("MYSQL_DB") or os.environ.get("MYSQL_DB") or "rjfinshed").strip()
    return host, port, user, password, db


def make_url(host: str, port: int, user: str, password: str, db: str | None) -> str:
    pwd = password.replace("@", "%40")
    base = f"mysql+pymysql://{user}:{pwd}@{host}:{port}"
    return base + (f"/{db}" if db else "/")


def db_exists(conn, db: str) -> bool:
    row = conn.execute(
        text("SELECT COUNT(*) AS c FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=:db"),
        {"db": db},
    ).fetchone()
    return int(row[0]) > 0


def list_tables(conn, db: str) -> list[str]:
    rows = conn.execute(
        text("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=:db"),
        {"db": db},
    ).fetchall()
    return [str(r[0]) for r in rows]


def list_columns(conn, db: str, table: str) -> list[str]:
    rows = conn.execute(text(f"SHOW COLUMNS FROM {q_ident(db)}.{q_ident(table)}")).fetchall()
    return [str(r[0]) for r in rows]


def copy_table(conn, old_db: str, new_db: str, table: str) -> None:
    old_cols = list_columns(conn, old_db, table)
    new_cols = list_columns(conn, new_db, table)
    common = [c for c in new_cols if c in old_cols]
    if not common:
        return
    cols_sql = ", ".join(q_ident(c) for c in common)
    conn.execute(text(f"TRUNCATE TABLE {q_ident(new_db)}.{q_ident(table)}"))
    conn.execute(
        text(
            f"INSERT INTO {q_ident(new_db)}.{q_ident(table)} ({cols_sql}) "
            f"SELECT {cols_sql} FROM {q_ident(old_db)}.{q_ident(table)}"
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--target-db", default="")
    args = parser.parse_args()

    os.chdir(args.workdir)
    env_map = load_dotenv(args.env)
    for k, v in env_map.items():
        os.environ[k] = v

    host, port, user, password, old_db = get_conn_parts(env_map)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_db = (args.target_db or "").strip() or f"{old_db}_new_{stamp}"

    server_engine = create_engine(make_url(host, port, user, password, None), pool_pre_ping=True)
    with server_engine.begin() as conn:
        if db_exists(conn, new_db):
            raise RuntimeError(f"target db already exists: {new_db}")
        conn.execute(text(f"CREATE DATABASE {q_ident(new_db)} DEFAULT CHARACTER SET utf8mb4"))

    os.environ["MYSQL_DB"] = new_db
    import importlib
    import config as cfg
    import database as db

    importlib.reload(cfg)
    importlib.reload(db)
    db.init_mysql_tables()

    engine = create_engine(make_url(host, port, user, password, None), pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        old_tables = set(list_tables(conn, old_db))
        new_tables = list_tables(conn, new_db)
        for t in new_tables:
            if t in old_tables:
                copy_table(conn, old_db, new_db, t)
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))

    print(new_db)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"db_migrate_newdb failed: {e}", file=sys.stderr)
        raise SystemExit(1)

