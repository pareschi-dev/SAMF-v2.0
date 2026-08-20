import csv
import io
import json
import os
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font


TIPOS = {
    'faturas': 'Todas as faturas',
    'compartilhadas': 'Faturas compartilhadas',
    'exclusivas': 'Faturas exclusivas',
    'revisao': 'Faturas em revisão',
    'lancamentos_competencia': 'Lançamentos por competência',
    'lancamentos_orgao': 'Lançamentos por órgão',
    'divergencias': 'Divergências',
    'auditoria': 'Auditoria',
}
MOEDA = '[$R$-pt-BR] #,##0.00'


def _tabela_existe(conn, nome):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone() is not None


def _valor(valor):
    return Decimal(str(valor or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _faturas(conn, tipo, competencia=None):
    filtro = []
    valores = []
    if tipo == 'compartilhadas':
        filtro.append("UPPER(COALESCE(f.classificacao, '')) IN ('COMPARTILHADA', 'COMPARTILHADO')")
    elif tipo == 'exclusivas':
        filtro.append("UPPER(COALESCE(f.classificacao, '')) IN ('EXCLUSIVA', 'EXCLUSIVO')")
    elif tipo == 'revisao':
        filtro.append("UPPER(COALESCE(f.classificacao, f.status, '')) IN ('REVISAO', 'REVISÃO', 'AGUARDANDO_REVISAO', 'AGUARDANDO_REVISÃO')")
    if competencia:
        filtro.append("COALESCE(f.competencia, strftime('%Y-%m', f.criado_em)) = ?")
        valores.append(competencia)
    where = (' WHERE ' + ' AND '.join(filtro)) if filtro else ''
    return conn.execute(f'''
        SELECT f.id, f.nome_arquivo AS arquivo,
               UPPER(COALESCE(f.classificacao, 'SEM_CLASSIFICACAO')) AS classificacao,
               COALESCE(f.competencia, strftime('%Y-%m', f.criado_em)) AS competencia,
               COALESCE(NULLIF(f.fornecedor, ''), f.fornecedor_extraido, '') AS fornecedor,
               COALESCE(NULLIF(f.servico, ''), s.nome, '') AS servico,
               COALESCE(f.orgao_beneficiario, '') AS orgao,
               COALESCE(f.status, '') AS status,
               COALESCE(f.valor_base, f.valor_total, 0) AS valor
        FROM faturas f LEFT JOIN servicos s ON s.id = f.servico_id
        {where} ORDER BY f.criado_em DESC, f.id DESC
    ''', valores).fetchall()


def dataset(conn, tipo, competencia=None, orgao=None):
    if tipo not in TIPOS:
        raise ValueError('Tipo de exportação inválido.')
    if tipo in {'faturas', 'compartilhadas', 'exclusivas', 'revisao'}:
        rows = _faturas(conn, tipo, competencia)
        headers = ['Arquivo', 'Classificação', 'Competência', 'Fornecedor', 'Serviço', 'Órgão', 'Status', 'Valor']
        data = [[r['arquivo'], r['classificacao'], r['competencia'], r['fornecedor'], r['servico'], r['orgao'], r['status'], float(_valor(r['valor']))] for r in rows]
        return headers, data, sum((_valor(r['valor']) for r in rows), Decimal('0.00')), 'valor'
    if tipo.startswith('lancamentos_'):
        where, values = [], []
        if competencia:
            where.append("COALESCE(f.competencia, strftime('%Y-%m', f.criado_em)) = ?"); values.append(competencia)
        if orgao:
            where.append('UPPER(o.nome) = UPPER(?)'); values.append(orgao)
        clause = (' WHERE ' + ' AND '.join(where)) if where else ''
        rows = conn.execute(f'''
            SELECT f.nome_arquivo AS arquivo, UPPER(COALESCE(f.classificacao, '')) AS classificacao,
                   COALESCE(f.competencia, strftime('%Y-%m', f.criado_em)) AS competencia,
                   COALESCE(NULLIF(f.fornecedor, ''), f.fornecedor_extraido, '') AS fornecedor,
                   COALESCE(NULLIF(f.servico, ''), s.nome, '') AS servico, o.nome AS orgao,
                   COALESCE(f.status, '') AS status, r.percentual, r.valor_rateio AS valor
            FROM rateios_calculados r JOIN faturas f ON f.id = r.fatura_id
            LEFT JOIN servicos s ON s.id = f.servico_id JOIN orgaos o ON o.id = r.orgao_id
            {clause} ORDER BY competencia, o.ordem, f.id
        ''', values).fetchall()
        headers = ['Arquivo', 'Classificação', 'Competência', 'Fornecedor', 'Serviço', 'Órgão', 'Status', 'Percentual', 'Valor']
        data = [[r['arquivo'], r['classificacao'], r['competencia'], r['fornecedor'], r['servico'], r['orgao'], r['status'], r['percentual'], float(_valor(r['valor']))] for r in rows]
        return headers, data, sum((_valor(r['valor']) for r in rows), Decimal('0.00')), 'valor'
    if tipo == 'divergencias':
        if not _tabela_existe(conn, 'divergencias'):
            return ['Arquivo', 'Classificação', 'Competência', 'Fornecedor', 'Serviço', 'Órgão', 'Status', 'Tipo', 'Descrição', 'Valor esperado', 'Valor obtido'], [], Decimal('0.00'), None
        rows = conn.execute('''
            SELECT f.nome_arquivo AS arquivo, UPPER(COALESCE(f.classificacao, '')) AS classificacao,
                   COALESCE(f.competencia, strftime('%Y-%m', f.criado_em)) AS competencia,
                   COALESCE(NULLIF(f.fornecedor, ''), f.fornecedor_extraido, '') AS fornecedor,
                   COALESCE(NULLIF(f.servico, ''), s.nome, '') AS servico,
                   COALESCE(f.orgao_beneficiario, '') AS orgao, COALESCE(f.status, '') AS status,
                   d.tipo_divergencia, d.descricao, d.valor_esperado, d.valor_obtido
            FROM divergencias d JOIN faturas f ON f.id=d.fatura_id LEFT JOIN servicos s ON s.id=f.servico_id
            ORDER BY d.criado_em DESC
        ''').fetchall()
        headers = ['Arquivo', 'Classificação', 'Competência', 'Fornecedor', 'Serviço', 'Órgão', 'Status', 'Tipo', 'Descrição', 'Valor esperado', 'Valor obtido']
        data = [[r['arquivo'], r['classificacao'], r['competencia'], r['fornecedor'], r['servico'], r['orgao'], r['status'], r['tipo_divergencia'], r['descricao'], float(_valor(r['valor_esperado'])), float(_valor(r['valor_obtido']))] for r in rows]
        return headers, data, sum((_valor(r['valor_obtido']) for r in rows), Decimal('0.00')), 'valor_obtido'
    rows = conn.execute('''
        SELECT a.*, UPPER(COALESCE(f.classificacao, '')) AS classificacao,
               COALESCE(f.competencia, strftime('%Y-%m', f.criado_em)) AS competencia,
               COALESCE(NULLIF(f.fornecedor, ''), f.fornecedor_extraido, '') AS fornecedor,
               COALESCE(NULLIF(f.servico, ''), s.nome, '') AS servico,
               COALESCE(f.orgao_beneficiario, '') AS orgao,
               COALESCE(f.status, a.status, '') AS status_fatura
        FROM auditoria_eventos a
        LEFT JOIN faturas f ON f.id = a.fatura_id
        LEFT JOIN servicos s ON s.id = f.servico_id
        ORDER BY a.data_hora DESC, a.id DESC
    ''') if _tabela_existe(conn, 'auditoria_eventos') else []
    headers = ['Arquivo', 'Classificação', 'Competência', 'Fornecedor', 'Serviço', 'Órgão', 'Status', 'Tipo de evento', 'Usuário', 'Data e hora', 'Valor anterior', 'Valor novo', 'Observação']
    data = [[r['arquivo'] or '', r['classificacao'] or '', r['competencia'] or '', r['fornecedor'] or '', r['servico'] or '', r['orgao'] or '', r['status_fatura'] or '', r['tipo_evento'], r['usuario'], r['data_hora'], r['valor_anterior'] or '', r['valor_novo'] or '', r['observacao'] or ''] for r in rows]
    return headers, data, Decimal('0.00'), None


def resumo_exportacao(conn, tipo, competencia=None, orgao=None):
    headers, data, total, campo = dataset(conn, tipo, competencia, orgao)
    return {'tipo': tipo, 'quantidade': len(data), 'total_exibido': f'{total:.2f}', 'total_exportado': f'{total:.2f}', 'campo_total': campo, 'valido': True}


def _csv_bytes(headers, data):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, delimiter=';', lineterminator='\r\n')
    writer.writerow(headers)
    for row in data:
        writer.writerow([f'{item:.2f}'.replace('.', ',') if isinstance(item, float) else item for item in row])
    return ('\ufeff' + stream.getvalue()).encode('utf-8')


def gerar_exportacao(conn, tipo, formato, destino, competencia=None, orgao=None):
    headers, data, total, _ = dataset(conn, tipo, competencia, orgao)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    if formato == 'csv':
        Path(destino).write_bytes(_csv_bytes(headers, data))
    elif formato == 'xlsx':
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = TIPOS[tipo][:31]
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in data:
            sheet.append(row)
        for index, header in enumerate(headers, 1):
            if 'valor' in header.lower():
                for cell in sheet.iter_cols(min_col=index, max_col=index, min_row=2):
                    for item in cell:
                        item.number_format = MOEDA
        workbook.save(destino)
    else:
        raise ValueError('Formato inválido. Use xlsx ou csv.')
    return {'arquivo': destino, 'quantidade': len(data), 'total_exibido': f'{total:.2f}', 'total_exportado': f'{total:.2f}', 'valido': True}
