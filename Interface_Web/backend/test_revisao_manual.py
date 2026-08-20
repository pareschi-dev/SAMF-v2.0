import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import app as app_module


def _banco(tmp_path):
    caminho = tmp_path / 'revisao.db'
    conn = sqlite3.connect(caminho)
    conn.executescript('''
        CREATE TABLE servicos (id INTEGER PRIMARY KEY, nome TEXT);
        CREATE TABLE faturas (id INTEGER PRIMARY KEY, status TEXT, classificacao TEXT, fornecedor TEXT, servico TEXT, competencia TEXT, valor_total REAL, atualizado_em TEXT, fornecedor_extraido TEXT, motivo_revisao TEXT);
        CREATE TABLE auditoria (id INTEGER PRIMARY KEY, tabela_origem TEXT, registro_id INTEGER, acao TEXT, usuario TEXT, dados_anterior TEXT, dados_novo TEXT, observacao TEXT, resultado TEXT, criado_em TEXT DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO faturas (id, status, classificacao, fornecedor, servico, competencia, valor_total, atualizado_em, fornecedor_extraido, motivo_revisao) VALUES (1, 'REVISAO', 'AGUARDANDO_REVISÃO', 'CESAN', 'Água e esgoto', '', 100, NULL, 'CESAN', 'pendente');
        INSERT INTO faturas (id, status, classificacao, fornecedor, servico, competencia, valor_total, atualizado_em, fornecedor_extraido, motivo_revisao) VALUES (2, 'processado', 'COMPARTILHADA', 'EDP', 'Energia elétrica', '05/2026', 200, NULL, 'EDP', NULL);
    ''')
    conn.commit(); conn.close()
    return caminho


def test_decisao_exige_usuario_e_justificativa(monkeypatch, tmp_path):
    caminho = _banco(tmp_path)
    monkeypatch.setattr(app_module, 'get_db', lambda: _conexao(caminho))
    cliente = app_module.app.test_client()
    assert cliente.post('/api/auth/bootstrap', json={'usuario': 'aprovador', 'nome': 'Aprovador', 'senha': 'senha-segura'}).status_code == 201
    token = cliente.post('/api/auth/login', json={'usuario': 'aprovador', 'senha': 'senha-segura'}).get_json()['token']
    resposta = cliente.post('/api/faturas/1/revisao', headers={'Authorization': f'Bearer {token}'}, json={'acao': 'aprovar_compartilhada'})
    assert resposta.status_code == 400


def test_aprovacao_registra_correcao_auditoria_e_bloqueia_lancamento(monkeypatch, tmp_path):
    caminho = _banco(tmp_path)
    monkeypatch.setattr(app_module, 'get_db', lambda: _conexao(caminho))
    cliente = app_module.app.test_client()
    assert cliente.post('/api/auth/bootstrap', json={'usuario': 'aprovador', 'nome': 'Aprovador', 'senha': 'senha-segura'}).status_code == 201
    token = cliente.post('/api/auth/login', json={'usuario': 'aprovador', 'senha': 'senha-segura'}).get_json()['token']
    resposta = cliente.post('/api/faturas/1/revisao', headers={'Authorization': f'Bearer {token}'}, json={
        'acao': 'aprovar_compartilhada', 'usuario': 'analista', 'justificativa': 'Dados confirmados',
        'fornecedor': 'CESAN', 'servico': 'Água e esgoto', 'complemento': 'Edifício-sede',
        'competencia': '05/2026', 'regra_utilizada': 'CESAN edifício-sede',
    })
    assert resposta.status_code == 200
    assert resposta.get_json()['status'] == 'REPROCESSAMENTO_PENDENTE'
    conn = sqlite3.connect(caminho)
    status, classificacao = conn.execute('SELECT status, classificacao FROM faturas WHERE id=1').fetchone()
    auditoria = conn.execute('SELECT usuario, observacao FROM auditoria WHERE registro_id=1').fetchone()
    conn.close()
    assert (status, classificacao) == ('REPROCESSAMENTO_PENDENTE', 'COMPARTILHADA')
    assert auditoria == ('aprovador', 'Dados confirmados')


def test_nao_permite_decidir_fatura_fora_da_revisao(monkeypatch, tmp_path):
    caminho = _banco(tmp_path)
    monkeypatch.setattr(app_module, 'get_db', lambda: _conexao(caminho))
    cliente = app_module.app.test_client()
    assert cliente.post('/api/auth/bootstrap', json={'usuario': 'aprovador', 'nome': 'Aprovador', 'senha': 'senha-segura'}).status_code == 201
    token = cliente.post('/api/auth/login', json={'usuario': 'aprovador', 'senha': 'senha-segura'}).get_json()['token']
    resposta = cliente.post('/api/faturas/2/revisao', headers={'Authorization': f'Bearer {token}'}, json={'acao': 'rejeitar', 'usuario': 'analista', 'justificativa': 'Teste'})
    assert resposta.status_code == 409


def _conexao(caminho):
    conn = sqlite3.connect(caminho)
    conn.row_factory = sqlite3.Row
    return conn