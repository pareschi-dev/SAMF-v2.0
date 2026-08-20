import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import app as app_module


def _db(tmp_path):
    caminho = tmp_path / 'navegacao.db'
    conn = sqlite3.connect(caminho)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE servicos (id INTEGER PRIMARY KEY, nome TEXT);
        CREATE TABLE faturas (
            id INTEGER PRIMARY KEY, hash_arquivo TEXT, caminho_arquivo TEXT,
            nome_arquivo TEXT, servico_id INTEGER, fornecedor_extraido TEXT,
            valor_total REAL, data_vencimento TEXT, confianca REAL, status TEXT,
            criado_em TEXT, atualizado_em TEXT, classificacao TEXT,
            valor_base REAL, orgao_beneficiario TEXT, servico TEXT, fornecedor TEXT, competencia TEXT
        );
        CREATE TABLE rateios_calculados (fatura_id INTEGER, orgao_id INTEGER, valor_rateio REAL);
        CREATE TABLE orgaos (id INTEGER PRIMARY KEY, nome TEXT, ordem INTEGER);
        CREATE TABLE logs_processamento (criado_em TEXT);
        INSERT INTO servicos VALUES (1, 'Água e esgoto');
            INSERT INTO faturas
                (id, hash_arquivo, caminho_arquivo, nome_arquivo, servico_id, fornecedor_extraido,
                 valor_total, data_vencimento, confianca, status, criado_em, atualizado_em, classificacao, valor_base, servico, fornecedor, competencia)
            VALUES
                (1, 'a', 'a.pdf', 'a.pdf', 1, 'CESAN', 10, NULL, 1, 'processado', '2026-08-19', '2026-08-19', 'COMPARTILHADA', 10, 'Água e esgoto', 'CESAN', '05/2026'),
                (2, 'b', 'b.pdf', 'b.pdf', 1, 'CESAN', 20, NULL, 1, 'processado', '2026-08-18', '2026-08-18', 'EXCLUSIVA', 20, 'Água e esgoto', 'CESAN', '05/2026'),
                (3, 'c', 'c.pdf', 'c.pdf', 1, 'CESAN', 30, NULL, 1, 'revisao', '2026-08-17', '2026-08-17', 'revisao', 30, 'Água e esgoto', 'CESAN', '05/2026');
    ''')
    conn.close()
    return caminho


def test_rotas_de_faturas_sao_servidas_pela_mesma_pagina():
    cliente = app_module.app.test_client()
    for rota in ('/faturas/todas', '/faturas/compartilhadas', '/faturas/exclusivas', '/faturas/revisao'):
        resposta = cliente.get(rota)
        assert resposta.status_code == 200
        assert b'GEST' in resposta.data


def test_api_filtra_classificacao_e_revisao_sem_duplicar_registros(monkeypatch, tmp_path):
    caminho = _db(tmp_path)
    def nova_conexao():
        conn = sqlite3.connect(caminho)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(app_module, 'get_db', nova_conexao)
    cliente = app_module.app.test_client()
    token = cliente.post('/api/auth/bootstrap', json={'usuario': 'admin', 'nome': 'Admin', 'senha': 'senha-segura'}).status_code
    assert token == 201
    token = cliente.post('/api/auth/login', json={'usuario': 'admin', 'senha': 'senha-segura'}).get_json()['token']
    cliente.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'

    todas = cliente.get('/api/faturas').get_json()
    compartilhadas = cliente.get('/api/faturas?classificacao=COMPARTILHADA').get_json()
    exclusivas = cliente.get('/api/faturas?classificacao=EXCLUSIVA').get_json()
    revisao = cliente.get('/api/faturas?status=AGUARDANDO_REVISÃO').get_json()

    assert len(todas) == 3
    assert [item['id'] for item in compartilhadas] == [1]
    assert [item['id'] for item in exclusivas] == [2]
    assert [item['id'] for item in revisao] == [3]
    assert len({item['id'] for item in todas}) == len(todas)


def test_totais_dashboard_coincidem_com_paginas_filtradas(monkeypatch, tmp_path):
    caminho = _db(tmp_path)

    def nova_conexao():
        conn = sqlite3.connect(caminho)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(app_module, 'get_db', nova_conexao)
    cliente = app_module.app.test_client()
    assert cliente.post('/api/auth/bootstrap', json={'usuario': 'admin', 'nome': 'Admin', 'senha': 'senha-segura'}).status_code == 201
    token = cliente.post('/api/auth/login', json={'usuario': 'admin', 'senha': 'senha-segura'}).get_json()['token']
    cliente.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    dashboard = cliente.get('/api/stats').get_json()

    assert dashboard['total_faturas'] == len(cliente.get('/api/faturas').get_json())
    for chave, filtro in (
        ('compartilhadas', 'COMPARTILHADA'),
        ('exclusivas', 'EXCLUSIVA'),
    ):
        pagina = cliente.get(f'/api/faturas?classificacao={filtro}').get_json()
        assert dashboard['classificacoes'][chave]['quantidade'] == len(pagina)
    revisao = cliente.get('/api/faturas?status=AGUARDANDO_REVISÃO').get_json()
    assert dashboard['classificacoes']['revisao']['quantidade'] == len(revisao)