import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import app as app_module


def _db(tmp_path):
    caminho = tmp_path / 'export.db'
    conn = sqlite3.connect(caminho)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE servicos (id INTEGER PRIMARY KEY, nome TEXT);
        CREATE TABLE orgaos (id INTEGER PRIMARY KEY, nome TEXT, ordem INTEGER);
        CREATE TABLE faturas (id INTEGER PRIMARY KEY, nome_arquivo TEXT, servico_id INTEGER, fornecedor TEXT, fornecedor_extraido TEXT, servico TEXT, competencia TEXT, classificacao TEXT, orgao_beneficiario TEXT, status TEXT, valor_base REAL, valor_total REAL, criado_em TEXT);
        CREATE TABLE rateios_calculados (fatura_id INTEGER, orgao_id INTEGER, percentual REAL, valor_rateio REAL);
        INSERT INTO servicos VALUES (1, 'Água e esgoto');
        INSERT INTO orgaos VALUES (1, 'SRA', 1);
        INSERT INTO faturas VALUES (1, 'cesan.pdf', 1, 'CESAN', 'CESAN', 'Água e esgoto', '2026-08', 'COMPARTILHADA', '', 'processado', 100, 100, '2026-08-19');
        INSERT INTO rateios_calculados VALUES (1, 1, 100, 100);
    ''')
    conn.commit(); conn.close()
    return caminho


def _cliente(monkeypatch, caminho):
    def conectar():
        conn = sqlite3.connect(caminho)
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(app_module, 'get_db', conectar)
    cliente = app_module.app.test_client()
    assert cliente.post('/api/auth/bootstrap', json={'usuario': 'admin', 'nome': 'Admin', 'senha': 'senha-segura'}).status_code == 201
    token = cliente.post('/api/auth/login', json={'usuario': 'admin', 'senha': 'senha-segura'}).get_json()['token']
    return cliente, {'Authorization': f'Bearer {token}'}


def test_exportacao_valida_total_e_auditoria_filtra(monkeypatch, tmp_path):
    caminho = _db(tmp_path)
    cliente, headers = _cliente(monkeypatch, caminho)
    resumo = cliente.get('/api/export/validar?tipo=faturas&formato=csv&competencia=2026-08', headers=headers)
    assert resumo.status_code == 200
    assert resumo.get_json()['total_exibido'] == resumo.get_json()['total_exportado'] == '100.00'
    assert cliente.get('/api/logs?tipo_evento=login', headers=headers).status_code == 200


def test_permissao_de_operador_bloqueia_regra_e_audita(monkeypatch, tmp_path):
    caminho = _db(tmp_path)
    cliente, admin = _cliente(monkeypatch, caminho)
    assert cliente.post('/api/usuarios', headers=admin, json={'usuario': 'operador', 'nome': 'Operador', 'senha': 'senha-segura', 'perfil': 'operador'}).status_code == 201
    token = cliente.post('/api/auth/login', json={'usuario': 'operador', 'senha': 'senha-segura'}).get_json()['token']
    resposta = cliente.post('/api/regras-administrativas', headers={'Authorization': f'Bearer {token}'}, json={'justificativa': 'teste'})
    assert resposta.status_code == 403
    eventos = cliente.get('/api/logs?tipo_evento=autorização%20negada', headers=admin).get_json()
    assert any(evento['usuario'] == 'operador' for evento in eventos)


def test_interface_ativa_declara_auth_export_logs_e_offline():
    html = (Path(__file__).parent / 'static' / 'index.html').read_text(encoding='utf-8')
    assert 'auth-modal' in html and 'const API = "/api"' in html and '${API}/auth/login' in html
    assert all(opcao in html for opcao in ('value="faturas"', 'value="auditoria"', 'Excel (.xlsx)', 'CSV (.csv)'))
    assert 'logs-body' in html and 'Registro append-only' in html
    assert 'catch { document.getElementById(\'status-dot\').className' in html
