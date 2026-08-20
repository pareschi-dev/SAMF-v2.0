import sys
import os
import re
import hashlib
import json
import sqlite3
import unicodedata
from datetime import datetime
import pdfplumber

# Adiciona o diretório atual ao path para importar database.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from database import get_connection, DB_PATH
except ImportError:
    # Fallback caso o arquivo ainda se chame db.py
    from db import get_connection, DB_PATH
from auditoria import registrar_evento
from configuracao_operacional import carregar_configuracao as carregar_configuracao_operacional
from configuracao_operacional import validar_configuracao as validar_configuracao_operacional

SIG_INDEX = 14
def carregar_configuracao(raiz):
    return carregar_configuracao_operacional(raiz)


def validar_configuracao(config):
    return validar_configuracao_operacional(config)

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
        tipo = {'duplicado': 'duplicidade', 'erro': 'erro', 'sucesso': 'processamento'}.get(status, 'processamento')
        registrar_evento(conn, tipo, fatura_id=fatura_id, arquivo=hash_arq, status=status,
                 observacao=mensagem)
        conn.commit()
    except Exception as e:
        print(f"Erro ao salvar log: {e}")


def _normalizar(texto):
    texto = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode('ascii')
    return ' '.join(texto.upper().split())


def _classificar_oficial(conn, nome_arquivo, texto):
    """Aplica as regras cadastradas usando texto e contexto do nome do PDF."""
    contexto = _normalizar(f'{nome_arquivo} {texto}')
    regras = conn.execute(
        "SELECT servico, fornecedor, complemento, secao, tipo FROM regras_classificacao WHERE ativo = 1"
    ).fetchall()
    candidatos = []
    for regra in regras:
        fornecedor = _normalizar(regra['fornecedor'])
        fornecedor_tokens = [token for token in fornecedor.replace('&', ' ').split() if len(token) > 2]
        fornecedor_encontrado = fornecedor in contexto or all(token in contexto for token in fornecedor_tokens)
        if not fornecedor or not fornecedor_encontrado:
            continue
        servico = _normalizar(regra['servico'])
        complemento = _normalizar(regra['complemento'])
        secao = _normalizar(regra['secao'])
        pontos = 2
        if servico and servico in contexto:
            pontos += 5
        if complemento and complemento in contexto:
            pontos += 5
        if secao and secao in contexto:
            pontos += 4
        if regra['tipo'] == 'compartilhado' and any(token in contexto for token in ('RATEIO', 'ED SEDE', 'EDIFICIO SEDE')):
            pontos += 3
        if regra['tipo'] == 'exclusivo' and any(token in contexto for token in ('ESTACIONAMENTO', 'PRINCESA ISABEL', 'VILA VELHA', 'CACHOEIRO', 'COLATINA', 'VITORIA')):
            pontos += 3
        candidatos.append((pontos, regra))

    if not candidatos:
        return None
    candidatos.sort(key=lambda item: item[0], reverse=True)
    melhor = candidatos[0][1]
    tipo = 'COMPARTILHADA' if melhor['tipo'] == 'compartilhado' else 'EXCLUSIVA'
    servico = conn.execute(
        "SELECT id, nome FROM servicos WHERE UPPER(nome) = UPPER(?) OR UPPER(fornecedor) = UPPER(?) LIMIT 1",
        (melhor['servico'], melhor['fornecedor']),
    ).fetchone()
    return {
        'classificacao': tipo,
        'servico_id': servico['id'] if servico else None,
        'servico': melhor['servico'],
        'fornecedor': melhor['fornecedor'],
        'confianca': 0.90 if candidatos[0][0] >= 7 else 0.75,
        'regra': f"{melhor['servico']} | {melhor['fornecedor']} | {melhor['secao']}",
    }

def processar(raiz, caminho_pdf):
    print(f"\n--- Iniciando Processamento: {os.path.basename(caminho_pdf)} ---")
    resultado_path = os.path.join(raiz, "Configuracoes", "resultado.json")
    conn = None
    
    try:
        if not os.path.exists(caminho_pdf):
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho_pdf}")

        config = carregar_configuracao(raiz)
        valido, motivo = validar_configuracao(config)
        if not valido:
            conn = get_connection()
            salvar_log(conn, None, 'revisao', f'Configuração incompleta para {os.path.basename(caminho_pdf)}: {motivo}', None)
            with open(resultado_path, 'w', encoding='utf-8') as f:
                json.dump({'status': 'revisao', 'motivo': motivo}, f, ensure_ascii=False)
            return

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
        classificacao = _classificar_oficial(conn, nome_arq, texto)
        if not classificacao:
            salvar_log(conn, None, "revisao", f"Regra oficial não identificada: {nome_arq}", hash_arq)
            with open(resultado_path, "w", encoding="utf-8") as f:
                json.dump({"status": "revisao", "motivo": "regra_nao_identificada"}, f)
            return
        print(f"Classificação oficial: {classificacao['classificacao']} ({classificacao['regra']})")
        registrar_evento(conn, 'classificação', arquivo=nome_arq, status='identificado',
                 valor_novo={'servico': classificacao['servico'], 'fornecedor': classificacao['fornecedor'], 'classificacao': classificacao['classificacao']})

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
            INSERT INTO faturas (hash_arquivo, caminho_arquivo, nome_arquivo, servico_id, fornecedor_extraido, fornecedor, servico, valor_total, valor_base, classificacao, confianca_classificacao, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (hash_arq, caminho_pdf, nome_arq, classificacao['servico_id'] or melhor_servico['id'], classificacao['fornecedor'], classificacao['fornecedor'], classificacao['servico'], valor, valor, classificacao['classificacao'], classificacao['confianca'], 'processado'))
        fatura_id = cur.lastrowid
        
        # Calcular Rateios
        cur.execute("SELECT orgao_id, percentual FROM padroes_rateio WHERE nome = ? ORDER BY orgao_id", (melhor_servico['padrao'],))
        pccs = cur.fetchall()
        
        soma_parcial = 0
        if classificacao['classificacao'] == 'EXCLUSIVA':
            pccs = []
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
        if classificacao['classificacao'] == 'COMPARTILHADA':
            sig_valor = round(valor - soma_parcial, 2)
            sig_pct = next((p['percentual'] for p in pccs if p['orgao_id'] == 15), 0.0)
            cur.execute("""
                INSERT INTO rateios_calculados (fatura_id, orgao_id, percentual, valor_rateio)
                VALUES (?, ?, ?, ?)
            """, (fatura_id, 15, sig_pct, sig_valor))
        registrar_evento(conn, 'cálculo', fatura_id=fatura_id, arquivo=nome_arq,
                 status='calculado', valor_novo={'valor_total': valor, 'valor_rateado': valor})
        registrar_evento(conn, 'lançamento', fatura_id=fatura_id, arquivo=nome_arq,
                 status='pendente', observacao='Rateios calculados e preparados para lançamento')
        
        conn.commit()
        salvar_log(conn, fatura_id, "sucesso", f"Processado com sucesso: {nome_arq}", hash_arq)
        print(f"Sucesso! Fatura {fatura_id} gravada no banco.")
        
        with open(resultado_path, "w", encoding="utf-8") as f:
            json.dump({"status": "sucesso", "classificacao": classificacao['classificacao'].lower()}, f)
            
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
