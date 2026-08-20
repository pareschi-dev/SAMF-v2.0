import sqlite3
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

EXPECTED_ORGAOS = [
    "SRA",
    "DRF",
    "PFN",
    "PSFN",
    "SPU",
    "CGU",
    "BB",
    "SERPRO",
    "ABIN",
    "ALFÂNDEGA",
    "SRT",
    "AGU (PF)",
    "AGU (CJU)",
    "AGU (PU)",
    "FUNDACENTRO",
    "ASSEFAZ",
    "IBGE",
]

EXPECTED_SECOES = [
    "SERVIÇOS DESPESAS COMPARTILHADAS",
    "SERVIÇOS EXCLUSIVOS",
]


def test_orgaos_oficiais_cadastrados_uma_vez():
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), '..', 'samf.db'))
    cur = conn.cursor()

    cur.execute("SELECT nome FROM orgaos")
    nomes = {row[0] for row in cur.fetchall()}

    for nome in EXPECTED_ORGAOS:
        assert nomes.__contains__(nome), f"Órgão ausente: {nome}"

    for nome in EXPECTED_ORGAOS:
        count = cur.execute("SELECT COUNT(*) FROM orgaos WHERE nome = ?", (nome,)).fetchone()[0]
        assert count == 1, f"Órgão duplicado: {nome} ({count})"

    conn.close()


def test_secoes_oficiais_cadastradas_uma_vez():
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), '..', 'samf.db'))
    cur = conn.cursor()

    cur.execute("SELECT nome FROM secoes")
    nomes = {row[0] for row in cur.fetchall()}

    for nome in EXPECTED_SECOES:
        assert nomes.__contains__(nome), f"Seção ausente: {nome}"

    for nome in EXPECTED_SECOES:
        count = cur.execute("SELECT COUNT(*) FROM secoes WHERE nome = ?", (nome,)).fetchone()[0]
        assert count == 1, f"Seção duplicada: {nome} ({count})"

    conn.close()
