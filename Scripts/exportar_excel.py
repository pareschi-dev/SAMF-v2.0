import sys
import os
import json
import sqlite3
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_connection

def exportar(raiz, mes):
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id, nome FROM orgaos ORDER BY ordem")
        orgaos = cur.fetchall()
        
        # Filtro de mês no SQLite (YYYY-MM)
        cur.execute("""
            SELECT f.id, s.nome as servico, f.fornecedor_extraido, f.valor_total, f.data_vencimento
            FROM faturas f
            JOIN servicos s ON f.servico_id = s.id
            WHERE f.status = 'processado' AND strftime('%Y-%m', f.criado_em) = ?
        """, (mes,))
        faturas = cur.fetchall()
        
        wb = Workbook()
        ws = wb.active
        ws.title = f"Rateio {mes}"
        
        headers = ["Serviço", "Fornecedor", "Valor Total", "Vencimento"]
        for o in orgaos:
            headers.extend([f"{o['nome']} %", f"{o['nome']} R$"])
            
        ws.append(headers)
        
        for f in faturas:
            row = [f['servico'], f['fornecedor_extraido'], f['valor_total'], f['data_vencimento']]
            
            cur.execute("SELECT orgao_id, percentual, valor_rateio FROM rateios_calculados WHERE fatura_id = ?", (f['id'],))
            rates = {r['orgao_id']: r for r in cur.fetchall()}
            
            for o in orgaos:
                r = rates.get(o['id'], {'percentual': 0, 'valor_rateio': 0})
                row.extend([r['percentual'], r['valor_rateio']])
            ws.append(row)
            
        path_rel = os.path.join(raiz, "Relatorios", f"Despesas_{mes.replace('-', '_')}.xlsx")
        os.makedirs(os.path.dirname(path_rel), exist_ok=True)
        wb.save(path_rel)
        print(json.dumps({"status": "sucesso", "arquivo": path_rel}))
        
    except Exception as e:
        print(json.dumps({"status": "erro", "mensagem": str(e)}))

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"status": "erro", "mensagem": "Argumentos insuficientes"}))
    else:
        exportar(sys.argv[1], sys.argv[2])
