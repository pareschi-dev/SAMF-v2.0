"""Altera a senha de um usuário SAMF sem exibir a senha no terminal."""

from __future__ import annotations

import getpass
import sys

from werkzeug.security import generate_password_hash

from database import get_connection


def main() -> int:
    usuario = (sys.argv[1] if len(sys.argv) > 1 else input("Usuário SAMF [sra]: ")).strip().lower() or "sra"
    senha = getpass.getpass("Nova senha: ")
    confirmacao = getpass.getpass("Repita a nova senha: ")
    if senha != confirmacao:
        raise SystemExit("As senhas não conferem.")
    if len(senha) < 8:
        raise SystemExit("A senha precisa ter pelo menos 8 caracteres.")

    connection = get_connection()
    try:
        cursor = connection.execute(
            "UPDATE usuarios SET senha_hash = ?, atualizado_em = CURRENT_TIMESTAMP WHERE usuario = ?",
            (generate_password_hash(senha), usuario),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            raise SystemExit(f"Usuário não encontrado: {usuario}")
        connection.commit()
    finally:
        connection.close()
    print(f"Senha do usuário {usuario} alterada com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
