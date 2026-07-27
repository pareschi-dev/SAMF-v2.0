import sqlite3
import os

# CAMINHO ABSOLUTO FIXO - GARANTE QUE TODOS USEM O MESMO ARQUIVO
DB_PATH = r"C:\Users\nerivaldo.junior\OneDrive - Ministério da Gestão e da Inovação dos Serv. Pub\SAMF\samf.db"

def get_connection():
    """Retorna uma conexão sqlite3 com timeout para evitar travamentos."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.row_factory = sqlite3.Row
    return conn

if __name__ == "__main__":
    try:
        conn = get_connection()
        print(f"--- SUCESSO ---")
        print(f"Conectado ao arquivo correto: {DB_PATH}")
        conn.close()
    except Exception as e:
        print(f"Erro ao conectar ao SQLite: {e}")
