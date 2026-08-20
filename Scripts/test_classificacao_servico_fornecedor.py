import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'samf.db')


def _fetch_rows():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT servico, fornecedor, complemento, secao, tipo, exigencia_analise, ativo
            FROM regras_classificacao
            WHERE ativo = 1
            ORDER BY id
            """
        )
        return cur.fetchall()
    finally:
        conn.close()


def test_regras_compartilhadas_cadastradas():
    rows = _fetch_rows()
    assert any(
        row['servico'] == 'Água e esgoto' and row['fornecedor'] == 'CESAN' and row['tipo'] == 'compartilhado'
        for row in rows
    )
    assert any(
        row['servico'] == 'Energia elétrica' and row['fornecedor'] == 'EDP' and row['tipo'] == 'compartilhado'
        for row in rows
    )


def test_regras_exclusivas_cadastradas_e_analise_obrigatoria():
    rows = _fetch_rows()
    assert any(
        row['servico'] == 'Água e esgoto'
        and row['fornecedor'] == 'CESAN'
        and row['complemento'] == 'ESTACIONAMENTO'
        and row['tipo'] == 'exclusivo'
        and row['secao'] == 'SERVIÇOS EXCLUSIVOS'
        for row in rows
    )
    assert any(
        row['servico'] == 'Auxiliar administrativo'
        and row['fornecedor'] == 'MÁXIMA'
        and row['tipo'] == 'exclusivo'
        and row['exigencia_analise'] in {'complemento', 'complemento_e_secao'}
        for row in rows
    )
    assert any(
        row['fornecedor'] in {'CESAN', 'P.M.V.', 'AJP', 'EDP', 'MÁXIMA', 'SUDESTE', 'JCA', 'VIVO', 'SEI'}
        and row['exigencia_analise'] in {'complemento', 'complemento_e_secao'}
        for row in rows
    )
