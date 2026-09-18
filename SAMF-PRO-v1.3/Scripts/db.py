import sqlite3
import os

# Caminho do banco de dados local na pasta raiz do SAMF
# O banco será um arquivo chamado samf.db
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "samf.db")  # Unificado com database.py

def get_connection():
    """Retorna uma conexão sqlite3."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")
    # Habilita suporte a chaves estrangeiras
    conn.execute("PRAGMA foreign_keys = ON")
    # Retorna linhas como dicionários (opcional, mas ajuda no backend)
    conn.row_factory = sqlite3.Row
    return conn

if __name__ == "__main__":
    try:
        conn = get_connection()
        print(f"Conectado ao SQLite com sucesso! Arquivo: {DB_PATH}")
        conn.close()
    except Exception as e:
        print(f"Erro ao conectar ao SQLite: {e}")
