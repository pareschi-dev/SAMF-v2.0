"""Prevenção de mensagens duplicadas para cobranças."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


ENVIADAS = {'enviado', 'entregue'}
PENDENTES = {'previa', 'aguardando_aprovacao', 'aprovado'}


def verificar_duplicidade(
    conn,
    *,
    conta_id: int,
    destinatario_id: int,
    regra_id: int,
    competencia: str,
    tipo_alerta: str,
    valor_pendente: float | None,
    data_vencimento: str | None,
    intervalo_minimo_segundos: int,
    agora: datetime | None = None,
) -> Dict[str, Any]:
    """Consulta duplicidade e cancela pendentes quando a conta foi paga."""
    agora = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    conta = conn.execute('SELECT valor_pendente, status FROM contas WHERE id=?', (conta_id,)).fetchone()
    if not conta:
        return {'permitido': False, 'codigo': 'conta_nao_encontrada', 'canceladas': 0}
    if _paga(conta):
        canceladas = conn.execute("""UPDATE mensagens SET status='cancelado', erro='Conta paga antes do envio'
            WHERE conta_id=? AND destinatario_id=? AND regra_id=? AND competencia=? AND tipo_alerta=?
            AND status IN ('previa', 'aguardando_aprovacao', 'aprovado')""",
            (conta_id, destinatario_id, regra_id, competencia, tipo_alerta)).rowcount
        conn.commit()
        return {'permitido': False, 'codigo': 'conta_paga', 'canceladas': canceladas}

    mensagens = conn.execute("""SELECT id, status, criada_em, enviada_em, valor_pendente_referencia, data_vencimento_referencia
        FROM mensagens WHERE conta_id=? AND destinatario_id=? AND regra_id=? AND competencia=? AND tipo_alerta=?
        ORDER BY id DESC""", (conta_id, destinatario_id, regra_id, competencia, tipo_alerta)).fetchall()
    houve_alteracao = any(_diferente(row['valor_pendente_referencia'], valor_pendente) or row['data_vencimento_referencia'] != data_vencimento for row in mensagens)
    for mensagem in mensagens:
        status = str(mensagem['status'] or '').lower()
        referencia = mensagem['enviada_em'] or mensagem['criada_em']
        if not houve_alteracao and status in ENVIADAS:
            if _dentro_intervalo(referencia, agora, intervalo_minimo_segundos):
                return {'permitido': False, 'codigo': 'mensagem_enviada_no_intervalo', 'mensagem_id': mensagem['id'], 'canceladas': 0}
        if not houve_alteracao and status in PENDENTES:
            return {'permitido': False, 'codigo': 'mensagem_pendente', 'mensagem_id': mensagem['id'], 'canceladas': 0}

    return {'permitido': True, 'codigo': 'alteracao_detectada' if houve_alteracao else 'sem_duplicidade', 'canceladas': 0}


def _paga(conta) -> bool:
    try:
        return str(conta['status'] or '').upper() == 'PAGA' or float(conta['valor_pendente']) == 0
    except (TypeError, ValueError):
        return False


def _diferente(anterior, atual) -> bool:
    if anterior is None or atual is None:
        return False
    try:
        return abs(float(anterior) - float(atual)) > 0.000001
    except (TypeError, ValueError):
        return str(anterior) != str(atual)


def _dentro_intervalo(referencia, agora, intervalo):
    if not referencia:
        return False
    try:
        momento = datetime.fromisoformat(str(referencia).replace('Z', '+00:00'))
        if momento.tzinfo is None:
            momento = momento.replace(tzinfo=timezone.utc)
        return (agora - momento.astimezone(timezone.utc)).total_seconds() < max(0, int(intervalo))
    except (TypeError, ValueError):
        return False
