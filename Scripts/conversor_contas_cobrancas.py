"""Conversao idempotente de linhas lidas em contas de cobrancas."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, Iterable


CAMPOS_CHAVE = (
    'orgao',
    'unidade',
    'fornecedor',
    'servico',
    'competencia',
    'numero_fatura',
    'data_vencimento',
    'valor_original',
)


def sincronizar_contas(
    conn: sqlite3.Connection,
    linhas: Iterable[Dict[str, Any]],
    *,
    arquivo_origem: str,
    origem_hash: str,
    leitura_planilha_id: int | None = None,
    agora: datetime | None = None,
) -> Dict[str, Any]:
    """Cria ou atualiza contas sem enviar mensagens ou ler a planilha."""
    instante = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    resultados: list[Dict[str, Any]] = []
    ids_processados: set[str] = set()
    criadas = atualizadas = duplicadas = 0

    for linha in linhas:
        chave = _chave_conta(linha)
        if not chave:
            continue
        identificador = _identificador(chave)
        if identificador in ids_processados:
            duplicadas += 1
            continue
        ids_processados.add(identificador)
        dados = _dados_conta(linha, identificador, arquivo_origem, origem_hash, leitura_planilha_id, instante)
        existente = conn.execute('SELECT id FROM contas WHERE identificador=?', (identificador,)).fetchone()
        if not existente:
            existente = conn.execute(
                """SELECT id FROM contas WHERE orgao IS ? AND unidade IS ? AND fornecedor IS ?
                AND servico IS ? AND competencia IS ? AND numero_fatura IS ?""",
                (linha.get('orgao'), linha.get('unidade'), linha.get('fornecedor'), linha.get('servico'), linha.get('competencia'), linha.get('numero_fatura')),
            ).fetchone()
        if existente:
            conn.execute(
                """UPDATE contas SET fatura_id=?, arquivo_origem=?, fornecedor=?, servico=?, orgao=?, unidade=?,
                numero_fatura=?, responsavel=?, competencia=?, data_emissao=?, data_vencimento=?, valor_original=?,
                valor_pago=?, valor_pendente=?, telefone_destinatario=?, origem_planilha=?, origem_hash=?,
                leitura_planilha_id=?, atualizada_em=?, identificador=? WHERE id=?""",
                (dados[1], dados[2], dados[3], dados[4], dados[5], dados[6], dados[7], dados[8], dados[9], dados[10],
                 dados[11], dados[12], dados[13], dados[14], dados[16], dados[17], dados[18], dados[19], dados[20], dados[0], existente[0]),
            )
            conta_id = existente[0]
            atualizadas += 1
            acao = 'atualizada'
        else:
            conn.execute(
                """INSERT INTO contas (identificador, fatura_id, arquivo_origem, fornecedor, servico, orgao, unidade,
                numero_fatura, responsavel, competencia, data_emissao, data_vencimento, valor_original, valor_pago, valor_pendente,
                status, telefone_destinatario, origem_planilha, origem_hash, leitura_planilha_id, atualizada_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                dados,
            )
            conta_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            criadas += 1
            acao = 'criada'
        resultados.append({'conta_id': conta_id, 'identificador': identificador, 'acao': acao})

    conn.commit()
    return {
        'status': 'sucesso',
        'criadas': criadas,
        'atualizadas': atualizadas,
        'duplicadas': duplicadas,
        'contas': resultados,
        'origem_hash': origem_hash,
    }


def _chave_conta(linha: Dict[str, Any]) -> tuple[str, ...] | None:
    valor_chave = linha.get('valor_original')
    if valor_chave is None:
        valor_chave = linha.get('valor_pendente')
    valores = tuple(_normalizar(linha.get(campo)) for campo in CAMPOS_CHAVE[:-1]) + (_normalizar(valor_chave),)
    if not valores[0] or not valores[2] or not valores[3] or not valores[4] or not valores[6] or not valores[7]:
        return None
    return valores


def _identificador(chave: tuple[str, ...]) -> str:
    payload = json.dumps(chave, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _dados_conta(linha: Dict[str, Any], identificador: str, arquivo_origem: str, origem_hash: str, leitura_id: int | None, instante: str) -> tuple[Any, ...]:
    valor_pendente = linha.get('valor_pendente')
    if valor_pendente is None and linha.get('valor_original') is not None and linha.get('valor_pago') is not None:
        valor_pendente = float(linha['valor_original']) - float(linha['valor_pago'])
    status = 'PAGA' if valor_pendente == 0 else 'PENDENTE'
    return (
        identificador,
        linha.get('fatura_id'),
        arquivo_origem,
        linha.get('fornecedor'),
        linha.get('servico'),
        linha.get('orgao'),
        linha.get('unidade'),
        linha.get('numero_fatura'),
        linha.get('responsavel'),
        linha.get('competencia'),
        linha.get('data_emissao'),
        linha.get('data_vencimento'),
        linha.get('valor_original'),
        linha.get('valor_pago'),
        valor_pendente,
        status,
        linha.get('telefone_destinatario'),
        arquivo_origem,
        origem_hash,
        leitura_id,
        instante,
    )


def _normalizar(valor: Any) -> str:
    texto = unicodedata.normalize('NFKD', str(valor or '')).encode('ascii', 'ignore').decode('ascii')
    return ' '.join(texto.upper().split())
