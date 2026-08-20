from datetime import datetime, timezone

from processador_agendado_cobrancas import ProcessadorAgendadoCobrancas


MOMENTO = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def config(modo='previa'):
    return {'cobrancas_modo_operacao': modo, 'cobrancas_fuso_horario': 'UTC', 'cobrancas_horario_execucao': '08:00-18:00', 'cobrancas_dias_semana': '0,1,2,3,4', 'cobrancas_janela_silencio': '22:00-06:00'}


def montar(configuracao, leitura=None, aplicar=None, duplicado=lambda item: False):
    eventos = {'contas': 0, 'status': 0, 'regras': 0, 'previas': 0, 'envios': 0, 'logs': []}
    processador = ProcessadorAgendadoCobrancas(
        configuracao,
        ler_planilha=lambda: leitura if leitura is not None else {'status': 'sucesso', 'linhas': [{'id': 1}]},
        atualizar_contas=lambda linhas, origem: eventos.update(contas=eventos['contas'] + len(linhas)) or {'contas': linhas},
        recalcular_status=lambda contas, cfg: eventos.update(status=eventos['status'] + len(list(contas))) or [{'id': 1}],
        aplicar_regras=lambda contas, cfg: eventos.update(regras=eventos['regras'] + len(list(contas))) or (aplicar if aplicar is not None else [{'id': 1}]),
        gerar_previa=lambda item: eventos.update(previas=eventos['previas'] + 1),
        enviar=lambda item: eventos.update(envios=eventos['envios'] + 1),
        verificar_duplicidade=duplicado,
        registrar=eventos['logs'].append,
        agora=lambda: MOMENTO,
    )
    return processador, eventos


def test_fluxo_previas_registra_contagens():
    processador, eventos = montar(config('previa'))
    resultado = processador.executar()
    assert resultado['status'] == 'concluido'
    assert resultado['quantidade_analisada'] == 1
    assert resultado['quantidade_elegivel'] == 1
    assert resultado['quantidade_previas'] == 1
    assert eventos['envios'] == 0
    assert resultado['inicio'] and resultado['fim']


def test_modo_analise_nao_gera_nem_envia():
    processador, eventos = montar(config('somente_analise'))
    resultado = processador.executar()
    assert resultado['status'] == 'concluido'
    assert resultado['quantidade_previas'] == 0
    assert eventos['envios'] == 0


def test_envio_somente_no_modo_autorizado():
    processador, eventos = montar(config('envio_autorizado'))
    resultado = processador.executar()
    assert resultado['quantidade_enviada'] == 1
    assert eventos['previas'] == 0


def test_duplicidade_impede_previa_ou_envio():
    processador, eventos = montar(config('previa'), duplicado=lambda item: True)
    resultado = processador.executar()
    assert resultado['quantidade_elegivel'] == 1
    assert resultado['quantidade_previas'] == 0
    assert eventos['envios'] == 0


def test_leitura_com_erro_interrompe_antes_de_atualizar_contas():
    processador, eventos = montar(config('previa'), leitura={'status': 'erro', 'erro': 'planilha bloqueada'})
    resultado = processador.executar()
    assert resultado['status'] == 'erro'
    assert resultado['erros'] == ['planilha bloqueada']
    assert eventos['contas'] == 0


def test_dia_fora_da_configuracao_nao_executa():
    configuracao = config('previa')
    configuracao['cobrancas_dias_semana'] = '0'
    processador, eventos = montar(configuracao)
    resultado = processador.executar()
    assert resultado['status'] == 'fora_da_janela'
    assert eventos['contas'] == 0
