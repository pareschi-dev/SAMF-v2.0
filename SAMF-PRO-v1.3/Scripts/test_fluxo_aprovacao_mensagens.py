from datetime import datetime, timezone

import pytest

from fluxo_aprovacao_mensagens import (
    AGUARDANDO,
    APROVADA,
    PREVIA,
    REJEITADA,
    ErroAprovacaoMensagem,
    transicionar_mensagem,
    validar_lote,
)


def mensagem(status='aguardando_aprovacao'):
    return {'status': status}


def test_aprovar_revalida_conta_e_destinatario():
    resultado = transicionar_mensagem(mensagem(), 'aprovar', usuario='ana', data=datetime(2026, 8, 20, tzinfo=timezone.utc), conta_pendente=True, destinatario_ativo=True)
    assert resultado['status'] == APROVADA
    assert resultado['status_armazenamento'] == 'aprovado'
    assert resultado['usuario'] == 'ana'
    assert resultado['data'].startswith('2026-08-20')


@pytest.mark.parametrize('conta_pendente,destinatario_ativo,codigo', [(False, True, 'conta_nao_pendente'), (True, False, 'destinatario_inativo')])
def test_aprovacao_bloqueia_revalidacao_invalida(conta_pendente, destinatario_ativo, codigo):
    with pytest.raises(ErroAprovacaoMensagem) as erro:
        transicionar_mensagem(mensagem(), 'aprovar', usuario='ana', conta_pendente=conta_pendente, destinatario_ativo=destinatario_ativo)
    assert erro.value.codigo == codigo


def test_rejeitar_exige_justificativa_e_registra_usuario():
    with pytest.raises(ErroAprovacaoMensagem):
        transicionar_mensagem(mensagem(), 'rejeitar', usuario='ana')
    resultado = transicionar_mensagem(mensagem(), 'rejeitar', usuario='ana', justificativa='Dados incorretos')
    assert resultado['status'] == REJEITADA
    assert resultado['justificativa'] == 'Dados incorretos'


def test_alterar_exige_justificativa_e_volta_para_previa():
    resultado = transicionar_mensagem(mensagem(), 'alterar', usuario='ana', justificativa='Corrigir texto')
    assert resultado['status'] == PREVIA
    assert resultado['justificativa'] == 'Corrigir texto'


def test_transicoes_finais_nao_podem_ser_aprovadas_novamente():
    with pytest.raises(ErroAprovacaoMensagem):
        transicionar_mensagem(mensagem('aprovado'), 'aprovar', usuario='ana', conta_pendente=True, destinatario_ativo=True)


def test_validar_lote_remove_repetidos_e_bloqueia_lote_vazio():
    assert validar_lote([1, '2', 1]) == [1, 2]
    with pytest.raises(ErroAprovacaoMensagem):
        validar_lote([])
