import os, sqlite3, subprocess, json
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from datetime import datetime

# Ajuste de Path para encontrar o database.py na pasta Scripts
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'Scripts'))
try:
    from database import get_connection, DB_PATH
except ImportError:
    # Fallback caso o usuário ainda não tenha renomeado
    from db import get_connection, DB_PATH

app = Flask(__name__, static_folder="static")
CORS(app)

BASE_PATH = r"C:\Users\nerivaldo.junior\OneDrive - Ministério da Gestão e da Inovação dos Serv. Pub\SAMF"

os.makedirs(os.path.join(BASE_PATH, "Faturas_entrada"), exist_ok=True)


def get_db():
    conn = get_connection()
    return conn

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/stats")
def get_stats():
    conn = get_db(); cur = conn.cursor()
    
    # Total faturas
    cur.execute("SELECT COUNT(*), SUM(valor_total) FROM faturas WHERE status = 'processado'")
    count, total = cur.fetchone()
    
    # Faturas por status
    cur.execute("SELECT status, COUNT(*) FROM faturas GROUP BY status")
    by_status = {row[0]: row[1] for row in cur.fetchall()}
    
    # Últimos 5 meses de volume
    cur.execute("SELECT strftime('%Y-%m', criado_em) as mes, SUM(valor_total) FROM faturas WHERE status = 'processado' GROUP BY mes ORDER BY mes DESC LIMIT 5")
    history = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    return jsonify({
        "total_faturas": count or 0,
        "valor_total": round(total or 0, 2),
        "status": by_status,
        "historico": history
    })

@app.route("/api/rateios")
def get_rateios():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT p.orgao_id, p.percentual, o.nome as orgao_nome, p.nome as padrao 
        FROM padroes_rateio p 
        JOIN orgaos o ON p.orgao_id = o.id
        ORDER BY o.ordem
    """)
    rows = cur.fetchall()
    conn.close()
    return jsonify({
        "padrao_a": [dict(r) for r in rows if r['padrao'] == 'A'],
        "padrao_b": [dict(r) for r in rows if r['padrao'] == 'B']
    })

@app.route("/api/faturas")
def get_faturas():
    status = request.args.get("status")
    conn = get_db(); cur = conn.cursor()
    query = "SELECT f.*, s.nome as servico_nome FROM faturas f LEFT JOIN servicos s ON f.servico_id = s.id"
    if status:
        cur.execute(query + " WHERE f.status = ? ORDER BY f.criado_em DESC", (status,))
    else:
        cur.execute(query + " ORDER BY f.criado_em DESC")
    faturas = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(faturas)

@app.route("/api/faturas/<int:id>/detalhes")
def get_fatura_detalhes(id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT r.*, o.nome as orgao_nome 
        FROM rateios_calculados r 
        JOIN orgaos o ON r.orgao_id = o.id 
        WHERE r.fatura_id = ?
        ORDER BY o.ordem
    """, (id,))
    detalhes = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(detalhes)

@app.route("/api/logs")
def get_logs():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM logs_processamento ORDER BY criado_em DESC LIMIT 100")
    logs = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(logs)

@app.route("/api/export/<mes>")
def exportar(mes):
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script = os.path.join(raiz, "Scripts", "exportar_excel.py")
    subprocess.run(["python", script, raiz, mes])
    file_path = os.path.join(raiz, "Relatorios", f"Despesas_{mes.replace('-','_')}.xlsx")
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({"erro": "Arquivo não gerado"}), 404

@app.route("/api/upload", methods=["POST"])
def upload_faturas():
    if "files" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    saved = []
    errors = []
    input_dir = os.path.join(BASE_PATH, "Faturas_entrada")
    os.makedirs(input_dir, exist_ok=True)
    script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Scripts", "processar_fatura.py")

    for uploaded in files:
        filename = uploaded.filename or "unnamed.pdf"
        if not filename.lower().endswith(".pdf"):
            errors.append({"file": filename, "status": "ignored", "message": "Formato não suportado"})
            continue

        safe_name = os.path.basename(filename)
        dest_path = os.path.join(input_dir, safe_name)
        base_name, ext = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(input_dir, f"{base_name}_{counter}{ext}")
            counter += 1

        uploaded.save(dest_path)
        process = subprocess.run([sys.executable, script_path, BASE_PATH, dest_path], capture_output=True, text=True)
        item = {
            "file": filename,
            "saved_as": os.path.basename(dest_path),
            "returncode": process.returncode,
            "stdout": process.stdout.strip(),
            "stderr": process.stderr.strip(),
        }
        if process.returncode == 0:
            item["status"] = "sucesso"
        else:
            item["status"] = "erro"
            errors.append({"file": filename, "status": item["status"], "message": process.stderr.strip() or "Erro interno"})

        saved.append(item)

    return jsonify({"processed": saved, "errors": errors, "success": len([x for x in saved if x["status"] == "sucesso"]), "failed": len(errors)})

if __name__ == "__main__":
    print(f"SAMF PRO SERVER ONLINE - Porta 5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
