import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from whatsapp_business import (
    STATUS_INCOMPLETO,
    STATUS_INVALIDO,
    STATUS_NAO_CONFIGURADO,
    STATUS_PRODUCAO_BLOQUEADA,
    STATUS_TESTE_APROVADO,
    ErroWhatsAppBusiness,
    WhatsAppBusinessAdapter,
    validar_configuracao_whatsapp,
)


def config(**alteracoes):
    base = {
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
    base.update(alteracoes)
    return base


def secrets():
    return {'TEST_WA_TOKEN': 'token-secreto', 'TEST_WA_VERIFY': 'verify-secreto'}


def test_configuracao_ausente_e_incompleta():
    assert validar_configuracao_whatsapp({})['status'] == STATUS_NAO_CONFIGURADO
    assert validar_configuracao_whatsapp({'cobrancas_whatsapp_modo': 'simulado'})['status'] == STATUS_INCOMPLETO


@pytest.mark.parametrize('campo', ['cobrancas_whatsapp_access_token_env', 'cobrancas_whatsapp_template_name'])
def test_token_ou_template_ausente(campo):
    dados = config()
    if campo.endswith('token_env'):
        dados[campo] = ''
    else:
        dados[campo] = ''
    assert validar_configuracao_whatsapp(dados, secret_loader=secrets().get)['status'] == STATUS_INCOMPLETO


def test_credencial_simulada_invalida_e_conexao_aprovada():
    assert WhatsAppBusinessAdapter(config(), secret_loader=secrets().get, simulated_credential=False).testar_conexao()['status'] == STATUS_INVALIDO
    resultado = WhatsAppBusinessAdapter(config(), secret_loader=secrets().get).testar_conexao()
    assert resultado == {'status': STATUS_TESTE_APROVADO, 'modo': 'simulado', 'externo_chamado': False}


def test_envio_real_desativado_e_producao_bloqueada():
    adapter = WhatsAppBusinessAdapter(config(), secret_loader=secrets().get)
    with pytest.raises(ErroWhatsAppBusiness, match='bloqueado'):
        adapter.enviar('+5511999991234', {'template': 'teste'})
    assert validar_configuracao_whatsapp(config(cobrancas_whatsapp_envio_real_ativo='true'), secret_loader=secrets().get)['status'] == STATUS_PRODUCAO_BLOQUEADA


def test_mensagem_montada_sem_segredo():
    resultado = WhatsAppBusinessAdapter(config(), secret_loader=secrets().get).montar_mensagem({'nome': 'Ana'})
    assert resultado['template'] == 'cobranca_vencimento'
    assert 'token-secreto' not in str(resultado)
    assert 'TEST_WA_TOKEN' not in str(resultado)