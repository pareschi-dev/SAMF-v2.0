import sys
import os
import re
import hashlib
import json
import sqlite3
from datetime import datetime
import pdfplumber

# Adiciona o diretório atual ao path para importar database.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from database import get_connection, DB_PATH
except ImportError:
    # Fallback caso o arquivo ainda se chame db.py
    from db import get_connection, DB_PATH

SIG_INDEX = 14

def calcular_hash(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def extrair_texto(filepath):
    texto = ""
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                texto += (page.extract_text() or "") + "\n"
    except Exception as e:
        print(f"Erro ao abrir PDF: {e}")
    return texto

def salvar_log(conn, fatura_id, status, mensagem, hash_arq=None):
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO logs_processamento (fatura_id, status, mensagem, hash_arquivo) 
            VALUES (?, ?, ?, ?)
        """, (fatura_id, status, mensagem, hash_arq))
        conn.commit()
    except Exception as e:
        print(f"Erro ao salvar log: {e}")

def processar(raiz, caminho_pdf):
    print(f"\n--- Iniciando Processamento: {os.path.basename(caminho_pdf)} ---")
    resultado_path = os.path.join(raiz, "Configuracoes", "resultado.json")
    conn = None
    
    try:
        if not os.path.exists(caminho_pdf):
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho_pdf}")

        nome_arq = os.path.basename(caminho_pdf)
        hash_arq = calcular_hash(caminho_pdf)
        
        conn = get_connection()
        cur = conn.cursor()
        
        # Verificar duplicidade
        cur.execute("SELECT id FROM faturas WHERE hash_arquivo = ?", (hash_arq,))
        if cur.fetchone():
            print(f"Arquivo duplicado: {nome_arq}")
            salvar_log(conn, None, "duplicado", f"Arquivo repetido ignorado: {nome_arq}", hash_arq)
            with open(resultado_path, "w", encoding="utf-8") as f:
                json.dump({"status": "duplicado"}, f)
            return

        texto = extrair_texto(caminho_pdf).upper()
        if not texto.strip():
            print("Aviso: PDF sem texto extraível (pode ser imagem/digitalização)")
            salvar_log(conn, None, "revisao", f"PDF sem texto extraível: {nome_arq}", hash_arq)
            with open(resultado_path, "w", encoding="utf-8") as f:
                json.dump({"status": "revisao", "motivo": "sem_texto"}, f)
            return

        # Identificar Serviço/Fornecedor
        cur.execute("SELECT id, nome, fornecedor, padrao FROM servicos")
        servicos = cur.fetchall()
        
        melhor_servico = None
        for s in servicos:
            if s['fornecedor'].upper() in texto:
                melhor_servico = s
                break
        
        if not melhor_servico:
            print(f"Fornecedor não identificado para {nome_arq}")
            salvar_log(conn, None, "revisao", f"Fornecedor não identificado: {nome_arq}", hash_arq)
            with open(resultado_path, "w", encoding="utf-8") as f:
                json.dump({"status": "revisao", "motivo": "fornecedor_nao_encontrado"}, f)
            return

        print(f"Serviço identificado: {melhor_servico['nome']} ({melhor_servico['fornecedor']})")

        # Extrair Valor Total (Regex melhorada para milhares brasileiros)
        # Procura padrões como R$ 6.421,80 ou TOTAL 6.421,80
        regex_valor = r"(?:R\$|TOTAL|VALOR|PAGAR|VENCIMENTO)[\s:]*([\d\.]+,\d{2})"
        match = re.search(regex_valor, texto)
        
        valor = None
        if match:
            valor_str = match.group(1)
            # Remove pontos de milhar e troca vírgula por ponto
            valor = float(valor_str.replace(".", "").replace(",", "."))
            print(f"Valor extraído: R$ {valor:.2f}")

        if valor is None or valor <= 0:
            print(f"Valor não encontrado em {nome_arq}")
            salvar_log(conn, None, "revisao", f"Valor total não encontrado: {nome_arq}", hash_arq)
            with open(resultado_path, "w", encoding="utf-8") as f:
                json.dump({"status": "revisao", "motivo": "valor_nao_encontrado"}, f)
            return

        # Gravar Fatura
        cur.execute("""
            INSERT INTO faturas (hash_arquivo, caminho_arquivo, nome_arquivo, servico_id, valor_total, status) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (hash_arq, caminho_pdf, nome_arq, melhor_servico['id'], valor, 'processado'))
        fatura_id = cur.lastrowid
        
        # Calcular Rateios
        cur.execute("SELECT orgao_id, percentual FROM padroes_rateio WHERE nome = ? ORDER BY orgao_id", (melhor_servico['padrao'],))
        pccs = cur.fetchall()
        
        soma_parcial = 0
        # Processar todos exceto o último (SIG) para ajuste de centavos
        for p in pccs:
            if p['orgao_id'] == 15: # Pula o SIG para o final
                continue
            
            v_rateio = round(valor * p['percentual'] / 100, 2)
            soma_parcial += v_rateio
            cur.execute("""
                INSERT INTO rateios_calculados (fatura_id, orgao_id, percentual, valor_rateio) 
                VALUES (?, ?, ?, ?)
            """, (fatura_id, p['orgao_id'], p['percentual'], v_rateio))
        
        # Ajuste do SIG (Órgão 15) com o resíduo
        sig_valor = round(valor - soma_parcial, 2)
        sig_pct = next((p['percentual'] for p in pccs if p['orgao_id'] == 15), 0.0)
        cur.execute("""
            INSERT INTO rateios_calculados (fatura_id, orgao_id, percentual, valor_rateio) 
            VALUES (?, ?, ?, ?)
        """, (fatura_id, 15, sig_pct, sig_valor))
        
        conn.commit()
        salvar_log(conn, fatura_id, "sucesso", f"Processado com sucesso: {nome_arq}", hash_arq)
        print(f"Sucesso! Fatura {fatura_id} gravada no banco.")
        
        with open(resultado_path, "w", encoding="utf-8") as f:
            json.dump({"status": "sucesso"}, f)
            
    except Exception as e:
        print(f"ERRO CRÍTICO: {str(e)}")
        if conn:
            salvar_log(conn, None, "erro", f"Erro técnico em {os.path.basename(caminho_pdf)}: {str(e)}")
        with open(resultado_path, "w", encoding="utf-8") as f:
            json.dump({"status": "erro", "mensagem": str(e)}, f)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"status": "erro", "mensagem": "Argumentos insuficientes. Use: python script.py <raiz> <caminho_pdf>"}))
    else:
        processar(sys.argv[1], sys.argv[2])
