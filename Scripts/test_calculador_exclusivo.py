from decimal import Decimal

from calculador_exclusivo import BeneficiarioExclusivo, CalculadorDespesaExclusiva, RegraExclusiva


ORGAOS = [{'id': 1, 'nome': 'SRA'}, {'id': 2, 'nome': 'DRF'}, {'id': 3, 'nome': 'CGU'}]


def _regra(beneficiario=True, complemento='ESTACIONAMENTO'):
    return RegraExclusiva(
        nome='CESAN | Água e esgoto | Estacionamento',
        fornecedor='CESAN',
        servico='Água e esgoto',
        complemento=complemento,
        beneficiario=BeneficiarioExclusivo('SRA', 1) if beneficiario else None,
    )


def _fatura(**alteracoes):
    fatura = {
        'classificacao': 'EXCLUSIVA',
        'valor_base': '125.37',
        'fornecedor': 'CESAN',
        'servico': 'Água e esgoto',
        'complemento': 'ESTACIONAMENTO LESTE',
        'unidade': 'Unidade SRA',
        'endereco': 'Rua Principal, 10',
    }
    fatura.update(alteracoes)
    return fatura


def test_beneficiario_identificado_recebe_cem_porcento():
    resultado = CalculadorDespesaExclusiva().calcular(_fatura(), _regra(), ORGAOS)

    assert resultado['status'] == 'CALCULADO_VALIDADO'
    assert resultado['beneficiario']['orgao'] == 'SRA'
    assert resultado['parcelas'][0]['percentual'] == '100.00'
    assert resultado['parcelas'][0]['valor'] == '125.37'
    assert all(parcela['valor'] == '0.00' for parcela in resultado['parcelas'][1:])
    assert resultado['soma_parcelas'] == '125.37'
    assert resultado['evidencias']


def test_beneficiario_ausente_vai_para_revisao():
    resultado = CalculadorDespesaExclusiva().calcular(_fatura(), _regra(beneficiario=False), ORGAOS)

    assert resultado['status'] == 'AGUARDANDO_REVISÃO'
    assert 'Beneficiário ausente' in resultado['motivos_revisao'][0]
    assert resultado['parcelas'] == []


def test_complemento_ambiguo_vai_para_revisao():
    resultado = CalculadorDespesaExclusiva().calcular(_fatura(complemento=''), _regra(), ORGAOS)

    assert resultado['status'] == 'AGUARDANDO_REVISÃO'
    assert 'Complemento' in resultado['motivos_revisao'][0]


def test_fornecedor_em_duas_categorias_exige_regra_contextual():
    regra = _regra(complemento='PRINCESA ISABEL')
    resultado = CalculadorDespesaExclusiva().calcular(_fatura(complemento=''), regra, ORGAOS)

    assert resultado['status'] == 'AGUARDANDO_REVISÃO'
    assert resultado['parcelas'] == []
    assert 'Complemento' in resultado['motivos_revisao'][0]


def test_valor_decimal_e_preservado_na_parcela_exclusiva():
    resultado = CalculadorDespesaExclusiva().calcular(_fatura(valor_base=Decimal('0.01')), _regra(), ORGAOS)

    assert resultado['parcelas'][0]['valor'] == '0.01'
    assert sum(Decimal(parcela['valor']) for parcela in resultado['parcelas']) == Decimal('0.01')