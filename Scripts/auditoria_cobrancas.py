"""Registro e consulta append-only da auditoria de cobranças."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict


def registrar_auditoria_cobranca(
    conn,
    *,
    tipo_evento: str,
    usuario: str,
    registro_id: int | None = None,
    status: str | None = None,
    arquivo: str | None = None,
    orgao: str | None = None,
    valor_anterior: Any = None,
    valor_novo: Any = None,
    observacao: str | None = None,
    origem: str = 'sistema',
    data_hora: datetime | None = None,
) -> int:
    """Registra um evento sem permitir exclusão silenciosa."""
    instante = (data_hora or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    cur = conn.execute('''INSERT INTO auditoria_cobranca
        (tabela_origem, registro_id, acao, usuario, dados_anterior, dados_novo, valor_anterior, valor_novo, origem,
         observacao, arquivo_origem, orgao, status, tipo_evento, criada_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        ('cobrancas', registro_id, tipo_evento, usuario, _json(valor_anterior), _json(valor_novo), _json(valor_anterior),
         _json(valor_novo), origem, observacao, arquivo, orgao, status, tipo_evento, instante))
    return cur.lastrowid


def listar_auditoria(conn, filtros: Dict[str, Any] | None = None, limite: int = 500) -> list[Dict[str, Any]]:
    filtros = filtros or {}
    where, valores = [], []
    for campo in ('usuario', 'arquivo_origem', 'orgao', 'status', 'tipo_evento'):
        if filtros.get(campo):
            where.append(f"LOWER(COALESCE({campo}, '')) LIKE LOWER(?)")
            valores.append(f"%{filtros[campo]}%")
    if filtros.get('data_inicio'):
        where.append('criada_em >= ?'); valores.append(filtros['data_inicio'] + 'T00:00:00')
    if filtros.get('data_fim'):
        where.append('criada_em <= ?'); valores.append(filtros['data_fim'] + 'T23:59:59')
    query = 'SELECT * FROM auditoria_cobranca'
    if where: query += ' WHERE ' + ' AND '.join(where)
    query += ' ORDER BY criada_em DESC, id DESC LIMIT ?'
    rows = conn.execute(query, (*valores, min(max(int(limite), 1), 1000))).fetchall()
    return [dict(row) for row in rows]


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, default=str) if valor is not None else None
