from datetime import datetime, timezone

import pytest
from openpyxl import Workbook

from leitor_planilha_cobrancas import ErroLeituraPlanilha, LeitorPlanilhaCobrancas


HEADERS = [
    'Órgão', 'Unidade', 'Fornecedor', 'Serviço', 'Competência',
    'Data de vencimento', 'Valor original', 'Valor pago', 'Valor pendente',
]


def _planilha(tmp_path, rows=None, sheet='Cobrancas'):
    caminho = tmp_path / 'cobrancas.xlsx'
    workbook = Workbook()
    planilha = workbook.active
    planilha.title = sheet
    planilha.append(HEADERS)
    for row in rows or [[
        'SRA', 'Sede', 'Fornecedor A', 'Servico A', '01/2026',
        '20/01/2026', 'R$ 1.234,56', '0,00', '1.234,56',
    ]]:
        planilha.append(row)
    workbook.save(caminho)
    workbook.close()
    return caminho


def _leitor(caminho, aba='Cobrancas', loader=None):
    config = {
        'cobrancas_planilha_oficial_path': str(caminho),
        'cobrancas_planilha_aba': aba,
    }
    kwargs = {'workbook_loader': loader} if loader else {}
    return LeitorPlanilhaCobrancas(config, **kwargs)


def test_planilha_inexistente_retorna_erro_detalhado(tmp_path):
    with pytest.raises(ErroLeituraPlanilha) as erro:
        _leitor(tmp_path / 'ausente.xlsx').ler()
    assert erro.value.codigo == 'arquivo_inexistente'
    assert 'não encontrada' in erro.value.mensagem


def test_aba_inexistente_retorna_abas_disponiveis(tmp_path):
    caminho = _planilha(tmp_path)
    with pytest.raises(ErroLeituraPlanilha) as erro:
        _leitor(caminho, 'OutraAba').ler()
    assert erro.value.codigo == 'aba_inexistente'
    assert 'Cobrancas' in erro.value.detalhes['abas']


def test_coluna_ausente_informa_campo_obrigatorio(tmp_path):
    caminho = tmp_path / 'sem_coluna.xlsx'
    workbook = Workbook()
    planilha = workbook.active
    planilha.title = 'Cobrancas'
    planilha.append([header for header in HEADERS if header != 'Valor pendente'])
    workbook.save(caminho)
    workbook.close()

    with pytest.raises(ErroLeituraPlanilha) as erro:
        _leitor(caminho).ler()
    assert erro.value.codigo == 'colunas_ausentes'
    assert 'valor_pendente' in erro.value.detalhes['campos_ausentes']


def test_valor_invalido_e_data_invalida_registram_linha(tmp_path):
    caminho = _planilha(tmp_path, [[
        'SRA', 'Sede', 'Fornecedor A', 'Servico A', '01/2026',
        '31/02/2026', 'valor errado', '0,00', '100,00',
    ]])
    resultado = _leitor(caminho).ler()
    assert resultado['status'] == 'sucesso'
    assert resultado['linhas'] == []
    assert len(resultado['linhas_invalidas']) == 1
    erros = resultado['linhas_invalidas'][0]['erros']
    assert any('valor_original' in erro for erro in erros)
    assert any('data_vencimento' in erro for erro in erros)


def test_leitura_gera_previa_hash_timestamp_e_reconhece_vazios(tmp_path):
    caminho = _planilha(tmp_path, [[
        'SRA', '', 'Fornecedor A', 'Servico A', '01/2026',
        '20/01/2026', 'R$ 1.234,56', '0,00', '1.234,56',
    ]])
    momento = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    resultado = LeitorPlanilhaCobrancas(
        {
            'cobrancas_planilha_oficial_path': str(caminho),
            'cobrancas_planilha_aba': 'Cobrancas',
        },
        clock=lambda: momento,
    ).ler(limite_previa=1)
    assert len(resultado['abas']) == 1
    assert resultado['linhas'][0]['valor_original'] == 1234.56
    assert resultado['linhas'][0]['data_vencimento'] == '2026-01-20'
    assert len(resultado['previa']) == 1
    assert len(resultado['hash_origem']) == 64
    assert resultado['lida_em'] == momento.isoformat()
    assert resultado['celulas_vazias'] == [{'linha': 2, 'campos': ['unidade']}]


def test_arquivo_bloqueado_retorna_erro_detalhado(tmp_path):
    caminho = _planilha(tmp_path)

    def loader(*args, **kwargs):
        raise PermissionError('arquivo em uso')

    with pytest.raises(ErroLeituraPlanilha) as erro:
        _leitor(caminho, loader=loader).ler()
    assert erro.value.codigo == 'arquivo_bloqueado'
