from datetime import date

import pytest

from classificador_status_contas import (
    STATUS_DIVERGENTE,
    STATUS_PAGA,
    STATUS_PENDENTE,
    STATUS_PROXIMA,
    STATUS_REVISAO,
    STATUS_SEM_DATA,
    STATUS_SEM_VALOR,
    STATUS_VENCIDA,
    classificar_status_conta,
)


HOJE = date(2026, 8, 20)


def _conta(valor='100,00', vencimento='30/08/2026'):
    return {'valor_pendente': valor, 'data_vencimento': vencimento}


def _status(conta, **kwargs):
    return classificar_status_conta(conta, data_atual=HOJE, **kwargs)['status']


def test_paga_nao_pode_gerar_aviso():
    resultado = classificar_status_conta(_conta('0,00'), data_atual=HOJE, dias_antecedencia=5)
    assert resultado == {'status': STATUS_PAGA, 'pode_gerar_aviso': False}


def test_pendente():
    assert _status(_conta(vencimento='30/09/2026')) == STATUS_PENDENTE


def test_proxima_do_vencimento():
    assert _status(_conta(vencimento='24/08/2026'), dias_antecedencia=7) == STATUS_PROXIMA


def test_vencida():
    assert _status(_conta(vencimento='19/08/2026')) == STATUS_VENCIDA


def test_sem_data_de_vencimento_para_ausente_e_invalida():
    assert _status(_conta(vencimento='')) == STATUS_SEM_DATA
    assert _status(_conta(vencimento='31/02/2026')) == STATUS_SEM_DATA


def test_sem_valor_para_ausente_invalido_e_negativo():
    assert _status(_conta(valor=None)) == STATUS_SEM_VALOR
    assert _status(_conta(valor='invalido')) == STATUS_SEM_VALOR
    assert _status(_conta(valor='-1,00')) == STATUS_SEM_VALOR


def test_divergente():
    assert _status(_conta(), divergente=True) == STATUS_DIVERGENTE


def test_aguardando_revisao():
    assert _status(_conta(), requer_revisao=True) == STATUS_REVISAO


def test_dias_para_considerar_vencida_respeitado():
    assert _status(_conta(vencimento='19/08/2026'), dias_para_considerar_vencida=2) == STATUS_PROXIMA
