import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / 'samf.db'

SHARED_RULES = [
    ('Água e esgoto', 'CESAN', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'complemento_e_secao'),
    ('Aluguéis + taxas (IPTU)', 'P.M.V.', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'complemento_e_secao'),
    ('Combustível de gerador', 'ACX - STAR GREEN', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'nenhuma'),
    ('Dedetização', 'AJP', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'complemento_e_secao'),
    ('Energia elétrica', 'EDP', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'complemento_e_secao'),
    ('Manutenção de ar-condicionado central', 'PGE', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'nenhuma'),
    ('Manutenção central de alarme', 'PREVIEW', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'nenhuma'),
    ('Manutenção de elevadores', 'ELEVADORES MILÊNIO', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'nenhuma'),
    ('Manutenção de jardins', 'ANATOVI/SUDESTE', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'complemento_e_secao'),
    ('Manutenção predial', 'PGE', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'nenhuma'),
    ('Manutenção de telefonia', 'ROTACIONAL - DND', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'nenhuma'),
    ('Manutenção de vídeo-monitoramento', 'PREVIEW', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'nenhuma'),
    ('Serviço de limpeza', 'SUDESTE', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'complemento_e_secao'),
    ('Telefonia fixa', 'VIVO (FIXO)', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'complemento_e_secao'),
    ('Telefonia móvel', 'JCA (MÓVEL)', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'complemento_e_secao'),
    ('Telefonista', 'MÁXIMA', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'complemento_e_secao'),
    ('Vigilância/segurança', 'SEI', '', 'SERVIÇOS DESPESAS COMPARTILHADAS', 'compartilhado', 'complemento_e_secao'),
]

EXCLUSIVE_RULES = [
    ('Água e esgoto', 'BRK', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
    ('Água e esgoto', 'CESAN', 'ESTACIONAMENTO', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Água e esgoto', 'SAAE', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
    ('Aluguéis + taxas (IPTU)', 'P.M.V.', 'UNIDADE ESPECÍFICA', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Auxiliar de informática', 'MÁXIMA', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Avaliação de imóveis', 'SAFIRA ENGENHARIA - SILVA', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
    ('Avaliação de insalubridade', 'RESULT', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
    ('Combustível', 'LINK CARD', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
    ('Copeiragem', 'MÁXIMA', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Correios', 'ECT', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
    ('Dedetização', 'AJP', 'PRINCESA ISABEL', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Energia elétrica', 'EDP', 'PRINCESA ISABEL', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Energia elétrica', 'LUZ E FORÇA SANTA MARIA', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
    ('Limpeza e higienização', 'SUDESTE', 'UNIDADE', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Locação de equipamentos', 'ALLGED', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
    ('Locação de imóveis', 'SRT', 'TAXA CONDOMINIAL/ALUGUEL', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Manutenção de veículos', 'XP3 - HALF', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
    ('Material de consumo', 'MAT. CONSUMO', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
    ('Motorista', 'MÁXIMA', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Publicidade legal', 'EBC', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
    ('Auxiliar administrativo', 'MÁXIMA', 'VITÓRIA', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Auxiliar administrativo', 'MÁXIMA', 'CACHOEIRO', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Auxiliar administrativo', 'MÁXIMA', 'COLATINA', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Auxiliar administrativo', 'MÁXIMA', 'VILA VELHA', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Telefonia', 'VIVO (FIXO - PABX)', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'complemento_e_secao'),
    ('Vigilância eletrônica', 'AGUIAR & MANTOVANI', '', 'SERVIÇOS EXCLUSIVOS', 'exclusivo', 'nenhuma'),
]

RULES = SHARED_RULES + EXCLUSIVE_RULES


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def ensure_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS regras_classificacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            servico TEXT,
            fornecedor TEXT,
            complemento TEXT,
            secao TEXT,
            tipo TEXT CHECK(tipo IN ('compartilhado', 'exclusivo')) NOT NULL,
            exigencia_analise TEXT NOT NULL DEFAULT 'nenhuma',
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(servico, fornecedor, complemento, secao, tipo)
        )
    ''')

    for column_name, column_sql in [
        ('servico', 'TEXT'),
        ('fornecedor', 'TEXT'),
        ('complemento', 'TEXT'),
        ('secao', 'TEXT'),
        ('tipo', "TEXT CHECK(tipo IN ('compartilhado', 'exclusivo'))"),
        ('exigencia_analise', "TEXT NOT NULL DEFAULT 'nenhuma'"),
        ('ativo', 'INTEGER NOT NULL DEFAULT 1'),
        ('atualizado_em', 'DATETIME DEFAULT CURRENT_TIMESTAMP'),
    ]:
        columns = conn.execute(f'PRAGMA table_info(regras_classificacao)').fetchall()
        if not any(col[1] == column_name for col in columns):
            conn.execute(f'ALTER TABLE regras_classificacao ADD COLUMN {column_name} {column_sql}')


def seed_rules(conn):
    for servico, fornecedor, complemento, secao, tipo, exigencia in RULES:
        existing = conn.execute(
            "SELECT id FROM regras_classificacao WHERE servico = ? AND fornecedor = ? AND complemento = ? AND secao = ? AND tipo = ?",
            (servico, fornecedor, complemento, secao, tipo),
        ).fetchone()

        nome = f'{servico} | {fornecedor} | {complemento or "GERAL"} | {secao}'

        if existing:
            conn.execute(
                '''
                UPDATE regras_classificacao
                SET nome = ?, exigencia_analise = ?, ativo = 1, atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (nome, exigencia, existing['id']),
            )
        else:
            conn.execute(
                '''
                INSERT INTO regras_classificacao (nome, servico, fornecedor, complemento, secao, tipo, exigencia_analise, ativo, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                ''',
                (nome, servico, fornecedor, complemento, secao, tipo, exigencia),
            )


def main():
    conn = connect_db()
    try:
        ensure_table(conn)
        seed_rules(conn)
        conn.commit()
        print('Cadastro da classificação oficial concluído com sucesso.')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
