import sqlite3
from datetime import datetime, timezone

import pytest

from auditoria_cobrancas import listar_auditoria, registrar_auditoria_cobranca
from migracao_modelo_dados import ensure_cobrancas_tables


def _conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('CREATE TABLE faturas (id INTEGER PRIMARY KEY)')
    ensure_cobrancas_tables(conn)
    return conn


def test_registra_eventos_com_valores_e_metadados():
    conn = _conn()
    evento_id = registrar_auditoria_cobranca(conn, tipo_evento='envio', usuario='ana', registro_id=4, arquivo='oficial.xlsx', orgao='SRA', status='enviado', valor_anterior={'status': 'aprovado'}, valor_novo={'status': 'enviado'}, data_hora=datetime(2026, 8, 20, 12, tzinfo=timezone.utc))
    conn.commit()
    row = conn.execute('SELECT * FROM auditoria_cobranca WHERE id=?', (evento_id,)).fetchone()
    assert row['tipo_evento'] == 'envio'
    assert row['usuario'] == 'ana'
    assert row['arquivo_origem'] == 'oficial.xlsx'
    assert row['orgao'] == 'SRA'
    assert row['valor_anterior'] == '{"status": "aprovado"}'
    assert row['valor_novo'] == '{"status": "enviado"}'


def test_filtros_por_periodo_usuario_arquivo_orgao_status_e_tipo():
    conn = _conn()
    registrar_auditoria_cobranca(conn, tipo_evento='envio', usuario='ana', arquivo='oficial.xlsx', orgao='SRA', status='enviado', data_hora=datetime(2026, 8, 20, 12, tzinfo=timezone.utc))
    registrar_auditoria_cobranca(conn, tipo_evento='falha', usuario='bruno', arquivo='outra.xlsx', orgao='SRT', status='falhou', data_hora=datetime(2026, 8, 19, 12, tzinfo=timezone.utc))
    conn.commit()
    eventos = listar_auditoria(conn, {'data_inicio': '2026-08-20', 'usuario': 'ana', 'arquivo_origem': 'oficial', 'orgao': 'SRA', 'status': 'enviado', 'tipo_evento': 'envio'})
    assert len(eventos) == 1
    assert eventos[0]['usuario'] == 'ana'


def test_auditoria_nao_pode_ser_excluida():
    conn = _conn()
    registrar_auditoria_cobranca(conn, tipo_evento='cancelamento', usuario='ana')
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute('DELETE FROM auditoria_cobranca')
