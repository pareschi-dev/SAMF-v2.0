from datetime import datetime, timezone

import pytest

from servico_envio_cobranca import ErroEnvioCobranca, ServicoEnvioCobranca


AGORA = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def config(modo='envio_autorizado', configurado=True):
    return {'cobrancas_modo_operacao': modo, 'cobrancas_provedor_whatsapp': 'teste' if configurado else '', 'cobrancas_status_integracao': 'configurado' if configurado else 'pendente de configuração'}


def mensagem(): return {'status': 'APROVADA', 'texto': 'Mensagem aprovada'}
def conta(): return {'status': 'PENDENTE', 'valor_pendente': 100}
def destinatario(): return {'ativo': 1, 'telefone': '+5511999991234', 'autorizacao_registrada': 1}
def regra(): return {'ativa': 1, 'limite_diario': 10, 'intervalo_minimo_segundos': 60, 'horario_permitido': '08:00-18:00'}


class ProvedorFalso:
    def __init__(self): self.envios = 0
    def testar_credencial(self): return {'configurado': True}
    def enviar(self, telefone, texto): self.envios += 1; return {'id': 'ext-1', 'status': 'accepted'}
    def consultar(self, identificador): return {'id': identificador, 'status': 'delivered'}
    def cancelar(self, identificador): return {'id': identificador, 'status': 'cancelled'}


def test_modo_teste_nao_chama_provedor():
    provedor = ProvedorFalso()
    resultado = ServicoEnvioCobranca(config('previa'), provedor, agora=lambda: AGORA).enviar_aprovada(mensagem(), conta(), destinatario(), regra())
    assert resultado['status'] == 'simulacao'
    assert provedor.envios == 0


def test_provedor_nao_configurado_bloqueia_envio():
    resultado = ServicoEnvioCobranca(config(configurado=False), agora=lambda: AGORA).enviar_aprovada(mensagem(), conta(), destinatario(), regra())
    assert resultado['status'] == 'bloqueado'
    assert 'não configurado' in resultado['erro']


def test_envio_aprovado_registra_id_resposta_e_tentativa():
    resultado = ServicoEnvioCobranca(config(), ProvedorFalso(), agora=lambda: AGORA).enviar_aprovada(mensagem(), conta(), destinatario(), regra())
    assert resultado['status'] == 'enviado'
    assert resultado['tentativa'] == 1
    assert resultado['identificador_externo'] == 'ext-1'
    assert resultado['resposta_provedor']['status'] == 'accepted'


@pytest.mark.parametrize('alteracao,codigo', [
    ({'mensagem': {'status': 'PENDENTE', 'texto': 'Mensagem aprovada'}}, 'mensagem_nao_aprovada'),
    ({'conta': {'status': 'PAGA', 'valor_pendente': 0}}, 'conta_nao_pendente'),
    ({'destinatario': {'ativo': 0, 'telefone': '+5511999991234', 'autorizacao_registrada': 1}}, 'destinatario_inativo'),
    ({'destinatario': {'ativo': 1, 'telefone': '123', 'autorizacao_registrada': 1}}, 'telefone_invalido'),
    ({'destinatario': {'ativo': 1, 'telefone': '+5511999991234', 'autorizacao_registrada': 0}}, 'sem_autorizacao'),
    ({'regra': {'ativa': 0, 'limite_diario': 10, 'horario_permitido': '08:00-18:00'}}, 'regra_inativa'),
    ({'contagem_diaria': 10}, 'limite_diario'),
    ({'regra': {'ativa': 1, 'limite_diario': 10, 'horario_permitido': '13:00-14:00'}}, 'fora_do_horario'),
    ({'duplicada': True}, 'mensagem_duplicada'),
])
def test_validacoes_antes_do_envio(alteracao, codigo):
    args = {'mensagem': mensagem(), 'conta': conta(), 'destinatario': destinatario(), 'regra': regra(), 'contagem_diaria': 0, 'duplicada': False}
    args.update(alteracao)
    with pytest.raises(ErroEnvioCobranca) as erro:
        ServicoEnvioCobranca(config(), ProvedorFalso(), agora=lambda: AGORA).enviar_aprovada(**args)
    assert erro.value.codigo == codigo


def test_intervalo_minimo_bloqueia():
    with pytest.raises(ErroEnvioCobranca) as erro:
        ServicoEnvioCobranca(config(), ProvedorFalso(), agora=lambda: AGORA).enviar_aprovada(mensagem(), conta(), destinatario(), regra(), ultima_mensagem_em=datetime(2026, 8, 20, 11, 59, 30, tzinfo=timezone.utc))
    assert erro.value.codigo == 'intervalo_minimo'


def test_consulta_e_cancelamento_delegam_ao_provedor():
    servico = ServicoEnvioCobranca(config(), ProvedorFalso(), agora=lambda: AGORA)
    assert servico.consultar_resposta('ext-1')['status'] == 'delivered'
    assert servico.cancelar_pendente('ext-1')['status'] == 'cancelled'
