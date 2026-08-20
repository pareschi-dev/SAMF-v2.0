import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_CONFIG_KEYS = [
    'entrada_path',
    'processamento_path',
    'processadas_path',
    'compartilhadas_path',
    'exclusivas_path',
    'revisao_path',
    'duplicadas_path',
    'erro_path',
    'planilha_oficial_path',
    'banco_path',
    'modo_execucao',
    'intervalo_monitoramento_segundos',
    'tempo_estabilidade_arquivo_segundos',
    'limite_diferenca_arredondamento',
    'backup_path',
    'formato_exportacao',
    'ambiente',
]


def test_configuracao_padrao_necessaria():
    base = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(os.path.dirname(base), 'Configuracoes', 'samf_config.json')
    assert os.path.exists(config_path), 'Arquivo de configuração obrigatório ausente.'
    with open(config_path, 'r', encoding='utf-8') as fh:
        config = json.load(fh)
    for key in REQUIRED_CONFIG_KEYS:
        assert key in config, f'Campo obrigatório ausente: {key}'


def test_configuracao_incompleta_deve_bloquear_processamento():
    from configuracao_operacional import validar_configuracao

    config = {key: '' for key in REQUIRED_CONFIG_KEYS}
    ok, mensagem = validar_configuracao(config)
    assert ok is False
    assert 'obrigatório' in mensagem.lower() or 'pendente' in mensagem.lower() or 'configuração' in mensagem.lower()


def _configuracao_cobrancas_valida():
    return {
        'cobrancas_planilha_oficial_path': r'%SAMF_PLANILHA_OFICIAL%',
        'cobrancas_planilha_aba': 'Aba configurada pelo usuário',
        'cobrancas_entrada_path': r'%SAMF_COBRANCAS_ENTRADA%',
        'cobrancas_fuso_horario': 'America/Sao_Paulo',
        'cobrancas_horario_leitura': '06:00-07:00',
        'cobrancas_dias_antecedencia': '3',
        'cobrancas_dias_vencida': '1',
        'cobrancas_valor_minimo_aviso': '0,01',
        'cobrancas_modo_operacao': 'somente_analise',
        'cobrancas_limite_diario_mensagens': '0',
        'cobrancas_intervalo_minimo_mensagens': '60',
        'cobrancas_horario_permitido_envio': '08:00-18:00',
        'cobrancas_backup_path': r'%SAMF_COBRANCAS_BACKUP%',
        'cobrancas_provedor_whatsapp': 'pendente de configuração',
        'cobrancas_status_integracao': 'pendente de configuração',
    }


def test_configuracao_cobrancas_ausente_deve_bloquear_leitura():
    from configuracao_operacional import validar_configuracao_cobrancas

    ok, mensagem = validar_configuracao_cobrancas({})
    assert ok is False
    assert 'cobranças' in mensagem.lower()


def test_configuracao_cobrancas_valida_sem_acessar_caminhos():
    from configuracao_operacional import validar_configuracao_cobrancas

    ok, mensagem = validar_configuracao_cobrancas(_configuracao_cobrancas_valida())
    assert ok is True
    assert 'válida' in mensagem.lower()


def test_envio_autorizado_sem_integracao_deve_ser_bloqueado():
    from configuracao_operacional import validar_configuracao_cobrancas

    config = _configuracao_cobrancas_valida()
    config['cobrancas_modo_operacao'] = 'envio_autorizado'
    ok, mensagem = validar_configuracao_cobrancas(config)
    assert ok is False
    assert 'integração' in mensagem.lower()


def test_modo_cobrancas_invalido_deve_ser_bloqueado():
    from configuracao_operacional import validar_configuracao_cobrancas

    config = _configuracao_cobrancas_valida()
    config['cobrancas_modo_operacao'] = 'automatico'
    ok, mensagem = validar_configuracao_cobrancas(config)
    assert ok is False
    assert 'modo' in mensagem.lower()
