"""Cálculo validado de despesas compartilhadas, sem persistência ou lançamento."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional


CENTAVO = Decimal('0.01')
PERCENTUAL_TOLERANCIA = Decimal('0.01')


@dataclass(frozen=True)
class ParticipanteRateio:
    orgao: str
    percentual: Optional[Decimal] = None
    valor_fixo: Optional[Decimal] = None
    orgao_id: Optional[int] = None


@dataclass(frozen=True)
class RegraRateio:
    nome: str
    participantes: tuple[ParticipanteRateio, ...]
    origem: str = 'fonte oficial'
    regra_id: Optional[int] = None


class FonteRegrasSQLite:
    """Localiza a regra legada oficial sem alterar o banco."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def localizar_regra(self, servico: str, fornecedor: str) -> Optional[RegraRateio]:
        linha_servico = self.connection.execute(
            'SELECT id, nome, padrao FROM servicos WHERE UPPER(nome) = UPPER(?) AND UPPER(fornecedor) = UPPER(?) LIMIT 1',
            (servico, fornecedor),
        ).fetchone()
        if not linha_servico:
            return None

        participantes = self.connection.execute(
            '''
            SELECT p.orgao_id, o.nome, p.percentual
            FROM padroes_rateio p
            JOIN orgaos o ON o.id = p.orgao_id
            WHERE p.nome = ?
            ORDER BY o.ordem
            ''',
            (linha_servico[2],),
        ).fetchall()
        return RegraRateio(
            nome=f'{linha_servico[1]} | padrão {linha_servico[2]}',
            origem='servicos + padroes_rateio + orgaos',
            participantes=tuple(
                ParticipanteRateio(orgao=row[1], percentual=_decimal(row[2]), orgao_id=row[0])
                for row in participantes
            ),
        )


class CalculadorRateioCompartilhado:
    def calcular(self, fatura: Dict[str, Any], regra: Optional[RegraRateio]) -> Dict[str, Any]:
        valor_base = _decimal(fatura.get('valor_base', fatura.get('valor_total')))
        classificacao = str(fatura.get('classificacao', '')).strip().upper()
        if classificacao != 'COMPARTILHADA':
            return self._revisao('A fatura não está classificada como COMPARTILHADA.', valor_base)
        if valor_base is None or valor_base < 0:
            return self._revisao('Valor-base ausente ou inválido.', valor_base)
        if regra is None:
            return self._revisao('Regra oficial de rateio não localizada.', valor_base)
        if not regra.participantes:
            return self._revisao('Regra oficial sem órgãos participantes.', valor_base, regra)

        for participante in regra.participantes:
            if not participante.orgao or (participante.percentual is None and participante.valor_fixo is None):
                return self._revisao('Falta órgão ou percentual/valor de participante.', valor_base, regra)
            if participante.percentual is not None and participante.percentual < 0:
                return self._revisao('Percentual inválido na regra oficial.', valor_base, regra)
            if participante.valor_fixo is not None and participante.valor_fixo < 0:
                return self._revisao('Valor fixo inválido na regra oficial.', valor_base, regra)

        tem_percentuais = any(item.percentual is not None for item in regra.participantes)
        tem_valores = any(item.valor_fixo is not None for item in regra.participantes)
        if tem_percentuais and tem_valores:
            return self._revisao('Regra mistura percentuais e valores fixos.', valor_base, regra)

        if tem_percentuais:
            total_percentual = sum((item.percentual for item in regra.participantes), Decimal('0'))
            if abs(total_percentual - Decimal('100')) > PERCENTUAL_TOLERANCIA:
                return self._revisao(f'Percentuais somam {total_percentual}%, diferente de 100%.', valor_base, regra)
            valores = [valor_base * _decimal(item.percentual) / Decimal('100') for item in regra.participantes]
        else:
            total_fixo = sum((item.valor_fixo for item in regra.participantes), Decimal('0'))
            if abs(total_fixo - valor_base) > CENTAVO:
                return self._revisao(f'Valores fixos somam {total_fixo}, diferente do valor-base.', valor_base, regra)
            valores = [_decimal(item.valor_fixo) for item in regra.participantes]

        parcelas = [
            {
                'orgao': item.orgao,
                'orgao_id': item.orgao_id,
                'percentual': _format_decimal(item.percentual),
                'valor': _format_decimal(valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)),
            }
            for item, valor in zip(regra.participantes, valores)
        ]
        soma_arredondada = sum((Decimal(item['valor']) for item in parcelas), Decimal('0'))
        residual = valor_base.quantize(CENTAVO, rounding=ROUND_HALF_UP) - soma_arredondada
        if residual and parcelas:
            parcelas[-1]['valor'] = _format_decimal(Decimal(parcelas[-1]['valor']) + residual)
            soma_arredondada += residual

        valido = soma_arredondada == valor_base.quantize(CENTAVO, rounding=ROUND_HALF_UP)
        resultado = {
            'status': 'CALCULADO_VALIDADO' if valido else 'AGUARDANDO_REVISÃO',
            'classificacao': 'COMPARTILHADA',
            'valor_base': _format_decimal(valor_base),
            'parcelas': parcelas,
            'soma_parcelas': _format_decimal(soma_arredondada),
            'residual': _format_decimal(residual),
            'regra': {'id': regra.regra_id, 'nome': regra.nome, 'origem': regra.origem},
            'valido': valido,
            'motivos_revisao': [] if valido else ['Soma das parcelas divergente do valor-base.'],
        }
        return resultado

    @staticmethod
    def _revisao(motivo: str, valor_base: Optional[Decimal], regra: Optional[RegraRateio] = None) -> Dict[str, Any]:
        return {
            'status': 'AGUARDANDO_REVISÃO',
            'classificacao': 'COMPARTILHADA',
            'valor_base': _format_decimal(valor_base),
            'parcelas': [],
            'soma_parcelas': '0.00',
            'residual': None,
            'regra': {'id': regra.regra_id, 'nome': regra.nome, 'origem': regra.origem} if regra else None,
            'valido': False,
            'motivos_revisao': [motivo],
        }


def calcular_rateio_compartilhado(fatura: Dict[str, Any], regra: Optional[RegraRateio]) -> Dict[str, Any]:
    return CalculadorRateioCompartilhado().calcular(fatura, regra)


def _decimal(valor: Any) -> Optional[Decimal]:
    if valor is None or valor == '':
        return None
    try:
        return Decimal(str(valor).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None


def _format_decimal(valor: Optional[Decimal]) -> Optional[str]:
    valor_decimal = _decimal(valor)
    return None if valor_decimal is None else format(valor_decimal.quantize(CENTAVO, rounding=ROUND_HALF_UP), '.2f')