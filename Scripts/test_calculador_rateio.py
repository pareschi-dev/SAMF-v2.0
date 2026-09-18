from decimal import Decimal

from calculador_rateio import CalculadorRateioCompartilhado, ParticipanteRateio, RegraRateio


def _regra(*participantes):
    return RegraRateio('regra oficial de teste', tuple(participantes), origem='teste')


def test_rateio_fecha_com_percentuais():
    regra = _regra(
        ParticipanteRateio('SRA', Decimal('60')),
        ParticipanteRateio('DRF', Decimal('40')),
    )

    resultado = CalculadorRateioCompartilhado().calcular(
        {'classificacao': 'COMPARTILHADA', 'valor_base': '1000.00'}, regra
    )

    assert resultado['status'] == 'CALCULADO_VALIDADO'
    assert [parcela['valor'] for parcela in resultado['parcelas']] == ['600.00', '400.00']
    assert resultado['soma_parcelas'] == '1000.00'
    assert resultado['valido'] is True


def test_rateio_controla_residual_de_arredondamento():
    regra = _regra(
        ParticipanteRateio('SRA', Decimal('33.33')),
        ParticipanteRateio('DRF', Decimal('33.33')),
        ParticipanteRateio('CGU', Decimal('33.34')),
    )

    resultado = CalculadorRateioCompartilhado().calcular(
        {'classificacao': 'COMPARTILHADA', 'valor_base': '10.00'}, regra
    )

    assert resultado['status'] == 'CALCULADO_VALIDADO'
    assert resultado['soma_parcelas'] == '10.00'
    assert sum(Decimal(parcela['valor']) for parcela in resultado['parcelas']) == Decimal('10.00')
    assert resultado['residual'] == '0.01'
    assert resultado['parcelas'][-1]['valor'] == '3.34'


def test_percentual_ausente_envia_para_revisao():
    regra = _regra(
        ParticipanteRateio('SRA', None),
        ParticipanteRateio('DRF', Decimal('40')),
    )

    resultado = CalculadorRateioCompartilhado().calcular(
        {'classificacao': 'COMPARTILHADA', 'valor_base': '100.00'}, regra
    )

    assert resultado['status'] == 'AGUARDANDO_REVISÃO'
    assert 'percentual/valor' in resultado['motivos_revisao'][0]
    assert resultado['parcelas'] == []


def test_total_divergente_envia_para_revisao():
    regra = _regra(
        ParticipanteRateio('SRA', Decimal('60')),
        ParticipanteRateio('DRF', Decimal('30')),
    )

    resultado = CalculadorRateioCompartilhado().calcular(
        {'classificacao': 'COMPARTILHADA', 'valor_base': '100.00'}, regra
    )

    assert resultado['status'] == 'AGUARDANDO_REVISÃO'
    assert '100%' in resultado['motivos_revisao'][0]


def test_orgao_ausente_envia_para_revisao():
    regra = _regra(ParticipanteRateio('', Decimal('100')))

    resultado = CalculadorRateioCompartilhado().calcular(
        {'classificacao': 'COMPARTILHADA', 'valor_base': '100.00'}, regra
    )

    assert resultado['status'] == 'AGUARDANDO_REVISÃO'
    assert 'órgão' in resultado['motivos_revisao'][0]