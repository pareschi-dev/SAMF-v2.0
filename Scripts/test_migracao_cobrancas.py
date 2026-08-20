import sqlite3

import pytest

from migracao_modelo_dados import ensure_cobrancas_tables


TABLES = {
    'contas',
    'regras_cobranca',
    'destinatarios',
    'mensagens',
    'mapeamentos_planilha',
    'leituras_planilha',
    'divergencias_cobranca',
    'auditoria_cobranca',
}


def _connection():
    conn = sqlite3.connect(':memory:')
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('CREATE TABLE faturas (id INTEGER PRIMARY KEY)')
    return conn


def test_estruturas_de_cobrancas_sao_idempotentes_e_preservam_faturas():
    conn = _connection()
    try:
        ensure_cobrancas_tables(conn)
        ensure_cobrancas_tables(conn)
        tabelas = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert TABLES <= tabelas
        assert conn.execute('SELECT COUNT(*) FROM faturas').fetchone()[0] == 0
    finally:
        conn.close()


def test_mensagens_bloqueiam_duplicidade_funcional():
    conn = _connection()
    try:
        ensure_cobrancas_tables(conn)
        regra = conn.execute(
            "INSERT INTO regras_cobranca (nome, usuario_criador) VALUES (?, ?) RETURNING id",
            ('Regra teste', 'teste'),
        ).fetchone()[0]
        destinatario = conn.execute(
            "INSERT INTO destinatarios (nome, tipo) VALUES (?, ?) RETURNING id",
            ('Destinatário teste', 'orgao'),
        ).fetchone()[0]
        conta = conn.execute(
            "INSERT INTO contas (identificador, status, regra_cobranca_id) VALUES (?, ?, ?) RETURNING id",
            ('CONTA-TESTE', 'PENDENTE', regra),
        ).fetchone()[0]
        dados = (conta, destinatario, regra, '2026-01', 'proxima_do_vencimento', 'whatsapp', 'prévia', 'previa')
        conn.execute(
            "INSERT INTO mensagens (conta_id, destinatario_id, regra_id, competencia, tipo_alerta, canal, texto, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            dados,
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO mensagens (conta_id, destinatario_id, regra_id, competencia, tipo_alerta, canal, texto, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                dados,
            )
    finally:
        conn.close()


def test_auditoria_de_cobranca_nao_pode_ser_excluida():
    conn = _connection()
    try:
        ensure_cobrancas_tables(conn)
        conn.execute("INSERT INTO auditoria_cobranca (tabela_origem, acao) VALUES ('contas', 'criação')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('DELETE FROM auditoria_cobranca')
    finally:
        conn.close()
