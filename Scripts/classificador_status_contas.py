"""Classificacao deterministica do status de contas, sem efeitos colaterais."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict


STATUS_PAGA = 'PAGA'
STATUS_PENDENTE = 'PENDENTE'
STATUS_PROXIMA = 'PRÓXIMA_DO_VENCIMENTO'
STATUS_VENCIDA = 'VENCIDA'
STATUS_SEM_DATA = 'SEM_DATA_DE_VENCIMENTO'
STATUS_SEM_VALOR = 'SEM_VALOR'
STATUS_DIVERGENTE = 'DIVERGENTE'
STATUS_REVISAO = 'AGUARDANDO_REVISÃO'


def classificar_status_conta(
    conta: Dict[str, Any],
    *,
    data_atual: date | datetime,
    dias_antecedencia: int = 0,
    dias_para_considerar_vencida: int = 0,
    divergente: bool = False,
    requer_revisao: bool = False,
) -> Dict[str, Any]:
    """Retorna status e se a conta pode originar aviso.

    A função não grava dados, lê planilhas ou envia mensagens.
    """
    if requer_revisao:
        status = STATUS_REVISAO
    else:
        valor, valor_valido = _decimal(conta.get('valor_pendente'))
        if not valor_valido:
            status = STATUS_SEM_VALOR
        else:
            vencimento, data_valida = _data(conta.get('data_vencimento'))
            if not data_valida:
                status = STATUS_SEM_DATA
            elif divergente:
                status = STATUS_DIVERGENTE
            elif valor == 0:
                status = STATUS_PAGA
            elif valor < 0:
                status = STATUS_SEM_VALOR
            else:
                hoje = _data_atual(data_atual)
                limite_vencida = vencimento + timedelta(days=max(0, int(dias_para_considerar_vencida)))
                limite_proxima = hoje + timedelta(days=max(0, int(dias_antecedencia)))
                if hoje > limite_vencida:
                    status = STATUS_VENCIDA
                elif vencimento <= limite_proxima:
                    status = STATUS_PROXIMA
                else:
                    status = STATUS_PENDENTE

    return {
        'status': status,
        'pode_gerar_aviso': status not in {STATUS_PAGA, STATUS_SEM_VALOR, STATUS_SEM_DATA, STATUS_DIVERGENTE, STATUS_REVISAO},
    }


def _decimal(valor: Any) -> tuple[Decimal | None, bool]:
    if valor is None or isinstance(valor, bool):
        return None, False
    try:
        texto = str(valor).strip().replace('R$', '').replace(' ', '')
        if ',' in texto:
            texto = texto.replace('.', '').replace(',', '.')
        resultado = Decimal(texto)
        return resultado, resultado.is_finite()
    except (InvalidOperation, ValueError):
        return None, False


def _data(valor: Any) -> tuple[date | None, bool]:
    if isinstance(valor, datetime):
        return valor.date(), True
    if isinstance(valor, date):
        return valor, True
    texto = str(valor or '').strip()
    for formato in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(texto, formato).date(), True
        except ValueError:
            continue
    return None, False


def _data_atual(valor: date | datetime) -> date:
    return valor.date() if isinstance(valor, datetime) else valor
