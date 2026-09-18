"""Configuracao versionada do mapeamento da planilha de cobrancas."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from leitor_planilha_cobrancas import CAMPOS, LeitorPlanilhaCobrancas


CAMPOS_MAPEAVEIS = (
    'orgao',
    'unidade',
    'fornecedor',
    'servico',
    'competencia',
    'numero_fatura',
    'data_vencimento',
    'valor_original',
    'valor_pago',
    'valor_pendente',
    'responsavel',
    'telefone_destinatario',
    'observacao',
)


class ErroMapeamentoPlanilha(ValueError):
    def __init__(self, mensagem: str, erros: Iterable[str] = ()) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.erros = list(erros)


def validar_mapeamento(mapeamento: Dict[str, str], cabecalhos: Iterable[str]) -> tuple[bool, list[str]]:
    cabecalhos_normalizados = {_normalizar(cabecalho) for cabecalho in cabecalhos}
    erros: list[str] = []
    for campo, cabecalho in mapeamento.items():
        if campo not in CAMPOS_MAPEAVEIS:
            erros.append(f'Campo de mapeamento desconhecido: {campo}.')
        elif not str(cabecalho or '').strip():
            erros.append(f'Campo sem coluna selecionada: {campo}.')
        elif _normalizar(cabecalho) not in cabecalhos_normalizados:
            erros.append(f'Coluna não encontrada na planilha: {cabecalho}.')

    if not mapeamento.get('orgao') and not mapeamento.get('responsavel'):
        erros.append('Mapeie órgão ou responsável.')
    if not mapeamento.get('data_vencimento'):
        erros.append('Mapeie a coluna de vencimento.')
    if not mapeamento.get('valor_pendente') and not (mapeamento.get('valor_original') and mapeamento.get('valor_pago')):
        erros.append('Mapeie valor pendente ou valor original e valor pago.')
    return not erros, erros


def inspecionar_mapeamento(config: Dict[str, Any], limite_previa: int = 10) -> Dict[str, Any]:
    """Retorna cabecalhos e previa para o usuario montar o mapeamento."""
    return LeitorPlanilhaCobrancas(config).inspecionar(limite_previa=limite_previa)


def salvar_mapeamento(
    caminho_arquivo: str | os.PathLike[str],
    mapeamento: Dict[str, str],
    cabecalhos: Iterable[str],
    usuario: str,
    aba: str,
    observacoes: str = '',
    agora: datetime | None = None,
) -> Dict[str, Any]:
    if not str(usuario or '').strip():
        raise ErroMapeamentoPlanilha('Usuário obrigatório para salvar o mapeamento.')
    valido, erros = validar_mapeamento(mapeamento, cabecalhos)
    if not valido:
        raise ErroMapeamentoPlanilha('Mapeamento inválido; análise bloqueada.', erros)
    caminho = Path(caminho_arquivo)
    historico = _ler_historico(caminho)
    versao = max((int(item.get('versao', 0)) for item in historico), default=0) + 1
    instante = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    registro = {
        'versao': versao,
        'aba': aba,
        'mapeamento': {campo: mapeamento[campo] for campo in CAMPOS_MAPEAVEIS if campo in mapeamento},
        'observacoes': observacoes,
        'usuario': usuario,
        'alterado_em': instante,
        'ativo': True,
    }
    historico = [{**item, 'ativo': False} for item in historico]
    historico.append(registro)
    payload = {'versao_ativa': versao, 'historico': historico}
    _salvar_atomico(caminho, payload)
    return registro


def carregar_mapeamento_ativo(caminho_arquivo: str | os.PathLike[str]) -> Dict[str, Any] | None:
    historico = _ler_historico(Path(caminho_arquivo))
    return next((item for item in reversed(historico) if item.get('ativo')), None)


def _ler_historico(caminho: Path) -> list[Dict[str, Any]]:
    if not caminho.exists():
        return []
    try:
        payload = json.loads(caminho.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErroMapeamentoPlanilha(f'Arquivo de mapeamento inválido: {exc}') from exc
    historico = payload.get('historico', []) if isinstance(payload, dict) else []
    if not isinstance(historico, list):
        raise ErroMapeamentoPlanilha('Histórico de mapeamento inválido.')
    return historico


def _salvar_atomico(caminho: Path, payload: Dict[str, Any]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=caminho.parent, delete=False) as arquivo:
            temporario = Path(arquivo.name)
            json.dump(payload, arquivo, ensure_ascii=False, indent=2)
            arquivo.write('\n')
        os.replace(temporario, caminho)
    finally:
        if temporario and temporario.exists():
            temporario.unlink()


def _normalizar(valor: Any) -> str:
    import unicodedata
    texto = unicodedata.normalize('NFKD', str(valor or '')).encode('ascii', 'ignore').decode('ascii')
    return ' '.join(texto.upper().split())
