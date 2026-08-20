import sqlite3
from datetime import datetime, timezone

from conversor_contas_cobrancas import sincronizar_contas
from migracao_modelo_dados import ensure_cobrancas_tables


def _conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('CREATE TABLE faturas (id INTEGER PRIMARY KEY)')
    ensure_cobrancas_tables(conn)
    conn.execute("INSERT INTO leituras_planilha (id, caminho_origem, aba, hash_origem, lida_em, status) VALUES (7, 'oficial.xlsx', 'Oficial', 'hash-1', '2026-08-20T00:00:00+00:00', 'sucesso')")
    return conn


def _linha(valor='100.00', vencimento='2026-08-31', numero='F-1'):
    return {
        'orgao': 'SRA', 'unidade': 'SEDE', 'fornecedor': 'Fornecedor A', 'servico': 'Servico A',
        'competencia': '08/2026', 'numero_fatura': numero, 'data_vencimento': vencimento,
        'valor_original': float(valor), 'valor_pago': 0.0, 'valor_pendente': float(valor),
        'responsavel': 'Responsavel A',
    }


def test_primeira_leitura_cria_conta_com_origem():
    conn = _conn()
    resultado = sincronizar_contas(conn, [_linha()], arquivo_origem='oficial.xlsx', origem_hash='hash-1', leitura_planilha_id=7)
    conta = conn.execute('SELECT * FROM contas').fetchone()
    assert resultado['criadas'] == 1
    assert conta['origem_hash'] == 'hash-1'
    assert conta['leitura_planilha_id'] == 7
    assert conta['status'] == 'PENDENTE'


def test_releitura_da_mesma_planilha_nao_duplica():
    conn = _conn()
    primeira = sincronizar_contas(conn, [_linha()], arquivo_origem='oficial.xlsx', origem_hash='hash-1')
    segunda = sincronizar_contas(conn, [_linha()], arquivo_origem='oficial.xlsx', origem_hash='hash-1')
    assert primeira['criadas'] == 1
    assert segunda['atualizadas'] == 1
    assert conn.execute('SELECT COUNT(*) FROM contas').fetchone()[0] == 1


def test_alteracao_de_valor_atualiza_mesma_conta():
    conn = _conn()
    sincronizar_contas(conn, [_linha('100.00')], arquivo_origem='oficial.xlsx', origem_hash='hash-1')
    resultado = sincronizar_contas(conn, [_linha('125.00')], arquivo_origem='oficial.xlsx', origem_hash='hash-2')
    conta = conn.execute('SELECT valor_original, valor_pendente, origem_hash FROM contas').fetchone()
    assert resultado['atualizadas'] == 1
    assert conta['valor_original'] == 125.0
    assert conta['valor_pendente'] == 125.0
    assert conta['origem_hash'] == 'hash-2'


def test_alteracao_de_vencimento_atualiza_mesma_conta():
    conn = _conn()
    sincronizar_contas(conn, [_linha(vencimento='2026-08-31')], arquivo_origem='oficial.xlsx', origem_hash='hash-1')
    resultado = sincronizar_contas(conn, [_linha(vencimento='2026-09-15')], arquivo_origem='oficial.xlsx', origem_hash='hash-2')
    assert resultado['atualizadas'] == 1
    assert conn.execute('SELECT COUNT(*) FROM contas').fetchone()[0] == 1
    assert conn.execute('SELECT data_vencimento FROM contas').fetchone()[0] == '2026-09-15'


def test_linha_duplicada_na_mesma_leitura_cria_uma_conta():
    conn = _conn()
    resultado = sincronizar_contas(conn, [_linha(), _linha()], arquivo_origem='oficial.xlsx', origem_hash='hash-1')
    assert resultado['criadas'] == 1
    assert resultado['duplicadas'] == 1
    assert conn.execute('SELECT COUNT(*) FROM contas').fetchone()[0] == 1
