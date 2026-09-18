import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import app as app_module


def _conn(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_regra_exige_permissao_confirmacao_e_justificativa(monkeypatch, tmp_path):
    path = tmp_path / 'regras.db'
    monkeypatch.setattr(app_module, 'get_db', lambda: _conn(path))
    client = app_module.app.test_client()
    assert client.post('/api/auth/bootstrap', json={'usuario': 'admin', 'nome': 'Admin', 'senha': 'senha-segura'}).status_code == 201
    admin_token = client.post('/api/auth/login', json={'usuario': 'admin', 'senha': 'senha-segura'}).get_json()['token']
    assert client.post('/api/usuarios', headers={'Authorization': f'Bearer {admin_token}'}, json={'usuario': 'operador', 'nome': 'Operador', 'senha': 'senha-segura', 'perfil': 'operador'}).status_code == 201
    operador_token = client.post('/api/auth/login', json={'usuario': 'operador', 'senha': 'senha-segura'}).get_json()['token']
    base = {'vigencia_inicio': '2026-01-01', 'usuario': 'operador', 'justificativa': 'x', 'confirmacao': True}
    assert client.post('/api/regras-administrativas', headers={'Authorization': f'Bearer {operador_token}'}, json=base).status_code == 403
    base['confirmacao'] = False
    assert client.post('/api/regras-administrativas', headers={'Authorization': f'Bearer {admin_token}'}, json=base).status_code == 400
    base['confirmacao'] = True; base['justificativa'] = ''
    assert client.post('/api/regras-administrativas', headers={'Authorization': f'Bearer {admin_token}'}, json=base).status_code == 400


def test_regra_cadastra_versoes_sem_alterar_historico(monkeypatch, tmp_path):
    path = tmp_path / 'regras.db'
    monkeypatch.setattr(app_module, 'get_db', lambda: _conn(path))
    client = app_module.app.test_client()
    assert client.post('/api/auth/bootstrap', json={'usuario': 'admin', 'nome': 'Admin', 'senha': 'senha-segura'}).status_code == 201
    token = client.post('/api/auth/login', json={'usuario': 'admin', 'senha': 'senha-segura'}).get_json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    payload = {'perfil': 'administrador', 'confirmacao': True, 'usuario': 'admin', 'justificativa': 'Cadastro inicial', 'servico': 'Água e esgoto', 'fornecedor': 'CESAN', 'classificacao': 'COMPARTILHADA', 'percentuais': '{"SRA": "60"}', 'vigencia_inicio': '2026-01-01'}
    primeira = client.post('/api/regras-administrativas', headers=headers, json=payload)
    assert primeira.status_code == 201
    payload.update({'grupo_id': primeira.get_json()['grupo_id'], 'justificativa': 'Nova vigência', 'vigencia_inicio': '2027-01-01', 'percentuais': '{"SRA": "70"}'})
    segunda = client.post('/api/regras-administrativas', headers=headers, json=payload)
    assert segunda.status_code == 201
    conn = _conn(path)
    rows = conn.execute('SELECT versao, percentuais, vigencia_inicio FROM regras_administrativas ORDER BY versao').fetchall()
    conn.close()
    assert [(row['versao'], row['percentuais']) for row in rows] == [(1, '{"SRA": "60"}'), (2, '{"SRA": "70"}')]