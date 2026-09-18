"""
SAMF v2.0 - API Flask Profissional
Endpoints completos para processamento, classificação e auditoria de faturas
"""

import os
import sys
import json
import sqlite3
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from datetime import datetime
from pathlib import Path

# Adicionar Scripts ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Scripts'))

from database import get_connection
from classifier import ClassificadorFaturas, FaturaExtraida, ResultadoClassificacao

app = Flask(__name__, static_folder="static")
CORS(app)

BASE_PATH = r"c:\code\SAMF-HUB-v1.1"
INPUT_DIR = os.path.join(BASE_PATH, "Faturas_entrada")
PROCESSED_DIR = os.path.join(BASE_PATH, "Processados")
RELATORIOS_DIR = os.path.join(BASE_PATH, "Relatorios")

for dir_path in [INPUT_DIR, PROCESSED_DIR, RELATORIOS_DIR]:
    os.makedirs(dir_path, exist_ok=True)

def get_db():
    return get_connection()

def registrar_auditoria(fatura_id, tipo_acao, usuario="sistema", dados_anterior=None, dados_novo=None, justificativa=None, resultado=None):
    """Registra ação na tabela de auditoria"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO auditoria (fatura_id, tipo_acao, usuario, dados_anterior, dados_novo, justificativa, resultado)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (fatura_id, tipo_acao, usuario, json.dumps(dados_anterior), json.dumps(dados_novo), justificativa, resultado))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao registrar auditoria: {e}")

def registrar_log(fatura_id, nivel, mensagem, contexto=None):
    """Registra log de processamento"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO logs_processamento (fatura_id, nivel, mensagem, contexto)
            VALUES (?, ?, ?, ?)
        """, (fatura_id, nivel, mensagem, json.dumps(contexto) if contexto else None))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao registrar log: {e}")

# ============================================
# ENDPOINTS: DASHBOARD E ESTATÍSTICAS
# ============================================

@app.route("/api/v2/dashboard")
def get_dashboard_v2():
    """Dashboard com estatísticas completas"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Total de faturas por classificação
        cur.execute("""
            SELECT classificacao, COUNT(*) as qtd, SUM(valor_total) as total
            FROM faturas_v2
            GROUP BY classificacao
        """)
        por_classificacao = {row[0]: {'qtd': row[1], 'valor': row[2] or 0} for row in cur.fetchall()}
        
        # Faturas por status
        cur.execute("""
            SELECT status, COUNT(*) as qtd
            FROM faturas_v2
            GROUP BY status
        """)
        por_status = {row[0]: row[1] for row in cur.fetchall()}
        
        # Totais gerais
        cur.execute("SELECT COUNT(*), SUM(valor_total) FROM faturas_v2")
        total_faturas, valor_total = cur.fetchone()
        
        # Divergências
        cur.execute("SELECT COUNT(*) FROM divergencias WHERE resolvido = 0")
        divergencias_abertas = cur.fetchone()[0]
        
        # Faturas aguardando revisão
        cur.execute("SELECT COUNT(*) FROM faturas_v2 WHERE classificacao = 'revisao'")
        em_revisao = cur.fetchone()[0]
        
        # Valor por serviço (top 10)
        cur.execute("""
            SELECT s.nome, COUNT(f.id) as qtd, SUM(f.valor_total) as total
            FROM faturas_v2 f
            LEFT JOIN servicos s ON f.servico_id = s.id
            GROUP BY f.servico_id
            ORDER BY total DESC
            LIMIT 10
        """)
        top_servicos = [{'servico': row[0] or 'Desconhecido', 'qtd': row[1], 'valor': row[2] or 0} for row in cur.fetchall()]
        
        # Valor por órgão
        cur.execute("""
            SELECT o.nome, SUM(l.valor_lançado) as total
            FROM lancamentos l
            JOIN orgaos o ON l.orgao_id = o.id
            GROUP BY l.orgao_id
            ORDER BY total DESC
        """)
        por_orgao = [{'orgao': row[0], 'valor': row[1] or 0} for row in cur.fetchall()]
        
        conn.close()
        
        taxa_sucesso = (por_status.get('lançado', 0) / total_faturas * 100) if total_faturas > 0 else 0
        
        return jsonify({
            'timestamp': datetime.now().isoformat(),
            'resumo': {
                'total_faturas': total_faturas or 0,
                'valor_total_processado': valor_total or 0,
                'taxa_sucesso': round(taxa_sucesso, 1),
                'divergencias_abertas': divergencias_abertas,
                'em_revisao': em_revisao
            },
            'por_classificacao': por_classificacao,
            'por_status': por_status,
            'top_servicos': top_servicos,
            'distribuicao_orgaos': por_orgao
        })
    except Exception as e:
        registrar_log(None, 'error', f'Erro ao gerar dashboard: {str(e)}')
        return jsonify({'erro': str(e)}), 500

# ============================================
# ENDPOINTS: LISTAGEM DE FATURAS
# ============================================

@app.route("/api/v2/faturas")
def listar_faturas():
    """Lista faturas com filtros"""
    try:
        # Parâmetros de filtro
        status = request.args.get('status')
        classificacao = request.args.get('classificacao')
        fornecedor = request.args.get('fornecedor')
        servico = request.args.get('servico')
        competencia = request.args.get('competencia')
        busca = request.args.get('busca')  # nome, fornecedor, número
        pagina = int(request.args.get('pagina', 1))
        por_pagina = int(request.args.get('por_pagina', 50))
        
        conn = get_db()
        cur = conn.cursor()
        
        # Construir query dinamicamente
        query = """
            SELECT 
                f.id, f.nome_arquivo, f.fornecedor_nome_original, s.nome as servico,
                f.competencia, f.classificacao, f.valor_total, f.status,
                f.confianca_classificacao, f.divergencia_detectada,
                f.processado_em
            FROM faturas_v2 f
            LEFT JOIN servicos s ON f.servico_id = s.id
            WHERE 1=1
        """
        
        params = []
        
        if status:
            query += " AND f.status = ?"
            params.append(status)
        if classificacao:
            query += " AND f.classificacao = ?"
            params.append(classificacao)
        if fornecedor:
            query += " AND f.fornecedor_nome_original LIKE ?"
            params.append(f"%{fornecedor}%")
        if servico:
            query += " AND s.nome LIKE ?"
            params.append(f"%{servico}%")
        if competencia:
            query += " AND f.competencia = ?"
            params.append(competencia)
        if busca:
            query += " AND (f.nome_arquivo LIKE ? OR f.numero_fatura LIKE ? OR f.fornecedor_nome_original LIKE ?)"
            params.extend([f"%{busca}%", f"%{busca}%", f"%{busca}%"])
        
        # Contar total
        count_query = f"SELECT COUNT(*) FROM ({query})"
        cur.execute(count_query, params)
        total = cur.fetchone()[0]
        
        # Ordernar e paginar
        query += " ORDER BY f.processado_em DESC LIMIT ? OFFSET ?"
        offset = (pagina - 1) * por_pagina
        params.extend([por_pagina, offset])
        
        cur.execute(query, params)
        faturas = []
        for row in cur.fetchall():
            faturas.append({
                'id': row[0],
                'nome_arquivo': row[1],
                'fornecedor': row[2],
                'servico': row[3],
                'competencia': row[4],
                'classificacao': row[5],
                'valor': row[6],
                'status': row[7],
                'confianca': row[8],
                'divergencia': row[9],
                'processado_em': row[10]
            })
        
        conn.close()
        
        return jsonify({
            'total': total,
            'pagina': pagina,
            'por_pagina': por_pagina,
            'faturas': faturas
        })
    except Exception as e:
        registrar_log(None, 'error', f'Erro ao listar faturas: {str(e)}')
        return jsonify({'erro': str(e)}), 500

@app.route("/api/v2/faturas/<int:fatura_id>")
def detalhes_fatura(fatura_id):
    """Detalhes completos de uma fatura"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Dados da fatura
        cur.execute("""
            SELECT 
                f.id, f.nome_arquivo, f.fornecedor_nome_original, f.numero_fatura,
                s.nome as servico, f.descricao, f.valor_total, f.competencia,
                f.data_fatura, f.data_vencimento, f.endereco, f.unidade,
                f.complemento_fatura, f.classificacao, f.confianca_classificacao,
                f.motivo_revisao, f.status, f.processado_em, o.nome as orgao_beneficiario
            FROM faturas_v2 f
            LEFT JOIN servicos s ON f.servico_id = s.id
            LEFT JOIN orgaos o ON f.orgao_beneficiario_id = o.id
            WHERE f.id = ?
        """, (fatura_id,))
        
        row = cur.fetchone()
        if not row:
            return jsonify({'erro': 'Fatura não encontrada'}), 404
        
        fatura = {
            'id': row[0],
            'nome_arquivo': row[1],
            'fornecedor': row[2],
            'numero_fatura': row[3],
            'servico': row[4],
            'descricao': row[5],
            'valor_total': row[6],
            'competencia': row[7],
            'data_fatura': row[8],
            'data_vencimento': row[9],
            'endereco': row[10],
            'unidade': row[11],
            'complemento': row[12],
            'classificacao': row[13],
            'confianca_classificacao': row[14],
            'motivo_revisao': row[15],
            'status': row[16],
            'processado_em': row[17],
            'orgao_beneficiario': row[18]
        }
        
        # Lançamentos
        cur.execute("""
            SELECT o.nome, l.valor_lançado, l.percentual_aplicado, l.criterio_aplicado
            FROM lancamentos l
            JOIN orgaos o ON l.orgao_id = o.id
            WHERE l.fatura_id = ?
            ORDER BY o.nome
        """, (fatura_id,))
        
        lancamentos = [
            {
                'orgao': row[0],
                'valor': row[1],
                'percentual': row[2],
                'criterio': row[3]
            }
            for row in cur.fetchall()
        ]
        
        # Divergências
        cur.execute("""
            SELECT tipo_divergencia, descricao, valor_esperado, valor_obtido, resolvido
            FROM divergencias
            WHERE fatura_id = ?
        """, (fatura_id,))
        
        divergencias = [
            {
                'tipo': row[0],
                'descricao': row[1],
                'valor_esperado': row[2],
                'valor_obtido': row[3],
                'resolvido': row[4]
            }
            for row in cur.fetchall()
        ]
        
        # Auditoria
        cur.execute("""
            SELECT tipo_acao, usuario, resultado, criado_em
            FROM auditoria
            WHERE fatura_id = ?
            ORDER BY criado_em DESC
            LIMIT 10
        """, (fatura_id,))
        
        auditoria = [
            {
                'acao': row[0],
                'usuario': row[1],
                'resultado': row[2],
                'data': row[3]
            }
            for row in cur.fetchall()
        ]
        
        conn.close()
        
        return jsonify({
            'fatura': fatura,
            'lancamentos': lancamentos,
            'divergencias': divergencias,
            'auditoria': auditoria
        })
    except Exception as e:
        registrar_log(fatura_id, 'error', f'Erro ao recuperar detalhes: {str(e)}')
        return jsonify({'erro': str(e)}), 500

# ============================================
# ENDPOINTS: REVISÃO E CLASSIFICAÇÃO
# ============================================

@app.route("/api/v2/faturas-revisao")
def listar_faturas_revisao():
    """Lista faturas aguardando revisão"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                f.id, f.nome_arquivo, f.fornecedor_nome_original, f.complemento_fatura,
                f.valor_total, f.motivo_revisao, f.confianca_classificacao
            FROM faturas_v2 f
            WHERE f.classificacao = 'revisao'
            ORDER BY f.confianca_classificacao ASC, f.criado_em ASC
        """)
        
        faturas = [
            {
                'id': row[0],
                'nome_arquivo': row[1],
                'fornecedor': row[2],
                'complemento': row[3],
                'valor': row[4],
                'motivo_revisao': row[5],
                'confianca': row[6]
            }
            for row in cur.fetchall()
        ]
        
        conn.close()
        return jsonify({'faturas_em_revisao': faturas, 'total': len(faturas)})
    except Exception as e:
        registrar_log(None, 'error', f'Erro ao listar revisão: {str(e)}')
        return jsonify({'erro': str(e)}), 500

@app.route("/api/v2/faturas/<int:fatura_id>/classificar", methods=['POST'])
def classificar_fatura_manual(fatura_id):
    """Classifica manualmente uma fatura em revisão"""
    try:
        data = request.get_json()
        classificacao = data.get('classificacao')  # 'compartilhado' ou 'exclusivo'
        justificativa = data.get('justificativa')
        usuario = data.get('usuario', 'admin')
        
        if classificacao not in ['compartilhado', 'exclusivo']:
            return jsonify({'erro': 'Classificação inválida'}), 400
        
        if not justificativa:
            return jsonify({'erro': 'Justificativa obrigatória'}), 400
        
        conn = get_db()
        cur = conn.cursor()
        
        # Atualizar classificação
        cur.execute("""
            UPDATE faturas_v2
            SET classificacao = ?, status = 'processado', revisado_por = ?, revisado_em = ?
            WHERE id = ?
        """, (classificacao, usuario, datetime.now(), fatura_id))
        
        conn.commit()
        
        # Registrar auditoria
        registrar_auditoria(
            fatura_id, 
            'revisao',
            usuario,
            {'classificacao': 'revisao'},
            {'classificacao': classificacao},
            justificativa,
            'Aprovado em revisão manual'
        )
        
        conn.close()
        
        return jsonify({'sucesso': True, 'mensagem': 'Fatura classificada com sucesso'})
    except Exception as e:
        registrar_log(fatura_id, 'error', f'Erro ao classificar: {str(e)}')
        return jsonify({'erro': str(e)}), 500

# ============================================
# ENDPOINTS: RATEIOS E CÁLCULOS
# ============================================

@app.route("/api/v2/rateios")
def visualizar_rateios():
    """Visualiza matriz de rateios"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Rateios processados (agrupado)
        cur.execute("""
            SELECT 
                s.nome as servico,
                f.nome as fornecedor,
                SUM(l.valor_lançado) as total_processado,
                COUNT(DISTINCT l.fatura_id) as qtd_faturas
            FROM lancamentos l
            JOIN faturas_v2 f2 ON l.fatura_id = f2.id
            LEFT JOIN servicos s ON f2.servico_id = s.id
            LEFT JOIN fornecedores f ON f2.fornecedor_id = f.id
            GROUP BY s.id, f.id
            ORDER BY total_processado DESC
        """)
        
        rateios = [
            {
                'servico': row[0] or 'Desconhecido',
                'fornecedor': row[1] or 'Desconhecido',
                'total': row[2] or 0,
                'qtd_faturas': row[3]
            }
            for row in cur.fetchall()
        ]
        
        conn.close()
        return jsonify({'rateios': rateios})
    except Exception as e:
        registrar_log(None, 'error', f'Erro ao visualizar rateios: {str(e)}')
        return jsonify({'erro': str(e)}), 500

# ============================================
# ENDPOINT: VALIDAÇÃO E RELATÓRIO
# ============================================

@app.route("/api/v2/validacao")
def validacao_geral():
    """Relatório de validação completo"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Divergências abertas
        cur.execute("""
            SELECT tipo_divergencia, COUNT(*) FROM divergencias
            WHERE resolvido = 0
            GROUP BY tipo_divergencia
        """)
        divergencias = {row[0]: row[1] for row in cur.fetchall()}
        
        # Duplicatas detectadas
        cur.execute("SELECT COUNT(*) FROM faturas_v2 WHERE classificacao = 'duplicado'")
        duplicatas = cur.fetchone()[0]
        
        # Soma de valores (validação)
        cur.execute("""
            SELECT 
                SUM(f.valor_total) as valor_original,
                SUM(l.valor_lançado) as valor_lancado
            FROM faturas_v2 f
            LEFT JOIN lancamentos l ON f.id = l.fatura_id
            WHERE f.status IN ('lançado', 'processado')
        """)
        row = cur.fetchone()
        valor_original = row[0] or 0
        valor_lancado = row[1] or 0
        diferenca = abs(valor_original - valor_lancado)
        
        conn.close()
        
        return jsonify({
            'divergencias': divergencias,
            'duplicatas': duplicatas,
            'validacao_valores': {
                'valor_original': valor_original,
                'valor_lancado': valor_lancado,
                'diferenca': diferenca,
                'consistente': diferenca < 1.00
            }
        })
    except Exception as e:
        registrar_log(None, 'error', f'Erro na validação: {str(e)}')
        return jsonify({'erro': str(e)}), 500

# ============================================
# HEALTH CHECK
# ============================================

@app.route("/api/v2/health")
def health_check():
    """Verifica saúde do sistema"""
    try:
        conn = get_db()
        conn.close()
        return jsonify({'status': 'OK', 'timestamp': datetime.now().isoformat()})
    except:
        return jsonify({'status': 'ERROR'}), 500

@app.route("/")
def index():
    """Serve frontend"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>SAMF v2.0 - Sistema de Processamento de Faturas</title>
    </head>
    <body>
        <div id="app"></div>
        <script src="/static/app.js"></script>
    </body>
    </html>
    """

if __name__ == "__main__":
    print("SAMF v2.0 - API Professional")
    app.run(host="0.0.0.0", port=5000, debug=True)

