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
