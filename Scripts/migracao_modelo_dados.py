import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from backup_recuperacao import criar_backup

ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "samf.db"
CONFIG_PATH = ROOT_DIR / "Configuracoes" / "samf_config.json"


def backup_db() -> Path:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Banco não encontrado em {DB_PATH}")

    criar_backup(motivo='migracao_banco', versao='v2.0.0', raiz=ROOT_DIR, db_path=DB_PATH, destino=ROOT_DIR / 'Backups')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = ROOT_DIR / f"samf_backup_{timestamp}.db"
    shutil.copy2(DB_PATH, backup_path)
    print(f"Backup criado: {backup_path}")
    return backup_path


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone() is not None


def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(col[1] == column_name for col in columns)


def add_column_if_missing(conn: sqlite3.Connection, table_name: str, column_name: str, column_definition: str) -> None:
    if not column_exists(conn, table_name, column_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def create_table_if_missing(conn: sqlite3.Connection, sql: str) -> None:
    conn.execute(sql)


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_faturas_hash_unique ON faturas(hash_arquivo)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_faturas_status ON faturas(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_faturas_classificacao ON faturas(classificacao)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_faturas_competencia ON faturas(competencia)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_faturas_fornecedor ON faturas(fornecedor)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rateios_fatura ON rateios(fatura_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rateios_orgao ON rateios(orgao_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_divergencias_fatura ON divergencias(fatura_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lancamentos_fatura ON lancamentos_planilha(fatura_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_fatura ON logs_processamento(fatura_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_tabela ON auditoria(tabela_origem, registro_id)")


def ensure_legacy_columns(conn: sqlite3.Connection) -> None:
    add_column_if_missing(conn, "orgaos", "sigla", "TEXT")
    add_column_if_missing(conn, "orgaos", "tipo", "TEXT")
    add_column_if_missing(conn, "orgaos", "codigo", "TEXT")
    add_column_if_missing(conn, "orgaos", "ativo", "INTEGER NOT NULL DEFAULT 1")
    add_column_if_missing(conn, "orgaos", "atualizado_em", "TEXT")

    add_column_if_missing(conn, "servicos", "categoria", "TEXT")
    add_column_if_missing(conn, "servicos", "descricao", "TEXT")
    add_column_if_missing(conn, "servicos", "ativo", "INTEGER NOT NULL DEFAULT 1")
    add_column_if_missing(conn, "servicos", "atualizado_em", "TEXT")

    add_column_if_missing(conn, "faturas", "nome_arquivo", "TEXT")
    add_column_if_missing(conn, "faturas", "caminho_original", "TEXT")
    add_column_if_missing(conn, "faturas", "caminho_atual", "TEXT")
    add_column_if_missing(conn, "faturas", "fornecedor", "TEXT")
    add_column_if_missing(conn, "faturas", "cnpj", "TEXT")
    add_column_if_missing(conn, "faturas", "numero_fatura", "TEXT")
    add_column_if_missing(conn, "faturas", "servico", "TEXT")
    add_column_if_missing(conn, "faturas", "descricao_extraida", "TEXT")
    add_column_if_missing(conn, "faturas", "competencia", "TEXT")
    add_column_if_missing(conn, "faturas", "data_emissao", "TEXT")
    add_column_if_missing(conn, "faturas", "endereco", "TEXT")
    add_column_if_missing(conn, "faturas", "unidade", "TEXT")
    add_column_if_missing(conn, "faturas", "orgao_beneficiario", "TEXT")
    add_column_if_missing(conn, "faturas", "valor_bruto", "REAL")
    add_column_if_missing(conn, "faturas", "descontos", "REAL")
    add_column_if_missing(conn, "faturas", "juros", "REAL")
    add_column_if_missing(conn, "faturas", "multas", "REAL")
    add_column_if_missing(conn, "faturas", "impostos", "REAL")
    add_column_if_missing(conn, "faturas", "valor_final", "REAL")
    add_column_if_missing(conn, "faturas", "valor_base", "REAL")
    add_column_if_missing(conn, "faturas", "classificacao", "TEXT")
    add_column_if_missing(conn, "faturas", "confianca_extracao", "REAL")
    add_column_if_missing(conn, "faturas", "confianca_classificacao", "REAL")
    add_column_if_missing(conn, "faturas", "motivo_revisao", "TEXT")
    add_column_if_missing(conn, "faturas", "criado_por", "TEXT")
    add_column_if_missing(conn, "faturas", "atualizado_por", "TEXT")

    add_column_if_missing(conn, "rateios_calculados", "tipo_rateio", "TEXT")
    add_column_if_missing(conn, "rateios_calculados", "status", "TEXT")
    add_column_if_missing(conn, "rateios_calculados", "atualizado_em", "TEXT")

    add_column_if_missing(conn, "logs_processamento", "nivel", "TEXT")
    add_column_if_missing(conn, "logs_processamento", "contexto", "TEXT")
    add_column_if_missing(conn, "logs_processamento", "payload", "TEXT")


def ensure_tables(conn: sqlite3.Connection) -> None:
    create_table_if_missing(
        conn,
        """
        CREATE TABLE IF NOT EXISTS regras_classificacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            servico_id INTEGER,
            fornecedor TEXT,
            complemento TEXT,
            orgao_id INTEGER,
            tipo TEXT CHECK(tipo IN ('compartilhado','exclusivo','revisao')) NOT NULL,
            prioridade INTEGER NOT NULL DEFAULT 100,
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(servico_id) REFERENCES servicos(id),
            FOREIGN KEY(orgao_id) REFERENCES orgaos(id)
        )
        """,
    )

    create_table_if_missing(
        conn,
        """
        CREATE TABLE IF NOT EXISTS regras_rateio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            servico_id INTEGER NOT NULL,
            orgao_id INTEGER,
            percentual REAL,
            valor_fixo REAL,
            criterio TEXT,
            tipo_rateio TEXT CHECK(tipo_rateio IN ('compartilhado','exclusivo')) NOT NULL,
            prioridade INTEGER NOT NULL DEFAULT 100,
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(servico_id) REFERENCES servicos(id),
            FOREIGN KEY(orgao_id) REFERENCES orgaos(id)
        )
        """,
    )

    create_table_if_missing(
        conn,
        """
        CREATE TABLE IF NOT EXISTS unidades_beneficiarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT CHECK(tipo IN ('unidade','beneficiario','endereco')) NOT NULL,
            orgao_id INTEGER,
            endereco TEXT,
            codigo TEXT,
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(orgao_id) REFERENCES orgaos(id)
        )
        """,
    )

    create_table_if_missing(
        conn,
        """
        CREATE TABLE IF NOT EXISTS rateios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fatura_id INTEGER NOT NULL,
            orgao_id INTEGER,
            percentual REAL,
            valor_rateio REAL NOT NULL,
            tipo_rateio TEXT CHECK(tipo_rateio IN ('compartilhado','exclusivo')) DEFAULT 'compartilhado',
            status TEXT CHECK(status IN ('calculado','lançado','revisao')) DEFAULT 'calculado',
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(fatura_id) REFERENCES faturas(id) ON DELETE CASCADE,
            FOREIGN KEY(orgao_id) REFERENCES orgaos(id)
        )
        """,
    )

    create_table_if_missing(
        conn,
        """
        CREATE TABLE IF NOT EXISTS lancamentos_planilha (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fatura_id INTEGER NOT NULL,
            orgao_id INTEGER,
            valor_lancado REAL NOT NULL,
            percentual_aplicado REAL,
            competencia TEXT,
            nome_planilha TEXT,
            linha_planilha INTEGER,
            status TEXT CHECK(status IN ('pendente','lançado','revisao','erro')) DEFAULT 'pendente',
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(fatura_id) REFERENCES faturas(id) ON DELETE CASCADE,
            FOREIGN KEY(orgao_id) REFERENCES orgaos(id)
        )
        """,
    )

    create_table_if_missing(
        conn,
        """
        CREATE TABLE IF NOT EXISTS divergencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fatura_id INTEGER NOT NULL,
            tipo_divergencia TEXT CHECK(tipo_divergencia IN ('soma_inconsistente','valor_zerado','fornecedor_ambiguo','servico_ambiguo','orgao_nao_identificado','duplicada','pdf_ilegivel','complemento_insuficiente')) NOT NULL,
            descricao TEXT,
            valor_esperado REAL,
            valor_obtido REAL,
            resolvido INTEGER NOT NULL DEFAULT 0,
            resolvido_em DATETIME,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(fatura_id) REFERENCES faturas(id) ON DELETE CASCADE
        )
        """,
    )

    create_table_if_missing(
        conn,
        """
        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tabela_origem TEXT NOT NULL,
            registro_id INTEGER,
            acao TEXT CHECK(acao IN ('leitura','classificacao','calculo','lancamento','validacao','revisao','alteracao','rejeicao')) NOT NULL,
            usuario TEXT,
            dados_anterior TEXT,
            dados_novo TEXT,
            observacao TEXT,
            resultado TEXT,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )

    create_table_if_missing(
        conn,
        """
        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave TEXT NOT NULL UNIQUE,
            valor TEXT,
            tipo TEXT,
            ambiente TEXT CHECK(ambiente IN ('desenvolvimento','producao')),
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )


def migrate_data(conn: sqlite3.Connection) -> None:
    if table_exists(conn, "orgaos"):
        rows = conn.execute("SELECT id, nome, ordem FROM orgaos ORDER BY ordem").fetchall()
        for row in rows:
            conn.execute(
                "UPDATE orgaos SET sigla = ?, tipo = 'orgao', codigo = ?, ativo = 1, atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
                (row["nome"], str(row["ordem"]), row["id"]),
            )

    if table_exists(conn, "servicos"):
        rows = conn.execute("SELECT id, nome, fornecedor, padrao, palavras_chave FROM servicos ORDER BY id").fetchall()
        for row in rows:
            categoria = "indeterminado"
            if str(row["padrao"]).strip().upper() in {"A", "B"}:
                categoria = "compartilhado"
            conn.execute(
                "UPDATE servicos SET categoria = ?, descricao = COALESCE(descricao, ?), ativo = 1, atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
                (categoria, row["palavras_chave"], row["id"]),
            )

    if table_exists(conn, "faturas"):
        rows = conn.execute(
            "SELECT f.id, f.nome_arquivo, f.hash_arquivo, f.caminho_arquivo, s.nome AS servico_nome, f.fornecedor_extraido, f.valor_total, f.data_vencimento, f.confianca, f.status FROM faturas f LEFT JOIN servicos s ON s.id = f.servico_id ORDER BY f.id"
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE faturas SET nome_arquivo = COALESCE(nome_arquivo, ?), caminho_original = COALESCE(caminho_original, ?), caminho_atual = COALESCE(caminho_atual, ?), fornecedor = COALESCE(fornecedor, ?), servico = COALESCE(servico, ?), valor_bruto = COALESCE(valor_bruto, ?), valor_final = COALESCE(valor_final, ?), data_vencimento = COALESCE(data_vencimento, ?), classificacao = COALESCE(classificacao, ?), confianca_extracao = COALESCE(confianca_extracao, ?), atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
                (
                    row["nome_arquivo"],
                    row["caminho_arquivo"],
                    row["caminho_arquivo"],
                    row["fornecedor_extraido"],
                    row["servico_nome"],
                    row["valor_total"],
                    row["valor_total"],
                    row["data_vencimento"],
                    "pendente" if row["status"] == "processado" else ("revisao" if row["status"] in ("revisao", "erro") else row["status"]),
                    row["confianca"],
                    row["id"],
                ),
            )

    if table_exists(conn, "rateios_calculados"):
        rows = conn.execute("SELECT id, fatura_id, orgao_id, percentual, valor_rateio FROM rateios_calculados ORDER BY id").fetchall()
        for row in rows:
            conn.execute(
                "INSERT OR IGNORE INTO rateios (id, fatura_id, orgao_id, percentual, valor_rateio, tipo_rateio, status, atualizado_em) VALUES (?, ?, ?, ?, ?, 'compartilhado', 'calculado', CURRENT_TIMESTAMP)",
                (row["id"], row["fatura_id"], row["orgao_id"], row["percentual"], row["valor_rateio"]),
            )

    if table_exists(conn, "logs_processamento"):
        rows = conn.execute("SELECT id, fatura_id, status, mensagem, hash_arquivo, criado_em FROM logs_processamento ORDER BY id").fetchall()
        for row in rows:
            nivel = "info"
            if str(row["status"]).lower() in {"erro", "rejeitado"}:
                nivel = "error"
            elif str(row["status"]).lower() in {"duplicado", "revisao"}:
                nivel = "warning"
            conn.execute(
                "UPDATE logs_processamento SET nivel = COALESCE(nivel, ?), contexto = COALESCE(contexto, ?), payload = COALESCE(payload, ?), criado_em = COALESCE(criado_em, ?) WHERE id = ?",
                (nivel, row["status"], json.dumps({"hash_arquivo": row["hash_arquivo"]}, ensure_ascii=False), row["criado_em"], row["id"]),
            )

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (json.JSONDecodeError, OSError):
            payload = {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                conn.execute(
                    "INSERT OR REPLACE INTO configuracoes (chave, valor, tipo, ambiente) VALUES (?, ?, ?, 'desenvolvimento')",
                    (str(key), "" if value is None else str(value), "texto"),
                )

    conn.commit()


def main() -> None:
    backup_db()
    conn = connect_db()
    try:
        ensure_legacy_columns(conn)
        ensure_tables(conn)
        migrate_data(conn)
        create_indexes(conn)
        conn.commit()
        print("Migração do modelo de dados concluída com sucesso.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
