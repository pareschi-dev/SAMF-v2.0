import sqlite3
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / 'samf.db'

ORGAOS_OFICIAIS = [
    'SRA',
    'DRF',
    'PFN',
    'PSFN',
    'SPU',
    'CGU',
    'BB',
    'SERPRO',
    'ABIN',
    'ALFÂNDEGA',
    'SRT',
    'AGU (PF)',
    'AGU (CJU)',
    'AGU (PU)',
    'FUNDACENTRO',
    'ASSEFAZ',
    'IBGE',
]

SECOES_OFICIAIS = [
    ('SERVIÇOS DESPESAS COMPARTILHADAS', 1),
    ('SERVIÇOS EXCLUSIVOS', 2),
]

PLANILHA_CONFIG = [
    {
        'servico': '',
        'fornecedor': '',
        'complemento': '',
        'secao': '',
        'competencia': '',
        'coluna_orgao': '',
        'linha_correspondente': '',
        'regra_calculo': '',
        'situacao': 'pendente',
    }
]


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def ensure_secoes_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS secoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            ordem INTEGER NOT NULL UNIQUE,
            ativa INTEGER NOT NULL DEFAULT 1,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')


def ensure_planilha_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS configuracao_planilha (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            servico TEXT,
            fornecedor TEXT,
            complemento TEXT,
            secao TEXT,
            competencia TEXT,
            coluna_orgao TEXT,
            linha_correspondente TEXT,
            regra_calculo TEXT,
            situacao TEXT NOT NULL DEFAULT 'pendente',
            ativa INTEGER NOT NULL DEFAULT 1,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(servico, fornecedor, complemento, secao, competencia, coluna_orgao, linha_correspondente)
        )
    ''')


def seed_orgaos(conn):
    if not ORGAOS_OFICIAIS:
        return

    for ordem, nome in enumerate(ORGAOS_OFICIAIS, start=1):
        existing = conn.execute(
            "SELECT id FROM orgaos WHERE nome = ?",
            (nome,),
        ).fetchone()

        if existing:
            continue

        next_ordem = conn.execute(
            "SELECT COALESCE(MAX(ordem), 0) + 1 FROM orgaos"
        ).fetchone()[0]

        conn.execute(
            '''
            INSERT INTO orgaos (nome, ordem, sigla, tipo, codigo, ativo, atualizado_em)
            VALUES (?, ?, ?, 'orgao', ?, 1, CURRENT_TIMESTAMP)
            ''',
            (nome, next_ordem, nome, str(next_ordem)),
        )


def seed_secoes(conn):
    if not SECOES_OFICIAIS:
        return

    for nome, ordem in SECOES_OFICIAIS:
        existing = conn.execute(
            "SELECT id FROM secoes WHERE nome = ?",
            (nome,),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE secoes SET ordem = ?, ativa = 1 WHERE id = ?",
                (ordem, existing['id']),
            )
        else:
            conn.execute(
                '''
                INSERT INTO secoes (nome, ordem, ativa)
                VALUES (?, ?, 1)
                ''',
                (nome, ordem),
            )


def seed_planilha_placeholder(conn):
    conn.execute(
        '''
        INSERT OR IGNORE INTO configuracao_planilha (
            servico, fornecedor, complemento, secao, competencia, coluna_orgao,
            linha_correspondente, regra_calculo, situacao, ativa
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        ('', '', '', '', '', '', '', '', 'pendente', 0),
    )


def main():
    conn = connect_db()
    try:
        ensure_secoes_table(conn)
        ensure_planilha_table(conn)
        seed_orgaos(conn)
        seed_secoes(conn)
        seed_planilha_placeholder(conn)
        conn.commit()
        print('Cadastros oficiais concluídos com sucesso.')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
