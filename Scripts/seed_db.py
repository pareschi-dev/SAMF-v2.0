import sqlite3
import os
import sys

# Adiciona o diretório atual ao path para importar db.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_connection

PADRAO_A = {
    "SRA": 15.45, "SRT": 10.66, "AGU (PF)": 13.36, "AGU (CJU)": 4.56, "AGU (PU)": 9.04,
    "SPU": 13.67, "CGU": 9.04, "SERPRO": 0.72, "ABIN": 4.48, "DRF": 3.68,
    "PFN": 4.55, "FUNDACENTRO": 0.93, "ASSEFAZ": 0.81, "IBGE": 9.04
}

PADRAO_B = {
    "SRA": 17.72, "SRT": 37.34, "AGU (PF)": 0.00, "AGU (CJU)": 0.00, "AGU (PU)": 0.00,
    "SPU": 34.18, "CGU": 0.00, "SERPRO": 1.27, "ABIN": 5.70, "DRF": 0.63,
    "PFN": 0.00, "FUNDACENTRO": 0.63, "ASSEFAZ": 2.53, "IBGE": 0.00
}

SERVICOS = [
    {"nome": "ÁGUA E ESGOTO", "fornecedor": "CESAN", "padrao": "A"},
    {"nome": "ALUGUÉIS + TAXAS (IPTU)", "fornecedor": "P.M.V.", "padrao": "A"},
    {"nome": "COMBUSTÍVEL - GERADOR", "fornecedor": "STAR GREEN", "padrao": "A"},
    {"nome": "DEDETIZAÇÃO", "fornecedor": "AJP", "padrao": "A"},
    {"nome": "ENERGIA ELÉTRICA", "fornecedor": "EDP", "padrao": "A"},
    {"nome": "MANUTENÇÃO AR CONDICIONADO (CENTRAL)", "fornecedor": "PGE", "padrao": "A"},
    {"nome": "MANUTENÇÃO CENTRAL DE ALARME", "fornecedor": "PREVIEW", "padrao": "A"},
    {"nome": "MANUTENÇÃO ELEVADORES", "fornecedor": "ELEVADORES MILÊNIO", "padrao": "A"},
    {"nome": "MANUTENÇÃO JARDINS", "fornecedor": "SUDESTE", "padrao": "A"},
    {"nome": "MANUTENÇÃO PREDIAL", "fornecedor": "PGE", "padrao": "A"},
    {"nome": "MANUTENÇÃO TELEFONIA", "fornecedor": "DND", "padrao": "B"},
    {"nome": "MANUTENÇÃO VÍDEO-MONITORAMENTO", "fornecedor": "PREVIEW", "padrao": "A"},
    {"nome": "SERVIÇO DE LIMPEZA", "fornecedor": "SUDESTE", "padrao": "A"},
    {"nome": "TELEFONIA (VIVO FIXO)", "fornecedor": "VIVO (FIXO)", "padrao": "B"},
    {"nome": "TELEFONIA (JCA MÓVEL)", "fornecedor": "JCA (MÓVEL)", "padrao": "B"},
    {"nome": "TELEFONISTA", "fornecedor": "MÁXIMA", "padrao": "B"},
    {"nome": "VIGILÂNCIA/SEGURANÇA", "fornecedor": "SEI", "padrao": "A"}
]

def seed():
    # Primeiro, garantir que as tabelas existam
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    conn = get_connection()
    with open(schema_path, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    
    cur = conn.cursor()
    
    # Limpar padrões e serviços para reinserir
    cur.execute("DELETE FROM padroes_rateio")
    cur.execute("DELETE FROM servicos")
    
    # Buscar IDs dos órgãos
    cur.execute("SELECT id, nome FROM orgaos")
    orgaos = {row['nome']: row['id'] for row in cur.fetchall()}
    
    # Inserir Padrão A
    for nome, pct in PADRAO_A.items():
        cur.execute("INSERT INTO padroes_rateio (nome, orgao_id, percentual) VALUES (?, ?, ?)",
                   ('A', orgaos[nome], pct))
    
    # Inserir Padrão B
    for nome, pct in PADRAO_B.items():
        cur.execute("INSERT INTO padroes_rateio (nome, orgao_id, percentual) VALUES (?, ?, ?)",
                   ('B', orgaos[nome], pct))
                   
    # Inserir Serviços
    for s in SERVICOS:
        cur.execute("""INSERT INTO servicos (nome, fornecedor, padrao, palavras_chave) 
                       VALUES (?, ?, ?, ?)""", (s['nome'], s['fornecedor'], s['padrao'], s['fornecedor'].upper()))
    
    conn.commit()
    conn.close()
    print("Banco SQLite inicializado e populado com sucesso!")

if __name__ == "__main__":
    seed()
