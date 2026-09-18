from datetime import datetime, timezone

import pytest
from openpyxl import Workbook

from mapeamento_planilha_cobrancas import (
    ErroMapeamentoPlanilha,
    carregar_mapeamento_ativo,
    inspecionar_mapeamento,
    salvar_mapeamento,
    validar_mapeamento,
)


HEADERS = ['Órgão', 'Unidade', 'Fornecedor', 'Serviço', 'Competência', 'Vencimento', 'Valor original', 'Valor pago', 'Valor pendente', 'Responsável']


def _planilha(tmp_path):
    caminho = tmp_path / 'oficial.xlsx'
    workbook = Workbook()
    planilha = workbook.active
    planilha.title = 'Oficial'
    planilha.append(HEADERS)
    planilha.append(['SRA', 'Sede', 'Fornecedor', 'Servico', '01/2026', '20/01/2026', '100,00', '0,00', '100,00', 'Responsavel'])
    workbook.save(caminho)
    workbook.close()
    return caminho


def _mapeamento():
    return {
        'orgao': 'Órgão',
        'unidade': 'Unidade',
        'fornecedor': 'Fornecedor',
        'servico': 'Serviço',
        'competencia': 'Competência',
        'data_vencimento': 'Vencimento',
        'valor_original': 'Valor original',
        'valor_pago': 'Valor pago',
        'valor_pendente': 'Valor pendente',
        'responsavel': 'Responsável',
    }


def test_previa_exibe_cabecalhos_e_linhas(tmp_path):
    resultado = inspecionar_mapeamento({
        'cobrancas_planilha_oficial_path': str(_planilha(tmp_path)),
        'cobrancas_planilha_aba': 'Oficial',
    }, limite_previa=1)
    assert resultado['cabecalhos'] == HEADERS
    assert resultado['previa'][0]['linha'] == 2
    assert resultado['previa'][0]['valores'][0] == 'SRA'


def test_mapeamento_bloqueia_sem_orgao_ou_responsavel():
    mapeamento = _mapeamento()
    del mapeamento['orgao']
    del mapeamento['responsavel']
    valido, erros = validar_mapeamento(mapeamento, HEADERS)
    assert valido is False
    assert any('órgão ou responsável' in erro for erro in erros)


def test_mapeamento_bloqueia_sem_vencimento_e_valores_necessarios():
    mapeamento = _mapeamento()
    del mapeamento['data_vencimento']
    del mapeamento['valor_pendente']
    del mapeamento['valor_original']
    valido, erros = validar_mapeamento(mapeamento, HEADERS)
    assert valido is False
    assert any('vencimento' in erro for erro in erros)
    assert any('valor pendente' in erro for erro in erros)


def test_salva_versoes_usuario_data_e_mapeamento_ativo(tmp_path):
    caminho = tmp_path / 'mapeamento.json'
    agora = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    primeira = salvar_mapeamento(caminho, _mapeamento(), HEADERS, 'usuario-teste', 'Oficial', 'primeira', agora)
    segunda = salvar_mapeamento(caminho, _mapeamento(), HEADERS, 'usuario-teste-2', 'Oficial', 'segunda', agora)
    ativo = carregar_mapeamento_ativo(caminho)
    assert primeira['versao'] == 1
    assert segunda['versao'] == 2
    assert ativo['versao'] == 2
    assert ativo['usuario'] == 'usuario-teste-2'
    assert ativo['alterado_em'] == agora.isoformat()


def test_salvar_mapeamento_invalido_nao_cria_arquivo(tmp_path):
    caminho = tmp_path / 'mapeamento.json'
    with pytest.raises(ErroMapeamentoPlanilha):
        salvar_mapeamento(caminho, {}, HEADERS, 'usuario-teste', 'Oficial')
    assert not caminho.exists()
