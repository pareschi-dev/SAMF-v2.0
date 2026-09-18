from datetime import date
from decimal import Decimal

import pytest

from gerador_previa_cobranca import ErroPreviaCobranca, gerar_previa_cobranca


HOJE = date(2026, 8, 20)
MODELO = ('Olá, {{nome_destinatario}}. {{orgao}}/{{unidade}}: {{servico}} - {{fornecedor}}. '
          'Competência {{competencia}}, pendente {{valor_pendente}}, vencimento {{data_vencimento}}. '
          'Restam {{dias_restantes}} dia(s); atraso {{dias_em_atraso}}.')


def conta(status='PROXIMA_DO_VENCIMENTO'):
    return {'status': status, 'orgao': 'SRA', 'unidade': 'Sede', 'servico': 'Energia', 'fornecedor': 'Fornecedor A', 'competencia': '08/2026', 'valor_pendente': 125.5, 'data_vencimento': '2026-08-25'}


def destinatario():
    return {'nome': 'Ana', 'telefone': '+5511999991234', 'autorizacao_registrada': 1}


def regra(**alteracoes):
    base = {'nome': 'Regra 5 dias', 'cobrar_proximas': 1, 'cobrar_vencidas': 1, 'modelo_mensagem': MODELO}
    base.update(alteracoes)
    return base


def test_previa_contem_campos_e_telefone_mascarado():
    resultado = gerar_previa_cobranca(conta(), destinatario(), regra(), data_atual=HOJE)
    assert resultado['status'] == 'previa'
    assert resultado['destinatario'] == 'Ana'
    assert resultado['telefone_mascarado'].endswith('1234')
    assert '99999' not in resultado['telefone_mascarado']
    assert resultado['orgao'] == 'SRA'
    assert resultado['valor_pendente'] == 125.5
    assert resultado['dias_restantes'] == 5
    assert resultado['dias_em_atraso'] == 0
    assert resultado['regra_utilizada'] == 'Regra 5 dias'
    assert 'Ana' in resultado['texto']
    assert 'R$ 125,50' in resultado['texto']


def test_previa_vencida_informa_atraso():
    dados = conta('VENCIDA')
    dados['data_vencimento'] = '2026-08-15'
    resultado = gerar_previa_cobranca(dados, destinatario(), regra(), data_atual=HOJE)
    assert resultado['dias_restantes'] == 0
    assert resultado['dias_em_atraso'] == 5


def test_conta_paga_bloqueia_previa():
    with pytest.raises(ErroPreviaCobranca) as erro:
        gerar_previa_cobranca(conta('PAGA'), destinatario(), regra(), data_atual=HOJE)
    assert erro.value.codigo == 'conta_paga'


def test_regra_inaplicavel_bloqueia_previa():
    with pytest.raises(ErroPreviaCobranca) as erro:
        gerar_previa_cobranca(conta(), destinatario(), regra(cobrar_proximas=0), data_atual=HOJE)
    assert erro.value.codigo == 'regra_nao_aplicavel'


@pytest.mark.parametrize('campo', ['orgao', 'unidade', 'servico', 'fornecedor', 'competencia', 'valor_pendente', 'data_vencimento'])
def test_campo_da_conta_ausente_bloqueia_previa(campo):
    dados = conta()
    dados[campo] = None
    with pytest.raises(ErroPreviaCobranca) as erro:
        gerar_previa_cobranca(dados, destinatario(), regra(), data_atual=HOJE)
    assert erro.value.codigo == 'variavel_ausente'
    assert campo in erro.value.campos_faltantes


def test_destinatario_sem_telefone_ou_autorizacao_bloqueia():
    with pytest.raises(ErroPreviaCobranca) as erro:
        gerar_previa_cobranca(conta(), {'nome': 'Ana', 'autorizacao_registrada': 1}, regra(), data_atual=HOJE)
    assert erro.value.codigo == 'telefone_ausente'
    with pytest.raises(ErroPreviaCobranca) as erro:
        gerar_previa_cobranca(conta(), {'nome': 'Ana', 'telefone': '+5511999991234'}, regra(), data_atual=HOJE)
    assert erro.value.codigo == 'destinatario_nao_autorizado'


def test_modelo_ausente_ou_variavel_desconhecida_bloqueia():
    with pytest.raises(ErroPreviaCobranca) as erro:
        gerar_previa_cobranca(conta(), destinatario(), regra(modelo_mensagem='Olá'), data_atual=HOJE)
    assert erro.value.codigo == 'variavel_ausente_modelo'
    with pytest.raises(ErroPreviaCobranca) as erro:
        gerar_previa_cobranca(conta(), destinatario(), regra(modelo_mensagem='{{token_secreto}}'), data_atual=HOJE)
    assert erro.value.codigo == 'variavel_desconhecida'
