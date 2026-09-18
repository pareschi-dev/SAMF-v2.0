from database import DB_PATH, get_connection

if __name__ == "__main__":
    try:
        conn = get_connection()
        print(f"Conectado ao SQLite com sucesso! Arquivo: {DB_PATH}")
        conn.close()
    except Exception as e:
        print(f"Erro ao conectar ao SQLite: {e}")
