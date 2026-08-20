import sqlite3
from datetime import datetime, timezone, timedelta

from controle_duplicidade_mensagens import verificar_duplicidade
from migracao_modelo_dados import ensure_cobrancas_tables


AGORA = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def _conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('CREATE TABLE faturas (id INTEGER PRIMARY KEY)')
    ensure_cobrancas_tables(conn)
    conn.execute("INSERT INTO regras_cobranca (id, nome, usuario_criador, ativa, intervalo_minimo_segundos) VALUES (1, 'Regra', 'teste', 1, 3600)")
    conn.execute("INSERT INTO destinatarios (id, nome, tipo, ativo, autorizacao_registrada) VALUES (1, 'Ana', 'orgao', 1, 1)")
    conn.execute("INSERT INTO contas (id, identificador, status, valor_pendente, data_vencimento) VALUES (1, 'C1', 'PENDENTE', 100, '2026-08-30')")
    return conn


def _mensagem(conn, status='enviado', criada='2026-08-20T11:30:00+00:00', valor=100, vencimento='2026-08-30'):
    conn.execute("""INSERT INTO mensagens (conta_id, destinatario_id, regra_id, competencia, tipo_alerta, canal, texto, status, criada_em, enviada_em, valor_pendente_referencia, data_vencimento_referencia) VALUES (1, 1, 1, '08/2026', 'proxima', 'whatsapp', 'x', ?, ?, ?, ?, ?)""", (status, criada, criada if status in {'enviado', 'entregue'} else None, valor, vencimento))
    conn.commit()


def _verificar(conn, **kwargs):
    base = {'conta_id': 1, 'destinatario_id': 1, 'regra_id': 1, 'competencia': '08/2026', 'tipo_alerta': 'proxima', 'valor_pendente': 100, 'data_vencimento': '2026-08-30', 'intervalo_minimo_segundos': 3600, 'agora': AGORA}
    base.update(kwargs)
    return verificar_duplicidade(conn, **base)


def test_repeticao_da_leitura_e_execucao_no_mesmo_dia_bloqueiam():
    conn = _conn(); _mensagem(conn)
    assert _verificar(conn)['codigo'] == 'mensagem_enviada_no_intervalo'
    conn.close()


def test_mensagem_pendente_bloqueia_nova_execucao():
    conn = _conn(); _mensagem(conn, status='aguardando_aprovacao', criada='2026-08-19T10:00:00+00:00')
    resultado = _verificar(conn)
    assert resultado['permitido'] is False
    assert resultado['codigo'] == 'mensagem_pendente'


def test_alteracao_de_valor_permite_novo_alerta():
    conn = _conn(); _mensagem(conn, valor=100)
    resultado = _verificar(conn, valor_pendente=125)
    assert resultado['permitido'] is True
    assert resultado['codigo'] == 'alteracao_detectada'


def test_alteracao_de_vencimento_permite_novo_alerta():
    conn = _conn(); _mensagem(conn, vencimento='2026-08-30')
    resultado = _verificar(conn, data_vencimento='2026-09-05')
    assert resultado['permitido'] is True
    assert resultado['codigo'] == 'alteracao_detectada'


def test_conta_paga_cancela_mensagens_pendentes():
    conn = _conn(); _mensagem(conn, status='aguardando_aprovacao')
    conn.execute("UPDATE contas SET status='PAGA', valor_pendente=0 WHERE id=1"); conn.commit()
    resultado = _verificar(conn)
    assert resultado['codigo'] == 'conta_paga'
    assert resultado['canceladas'] == 1
    assert conn.execute('SELECT status FROM mensagens').fetchone()[0] == 'cancelado'
