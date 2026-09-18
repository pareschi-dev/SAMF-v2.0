"""Cria o banco PostgreSQL do SAMF sem executar comandos destrutivos."""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import psycopg
from dotenv import load_dotenv

from database import BASE_DIR

load_dotenv(BASE_DIR / ".env")


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    admin_url = os.getenv("POSTGRES_ADMIN_URL")
    if not database_url or not admin_url:
        raise SystemExit("Configure DATABASE_URL e POSTGRES_ADMIN_URL no arquivo .env.")
    target = urlsplit(database_url)
    if not target.path or target.path == "/":
        raise SystemExit("DATABASE_URL precisa informar o banco de destino, por exemplo /samf.")
    database_name = target.path.lstrip("/")
    with psycopg.connect(admin_url, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)
        ).fetchone()
        if exists:
            print(f"Banco '{database_name}' já existe; nenhum comando destrutivo foi executado.")
            return 0
        connection.execute(f'CREATE DATABASE "{database_name.replace(chr(34), chr(34) * 2)}"')
    print(f"Banco '{database_name}' criado com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
