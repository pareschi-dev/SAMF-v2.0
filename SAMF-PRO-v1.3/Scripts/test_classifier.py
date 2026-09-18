from classifier import ClassificadorFaturas, FaturaExtraida


def _classificar(**kwargs):
    dados = {
        'nome_arquivo': 'teste.pdf',
        'fornecedor': '',
        'servico': '',
        'complemento': '',
        'endereco': '',
        'unidade': '',
        'orgao_original': '',
        'descricao': '',
        'valor': 1000.0,
        'secao': '',
    }
    dados.update(kwargs)
    return ClassificadorFaturas().classificar(FaturaExtraida(**dados))


def test_cesan_agua_compartilhado():
    resultado = _classificar(fornecedor='CESAN', servico='Água e esgoto', complemento='EDIFÍCIO-SEDE', secao='SERVIÇOS DESPESAS COMPARTILHADAS')
    assert resultado.classificacao == 'COMPARTILHADA'


def test_cesan_agua_exclusivo_estacionamento():
    resultado = _classificar(fornecedor='CESAN', servico='Água e esgoto', complemento='ESTACIONAMENTO', secao='SERVIÇOS EXCLUSIVOS')
    assert resultado.classificacao == 'EXCLUSIVA'


def test_edp_energia_compartilhado():
    resultado = _classificar(fornecedor='EDP', servico='Energia elétrica', complemento='EDIFÍCIO-SEDE', secao='SERVIÇOS DESPESAS COMPARTILHADAS')
    assert resultado.classificacao == 'COMPARTILHADA'


def test_edp_energia_exclusivo_princesa_isabel():
    resultado = _classificar(fornecedor='EDP', servico='Energia elétrica', complemento='PRINCESA ISABEL', secao='SERVIÇOS EXCLUSIVOS')
    assert resultado.classificacao == 'EXCLUSIVA'


def test_ajp_dedetizacao_compartilhado():
    resultado = _classificar(fornecedor='AJP', servico='Dedetização', complemento='EDIFÍCIO-SEDE', secao='SERVIÇOS DESPESAS COMPARTILHADAS')
    assert resultado.classificacao == 'COMPARTILHADA'


def test_ajp_dedetizacao_exclusivo_princesa_isabel():
    resultado = _classificar(fornecedor='AJP', servico='Dedetização', complemento='PRINCESA ISABEL', secao='SERVIÇOS EXCLUSIVOS')
    assert resultado.classificacao == 'EXCLUSIVA'


def test_sudeste_servico_limpeza_compartilhado():
    resultado = _classificar(fornecedor='SUDESTE', servico='Serviço de limpeza', complemento='EDIFÍCIO-SEDE', secao='SERVIÇOS DESPESAS COMPARTILHADAS')
    assert resultado.classificacao == 'COMPARTILHADA'


def test_sudeste_limpeza_higienizacao_exclusivo():
    resultado = _classificar(fornecedor='SUDESTE', servico='Limpeza e higienização', complemento='UNIDADE', secao='SERVIÇOS EXCLUSIVOS')
    assert resultado.classificacao == 'EXCLUSIVA'


def test_maxima_telefonista_compartilhado():
    resultado = _classificar(fornecedor='MÁXIMA', servico='Telefonista', complemento='GERAL', secao='SERVIÇOS DESPESAS COMPARTILHADAS')
    assert resultado.classificacao == 'COMPARTILHADA'


def test_maxima_aux_admin_exclusivo_vitoria():
    resultado = _classificar(fornecedor='MÁXIMA', servico='Auxiliar administrativo', complemento='VITÓRIA', secao='SERVIÇOS EXCLUSIVOS')
    assert resultado.classificacao == 'EXCLUSIVA'


def test_vivo_fixo_compartilhado():
    resultado = _classificar(fornecedor='VIVO', servico='VIVO FIXO', complemento='GERAL', secao='SERVIÇOS DESPESAS COMPARTILHADAS')
    assert resultado.classificacao == 'COMPARTILHADA'


def test_vivo_fixo_pabx_exclusivo():
    resultado = _classificar(fornecedor='VIVO', servico='VIVO FIXO', complemento='PABX', secao='SERVIÇOS EXCLUSIVOS')
    assert resultado.classificacao == 'EXCLUSIVA'


def test_fornecedor_ambiguous_sem_complemento_revisao():
    resultado = _classificar(fornecedor='AJP', servico='Dedetização', complemento='', secao='SERVIÇOS DESPESAS COMPARTILHADAS')
    assert resultado.classificacao == 'AGUARDANDO_REVISÃO'


def test_servico_desconhecido_revisao():
    resultado = _classificar(fornecedor='FORNECEDOR X', servico='Desconhecido', complemento='X', secao='SERVIÇOS EXCLUSIVOS')
    assert resultado.classificacao == 'AGUARDANDO_REVISÃO'


def test_retorno_de_revisao_tem_detalhes_operacionais():
    resultado = _classificar(fornecedor='CESAN', servico='Água e esgoto', complemento='', secao='SERVIÇOS DESPESAS COMPARTILHADAS')
    dados = resultado.as_dict()
    assert dados['classificacao'] == 'AGUARDANDO_REVISÃO'
    assert dados['confianca'] < 0.95
    assert dados['evidencias']
    assert dados['possiveis_alternativas']
    assert dados['motivo_revisao']
