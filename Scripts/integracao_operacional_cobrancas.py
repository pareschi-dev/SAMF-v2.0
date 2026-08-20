"""Fluxo operacional da planilha oficial de cobranças."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict

from auditoria_cobrancas import registrar_auditoria_cobranca
from classificador_status_contas import classificar_status_conta
from conversor_contas_cobrancas import sincronizar_contas
from leitor_planilha_cobrancas import ErroLeituraPlanilha, LeitorPlanilhaCobrancas
from mapeamento_planilha_cobrancas import ErroMapeamentoPlanilha, carregar_mapeamento_ativo, validar_mapeamento
from migracao_modelo_dados import ensure_cobrancas_tables


STATUS_AGUARDANDO_REVISAO = 'AGUARDANDO_REVISÃO'


def caminho_mapeamento(config: Dict[str, Any], raiz: str | Path | None = None) -> Path:
    valor = str(config.get('cobrancas_mapeamento_path') or '').strip()
    if not valor:
        raise ErroMapeamentoPlanilha('Caminho do mapeamento ativo não configurado.')
    caminho = Path(valor)
    if not caminho.is_absolute() and raiz is not None:
        caminho = Path(raiz) / caminho
    return caminho


def ler_planilha_operacional(
    config: Dict[str, Any],
    *,
    raiz: str | Path | None = None,
    limite_previa: int = 10,
) -> Dict[str, Any]:
    try:
        ativo = carregar_mapeamento_ativo(caminho_mapeamento(config, raiz))
        if not ativo or not isinstance(ativo.get('mapeamento'), dict):
            raise ErroMapeamentoPlanilha('Mapeamento ativo ausente ou inválido.')
        aba = str(config.get('cobrancas_planilha_aba') or '').strip()
        if str(ativo.get('aba') or '').strip() != aba:
            raise ErroMapeamentoPlanilha('Mapeamento ativo incompatível com a aba configurada.')
        resultado = LeitorPlanilhaCobrancas(config).ler(
            mapeamento=ativo['mapeamento'], limite_previa=limite_previa
        )
        resultado['mapeamento_versao'] = ativo.get('versao')
        resultado['mapeamento_arquivo'] = str(caminho_mapeamento(config, raiz))
        valido, erros = validar_mapeamento(ativo['mapeamento'], resultado['cabecalhos'].values())
        if not valido:
            raise ErroMapeamentoPlanilha('Mapeamento ativo incompatível com a planilha: ' + ' '.join(erros))
        return resultado
    except (ErroMapeamentoPlanilha, ErroLeituraPlanilha) as exc:
        return {
            'status': STATUS_AGUARDANDO_REVISAO,
            'codigo': getattr(exc, 'codigo', 'mapeamento_invalido'),
            'erro': str(exc),
            'linhas': [],
        }


def executar_integracao_planilha(
    conn: sqlite3.Connection,
    config: Dict[str, Any],
    *,
    raiz: str | Path | None = None,
    usuario: str = 'sistema',
    data_atual: date | datetime | None = None,
) -> Dict[str, Any]:
    ensure_cobrancas_tables(conn)
    leitura = ler_planilha_operacional(config, raiz=raiz)
    agora = datetime.now(timezone.utc).isoformat()
    leitura_id = _registrar_leitura(conn, leitura, agora)
    if leitura.get('status') != 'sucesso':
        registrar_auditoria_cobranca(
            conn, tipo_evento='leitura_planilha', usuario=usuario,
            status=STATUS_AGUARDANDO_REVISAO, arquivo=leitura.get('arquivo'),
            observacao=leitura.get('erro'),
        )
        conn.commit()
        return {**leitura, 'leitura_planilha_id': leitura_id}

    divergencias = _detectar_divergencias(conn, leitura['linhas'])
    sincronizado = sincronizar_contas(
        conn, leitura['linhas'], arquivo_origem=leitura['arquivo'],
        origem_hash=leitura['hash_origem'], leitura_planilha_id=leitura_id,
    )
    _recalcular_status(conn, sincronizado['contas'], config, data_atual)
    for divergencia in divergencias:
        conn.execute('''INSERT INTO divergencias_cobranca
            (conta_id, campo, valor_planilha, valor_banco, descricao)
            VALUES (?, ?, ?, ?, ?)''', (
                divergencia['conta_id'], divergencia['campo'],
                divergencia['valor_planilha'], divergencia['valor_banco'],
                'Valor da planilha diverge do valor armazenado anteriormente.',
        ))
    registrar_auditoria_cobranca(
        conn, tipo_evento='leitura_planilha', usuario=usuario, status='sucesso',
        arquivo=leitura['arquivo'], valor_novo={
            'hash_origem': leitura['hash_origem'],
            'mapeamento_versao': leitura.get('mapeamento_versao'),
            'criadas': sincronizado['criadas'],
            'atualizadas': sincronizado['atualizadas'],
            'divergencias': len(divergencias),
        },
    )
    conn.commit()
    return {
        'status': 'sucesso', 'leitura_planilha_id': leitura_id,
        'hash_origem': leitura['hash_origem'],
        'mapeamento_versao': leitura.get('mapeamento_versao'),
        'criadas': sincronizado['criadas'], 'atualizadas': sincronizado['atualizadas'],
        'duplicadas': sincronizado['duplicadas'], 'divergencias': divergencias,
        'linhas_invalidas': leitura.get('linhas_invalidas', []),
    }


def _registrar_leitura(conn, leitura: Dict[str, Any], agora: str) -> int:
    status = 'sucesso' if leitura.get('status') == 'sucesso' else 'erro'
    caminho = leitura.get('arquivo') or ''
    hash_origem = leitura.get('hash_origem') or f'erro:{agora}'
    conn.execute('''INSERT OR IGNORE INTO leituras_planilha
        (caminho_origem, aba, hash_origem, versao_origem, lida_em, status, erro)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (caminho, leitura.get('aba'), hash_origem, str(leitura.get('mapeamento_versao') or hash_origem),
         leitura.get('lida_em') or agora, status, leitura.get('erro')))
    row = conn.execute('''SELECT id FROM leituras_planilha
        WHERE caminho_origem=? AND hash_origem=? AND aba IS ?''',
        (caminho, hash_origem, leitura.get('aba'))).fetchone()
    return int(row[0])


def _detectar_divergencias(conn, linhas):
    resultado = []
    for linha in linhas:
        row = conn.execute('''SELECT id, valor_pendente, data_vencimento FROM contas
            WHERE orgao IS ? AND unidade IS ? AND fornecedor IS ? AND servico IS ?
            AND competencia IS ? AND numero_fatura IS ? LIMIT 1''',
            tuple(linha.get(campo) for campo in ('orgao', 'unidade', 'fornecedor', 'servico', 'competencia', 'numero_fatura'))).fetchone()
        if not row:
            continue
        for campo in ('valor_pendente', 'data_vencimento'):
            planilha = linha.get(campo)
            banco = row[campo]
            if planilha is not None and banco is not None and str(planilha) != str(banco):
                resultado.append({'conta_id': row['id'], 'campo': campo, 'valor_planilha': str(planilha), 'valor_banco': str(banco)})
    return resultado


def _recalcular_status(conn, contas, config, data_atual):
    hoje = data_atual or date.today()
    for item in contas:
        row = conn.execute('SELECT * FROM contas WHERE id=?', (item['conta_id'],)).fetchone()
        if not row:
            continue
        status = classificar_status_conta(
            dict(row), data_atual=hoje,
            dias_antecedencia=int(config.get('cobrancas_dias_antecedencia') or 0),
            dias_para_considerar_vencida=int(config.get('cobrancas_dias_vencida') or 0),
            divergente=False,
        )['status']
        status_db = status.replace('PRÓXIMA_DO_VENCIMENTO', 'PROXIMA_DO_VENCIMENTO').replace('AGUARDANDO_REVISÃO', 'AGUARDANDO_REVISAO')
        conn.execute('UPDATE contas SET status=?, atualizada_em=? WHERE id=?', (status_db, datetime.now(timezone.utc).isoformat(), item['conta_id']))