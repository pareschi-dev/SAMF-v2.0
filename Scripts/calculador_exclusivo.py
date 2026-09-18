"""Cálculo validado de despesas exclusivas, sem persistência ou lançamento."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, Optional


CENTAVO = Decimal('0.01')


@dataclass(frozen=True)
class BeneficiarioExclusivo:
    orgao: str
    orgao_id: Optional[int] = None


@dataclass(frozen=True)
class RegraExclusiva:
    nome: str
    fornecedor: str
    servico: str
    beneficiario: Optional[BeneficiarioExclusivo]
    complemento: Optional[str] = None
    unidade: Optional[str] = None
    endereco: Optional[str] = None
    secao: str = 'SERVIÇOS EXCLUSIVOS'
    regra_id: Optional[int] = None
    origem: str = 'fonte oficial'


class CalculadorDespesaExclusiva:
    """Atribui 100% somente quando a regra e o beneficiário estão confirmados."""

    def calcular(self, fatura: Dict[str, Any], regra: Optional[RegraExclusiva], orgaos: Iterable[Any]) -> Dict[str, Any]:
        valor_base = _decimal(fatura.get('valor_base', fatura.get('valor_total')))
        if str(fatura.get('classificacao', '')).strip().upper() != 'EXCLUSIVA':
            return self._revisao('A fatura não está classificada como EXCLUSIVA.', valor_base, regra)
        if valor_base is None or valor_base < 0:
            return self._revisao('Valor-base ausente ou inválido.', valor_base, regra)
        if regra is None:
            return self._revisao('Regra oficial de despesa exclusiva não localizada.', valor_base)
        if not regra.beneficiario or not regra.beneficiario.orgao:
            return self._revisao('Beneficiário ausente na regra oficial.', valor_base, regra)

        evidencias, motivo = self._confirmar_contexto(fatura, regra)
        if motivo:
            return self._revisao(motivo, valor_base, regra, evidencias)

        lista_orgaos = [_normalizar_orgao(item) for item in orgaos]
        nomes_orgaos = {item['nome_normalizado'] for item in lista_orgaos}
        beneficiario_normalizado = _normalizar(regra.beneficiario.orgao)
        if not lista_orgaos or beneficiario_normalizado not in nomes_orgaos:
            return self._revisao('Beneficiário não encontrado entre os órgãos oficiais.', valor_base, regra, evidencias)

        valor_formatado = _formatar(valor_base)
        parcelas = [
            {
                'orgao': item['nome'],
                'orgao_id': item.get('orgao_id'),
                'percentual': '100.00' if item['nome_normalizado'] == beneficiario_normalizado else '0.00',
                'valor': valor_formatado if item['nome_normalizado'] == beneficiario_normalizado else '0.00',
            }
            for item in lista_orgaos
        ]
        evidencias.append(f'Beneficiário oficial confirmado: {regra.beneficiario.orgao}.')
        return {
            'status': 'CALCULADO_VALIDADO',
            'classificacao': 'EXCLUSIVA',
            'valor_base': valor_formatado,
            'beneficiario': {'orgao': regra.beneficiario.orgao, 'orgao_id': regra.beneficiario.orgao_id},
            'parcelas': parcelas,
            'soma_parcelas': valor_formatado,
            'regra': {'id': regra.regra_id, 'nome': regra.nome, 'origem': regra.origem},
            'evidencias': evidencias,
            'valido': True,
            'motivos_revisao': [],
        }

    @staticmethod
    def _confirmar_contexto(fatura: Dict[str, Any], regra: RegraExclusiva) -> tuple[list[str], Optional[str]]:
        evidencias = [f'Regra oficial: {regra.nome}.']
        for campo in ('fornecedor', 'servico'):
            esperado = _normalizar(getattr(regra, campo))
            recebido = _normalizar(fatura.get(campo))
            if not esperado or esperado not in recebido:
                return evidencias, f'{campo.capitalize()} da fatura não confirma a regra oficial.'
            evidencias.append(f'{campo.capitalize()} confirmado: {fatura.get(campo)}.')

        for campo in ('complemento', 'unidade', 'endereco'):
            esperado = _normalizar(getattr(regra, campo))
            if esperado:
                recebido = _normalizar(fatura.get(campo))
                if not recebido or esperado not in recebido:
                    return evidencias, f'{campo.capitalize()} ausente, ambíguo ou divergente da regra oficial.'
                evidencias.append(f'{campo.capitalize()} confirmado: {fatura.get(campo)}.')
        return evidencias, None

    @staticmethod
    def _revisao(motivo: str, valor_base: Optional[Decimal], regra: Optional[RegraExclusiva], evidencias=None) -> Dict[str, Any]:
        return {
            'status': 'AGUARDANDO_REVISÃO',
            'classificacao': 'EXCLUSIVA',
            'valor_base': _formatar(valor_base),
            'beneficiario': None if not regra or not regra.beneficiario else {'orgao': regra.beneficiario.orgao, 'orgao_id': regra.beneficiario.orgao_id},
            'parcelas': [],
            'soma_parcelas': '0.00',
            'regra': None if not regra else {'id': regra.regra_id, 'nome': regra.nome, 'origem': regra.origem},
            'evidencias': evidencias or [],
            'valido': False,
            'motivos_revisao': [motivo],
        }


def calcular_despesa_exclusiva(fatura: Dict[str, Any], regra: Optional[RegraExclusiva], orgaos: Iterable[Any]) -> Dict[str, Any]:
    return CalculadorDespesaExclusiva().calcular(fatura, regra, orgaos)


def _normalizar(texto: Any) -> str:
    if texto is None:
        return ''
    texto = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', texto).strip().upper()


def _normalizar_orgao(orgao: Any) -> Dict[str, Any]:
    if isinstance(orgao, dict):
        nome = str(orgao.get('nome', '')).strip()
        return {'nome': nome, 'nome_normalizado': _normalizar(nome), 'orgao_id': orgao.get('id', orgao.get('orgao_id'))}
    nome = str(orgao).strip()
    return {'nome': nome, 'nome_normalizado': _normalizar(nome), 'orgao_id': None}


def _decimal(valor: Any) -> Optional[Decimal]:
    if valor is None or valor == '':
        return None
    try:
        return Decimal(str(valor).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None


def _formatar(valor: Optional[Decimal]) -> Optional[str]:
    return None if valor is None else format(valor.quantize(CENTAVO, rounding=ROUND_HALF_UP), '.2f')