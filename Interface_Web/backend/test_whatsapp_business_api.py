import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import app as app_module


CONFIG = {
    'cobrancas_whatsapp_business_account_id': '123456789',
    'cobrancas_whatsapp_phone_number_id': '987654321',
    'cobrancas_whatsapp_api_url': 'https://graph.facebook.com',
    'cobrancas_whatsapp_api_version': 'v20.0',
    'cobrancas_whatsapp_template_name': 'cobranca_vencimento',
    'cobrancas_whatsapp_template_language': 'pt_BR',
    'cobrancas_whatsapp_webhook_url': 'https://samf.example/webhook',
    'cobrancas_whatsapp_access_token_env': 'TEST_WA_TOKEN',
    'cobrancas_whatsapp_webhook_verify_token_env': 'TEST_WA_VERIFY',
    'cobrancas_whatsapp_ambiente': 'teste',
    'cobrancas_whatsapp_modo': 'simulado',
    'cobrancas_whatsapp_envio_real_ativo': 'false',
}


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    banco = tmp_path / 'whatsapp_api.db'
    configuracao = {}
    backups = []

    def conectar():
        conn = sqlite3.connect(banco)
        conn.row_factory = sqlite3.Row
        return conn

    def carregar():
        return dict(configuracao)

    def salvar(config, _raiz):
        configuracao.clear()
        configuracao.update(config)
        return dict(config)

    monkeypatch.setenv('TEST_WA_TOKEN', 'segredo-de-teste')
    monkeypatch.setenv('TEST_WA_VERIFY', 'verificacao-de-teste')
    monkeypatch.setattr(app_module, 'get_db', conectar)
    monkeypatch.setattr(app_module, 'load_config', carregar)
    monkeypatch.setattr(app_module, 'salvar_configuracao', salvar)
    monkeypatch.setattr(app_module, '_backup_antes', lambda motivo: backups.append(motivo))
    cliente = app_module.app.test_client()
    assert cliente.post('/api/auth/bootstrap', json={'usuario': 'admin', 'nome': 'Admin', 'senha': 'senha-segura'}).status_code == 201
    admin = cliente.post('/api/auth/login', json={'usuario': 'admin', 'senha': 'senha-segura'}).get_json()['token']
    assert cliente.post('/api/usuarios', headers={'Authorization': f'Bearer {admin}'}, json={'usuario': 'aprovador', 'nome': 'Aprovador', 'senha': 'senha-segura', 'perfil': 'aprovador'}).status_code == 201
    aprovador = cliente.post('/api/auth/login', json={'usuario': 'aprovador', 'senha': 'senha-segura'}).get_json()['token']
    return cliente, {'Authorization': f'Bearer {admin}'}, {'Authorization': f'Bearer {aprovador}'}, configuracao, backups, conectar


def test_configuracao_ausente_e_aprovador_sem_permissao(ambiente):
    cliente, admin, aprovador, *_ = ambiente
    assert cliente.get('/api/integracao-whatsapp/configuracao', headers=admin).get_json()['status'] == 'nao_configurado'
    assert cliente.get('/api/integracao-whatsapp/configuracao', headers=aprovador).status_code == 403


def test_administrador_configura_modo_simulado_e_audita_sem_segredos(ambiente):
    cliente, admin, _, configuracao, backups, conectar = ambiente
    resposta = cliente.post('/api/integracao-whatsapp/configuracao', headers=admin, json=CONFIG)
    assert resposta.status_code == 200
    assert resposta.get_json()['status'] == 'teste_aprovado'
    assert backups == ['configuracao_whatsapp']
    conn = conectar()
    eventos = conn.execute("SELECT * FROM auditoria_eventos WHERE tipo_evento='configuração_whatsapp'").fetchall()
    assert len(eventos) == 1
    texto = json.dumps(dict(eventos[0]), ensure_ascii=False)
    assert 'segredo-de-teste' not in texto
    assert 'verificacao-de-teste' not in texto
    assert 'token' not in texto.lower()
    conn.close()


def test_rejeita_token_em_texto_e_bloqueia_producao(ambiente):
    cliente, admin, *_ = ambiente
    resposta = cliente.post('/api/integracao-whatsapp/configuracao', headers=admin, json={**CONFIG, 'cobrancas_whatsapp_access_token': 'token-em-texto'})
    assert resposta.status_code == 400
    resposta = cliente.post('/api/integracao-whatsapp/configuracao', headers=admin, json={**CONFIG, 'cobrancas_whatsapp_envio_real_ativo': 'true'})
    assert resposta.status_code == 409