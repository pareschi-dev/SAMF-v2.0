from usuarios import PERFIS


PERMISSOES = {
    'visualizar_cobrancas',
    'editar_regras_cobranca',
    'cadastrar_destinatarios_cobranca',
    'gerar_previas_cobranca',
    'aprovar_mensagens_cobranca',
    'enviar_mensagens_cobranca',
    'consultar_historico_cobranca',
    'alterar_integracao_cobranca',
}


def test_todos_os_perfis_existentes_foram_avaliados():
    assert set(PERFIS) == {'visualizador', 'operador', 'aprovador', 'administrador'}
    for perfil, permissoes in PERFIS.items():
        assert isinstance(permissoes, set), perfil


def test_todos_visualizam_cobrancas_e_historico():
    for perfil in PERFIS:
        assert 'visualizar_cobrancas' in PERFIS[perfil], perfil
        assert 'consultar_historico_cobranca' in PERFIS[perfil], perfil


def test_operador_pode_gerar_previa_mas_nao_aprovar_ou_enviar():
    assert 'gerar_previas_cobranca' in PERFIS['operador']
    assert 'aprovar_mensagens_cobranca' not in PERFIS['operador']
    assert 'enviar_mensagens_cobranca' not in PERFIS['operador']


def test_aprovador_pode_aprovar_mas_nao_enviar_ou_alterar_regras():
    assert 'gerar_previas_cobranca' in PERFIS['aprovador']
    assert 'aprovar_mensagens_cobranca' in PERFIS['aprovador']
    assert 'enviar_mensagens_cobranca' not in PERFIS['aprovador']
    assert 'editar_regras_cobranca' not in PERFIS['aprovador']


def test_visualizador_nao_altera_dados_operacionais():
    assert not PERFIS['visualizador'] & {
        'editar_regras_cobranca', 'cadastrar_destinatarios_cobranca',
        'aprovar_mensagens_cobranca', 'enviar_mensagens_cobranca',
        'alterar_integracao_cobranca',
    }


def test_administrador_tem_permissao_especifica_de_envio_e_integracao():
    assert PERMISSOES <= PERFIS['administrador']
