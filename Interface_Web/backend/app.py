import os
import json
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory, g
from flask_cors import CORS

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'Scripts'))
try:
    from database import get_connection
except ImportError:
    from db import get_connection

from configuracao_operacional import carregar_configuracao, salvar_configuracao, validar_configuracao
from auditoria import garantir_tabela, registrar_evento
from exportador import TIPOS, gerar_exportacao, resumo_exportacao
from usuarios import garantir_tabelas, quantidade_usuarios, criar_usuario, autenticar, usuario_da_requisicao, exigir, PERFIS, _perfil
from backup_recuperacao import criar_backup
from migracao_modelo_dados import ensure_cobrancas_tables
from gerador_previa_cobranca import ErroPreviaCobranca, gerar_previa_cobranca
from fluxo_aprovacao_mensagens import ErroAprovacaoMensagem, validar_lote, transicionar_mensagem
from auditoria_cobrancas import listar_auditoria
from integracao_operacional_cobrancas import executar_integracao_planilha
from whatsapp_business import configuracao_auditoria, validar_configuracao_whatsapp, _config_publica

app = Flask(__name__, static_folder='static')
CORS(app)
BASE_PATH = str(Path(__file__).resolve().parents[2])
os.makedirs(os.path.join(BASE_PATH, 'Faturas_entrada'), exist_ok=True)


def get_db():
    conn = get_connection()
    garantir_tabela(conn)
    garantir_tabelas(conn)
    return conn


def load_config():
    return carregar_configuracao(BASE_PATH)


def _backup_antes(motivo):
    arquivo = criar_backup(load_config(), motivo=motivo, versao='v1.0.0', raiz=Path(BASE_PATH))
    conn = get_db()
    registrar_evento(conn, 'backup', usuario=g.usuario['usuario'], status='sucesso', valor_novo={'arquivo': str(arquivo), 'motivo': motivo}, observacao='Backup obrigatório antes de alteração')
    conn.commit(); conn.close()
    return arquivo


def _mascarar_telefone(valor):
    digitos = ''.join(char for char in str(valor or '') if char.isdigit())
    if len(digitos) <= 4:
        return '*' * len(digitos)
    return '*' * (len(digitos) - 4) + digitos[-4:]


def _normalizar_telefone(valor):
    """Aceita 10-15 dígitos; remove apenas formatação e preserva código do país."""
    texto = str(valor or '').strip()
    if not texto or re.search(r'[A-Za-z]', texto):
        raise ValueError('Telefone deve conter somente dígitos e formatação válida.')
    if not re.fullmatch(r'\+?[0-9().\s-]+', texto):
        raise ValueError('Telefone contém caracteres inválidos.')
    digitos = ''.join(char for char in texto if char.isdigit())
    if not 10 <= len(digitos) <= 15:
        raise ValueError('Telefone deve conter entre 10 e 15 dígitos.')
    return f'+{digitos}' if texto.startswith('+') else digitos


def _dados_destinatario_auditoria(registro):
    dados = dict(registro)
    if 'telefone' in dados:
        dados['telefone'] = _mascarar_telefone(dados['telefone'])
    return dados


def _auditar_destinatario(conn, acao, registro_id, anterior, novo, usuario, resultado='sucesso'):
    conn.execute('''INSERT INTO auditoria_cobranca
        (tabela_origem, registro_id, acao, usuario, dados_anterior, dados_novo,
         valor_anterior, valor_novo, origem, observacao, status, tipo_evento)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        ('destinatario', registro_id, acao, usuario,
         json.dumps(_dados_destinatario_auditoria(anterior), ensure_ascii=False, default=str) if anterior else None,
         json.dumps(_dados_destinatario_auditoria(novo), ensure_ascii=False, default=str) if novo else None,
         json.dumps(_dados_destinatario_auditoria(anterior), ensure_ascii=False, default=str) if anterior else None,
         json.dumps(_dados_destinatario_auditoria(novo), ensure_ascii=False, default=str) if novo else None,
         'api', None, resultado, 'destinatario'))


def _proteger_telefone(registro):
    resultado = dict(registro)
    if 'telefone' in resultado and 'visualizar_telefone_destinatario' not in PERFIS[g.usuario['perfil']]:
        resultado['telefone'] = _mascarar_telefone(resultado['telefone'])
    if 'telefone_destinatario' in resultado and 'visualizar_telefone_destinatario' not in PERFIS[g.usuario['perfil']]:
        resultado['telefone_destinatario'] = _mascarar_telefone(resultado['telefone_destinatario'])
    return resultado


@app.before_request
def autenticar_requisicao():
    if not request.path.startswith('/api/') or request.path.startswith('/api/auth/'):
        return None
    conn = get_db()
    g.auth_conn = conn
    g.usuario = {'id': 0, 'usuario': 'sistema', 'nome': 'Acesso local', 'perfil': 'administrador'}
    return None


@app.teardown_request
def fechar_conexao_autenticacao(_erro):
    conn = g.pop('auth_conn', None)
    if conn:
        conn.close()


@app.route('/api/auth/status')
def auth_status():
    conn = get_db()
    total = quantidade_usuarios(conn)
    usuario = usuario_da_requisicao(conn)
    conn.close()
    return jsonify({'configurado': total > 0, 'usuario': usuario, 'perfis': list(PERFIS)})


@app.route('/api/auth/bootstrap', methods=['POST'])
def auth_bootstrap():
    payload = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        if quantidade_usuarios(conn):
            return jsonify({'erro': 'O administrador inicial já foi criado.'}), 409
        user_id, perfil = criar_usuario(conn, payload.get('usuario'), payload.get('nome'), payload.get('senha'), 'administrador')
        registrar_evento(conn, 'usuário criado', usuario=payload.get('usuario'), status='sucesso', valor_novo={'id': user_id, 'perfil': perfil}, observacao='Administrador inicial')
        conn.commit()
        return jsonify({'status': 'criado'}), 201
    except (ValueError, sqlite3.IntegrityError) as exc:
        conn.rollback()
        return jsonify({'erro': str(exc)}), 400
    finally:
        conn.close()


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    payload = request.get_json(silent=True) or {}
    conn = get_db()
    resultado = autenticar(conn, payload.get('usuario'), payload.get('senha'))
    if not resultado:
        registrar_evento(conn, 'login', usuario=payload.get('usuario', 'anônimo'), status='falha', observacao='Credenciais inválidas')
        conn.commit(); conn.close()
        return jsonify({'erro': 'Credenciais inválidas.'}), 401
    token, usuario = resultado
    registrar_evento(conn, 'login', usuario=usuario['usuario'], status='sucesso', observacao='Sessão iniciada')
    conn.commit(); conn.close()
    return jsonify({'token': token, 'usuario': {k: usuario[k] for k in ('id', 'usuario', 'nome', 'perfil')}})


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    conn = get_db()
    usuario = usuario_da_requisicao(conn)
    if usuario:
        conn.execute('UPDATE sessoes_usuario SET encerrada_em=CURRENT_TIMESTAMP WHERE id=?', (usuario['sessao_id'],))
        registrar_evento(conn, 'logout', usuario=usuario['usuario'], status='sucesso', observacao='Sessão encerrada')
        conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/api/usuarios', methods=['GET', 'POST'])
def usuarios_api():
    conn = get_db()
    if request.method == 'GET':
        rows = conn.execute('SELECT id, usuario, nome, perfil, ativo, criado_em, atualizado_em FROM usuarios ORDER BY nome').fetchall()
        conn.close()
        return jsonify([dict(row) for row in rows])
    payload = request.get_json(silent=True) or {}
    try:
        user_id, perfil = criar_usuario(conn, payload.get('usuario'), payload.get('nome'), payload.get('senha'), payload.get('perfil'))
        registrar_evento(conn, 'usuário criado', usuario=g.usuario['usuario'], status='sucesso', valor_novo={'id': user_id, 'usuario': payload.get('usuario'), 'perfil': perfil})
        conn.commit()
        return jsonify({'id': user_id, 'perfil': perfil}), 201
    except (ValueError, sqlite3.IntegrityError) as exc:
        conn.rollback()
        return jsonify({'erro': str(exc)}), 400
    finally:
        conn.close()


@app.route('/api/usuarios/<int:id>', methods=['PUT'])
def atualizar_usuario(id):
    payload = request.get_json(silent=True) or {}
    conn = get_db()
    atual = conn.execute('SELECT * FROM usuarios WHERE id=?', (id,)).fetchone()
    if not atual:
        conn.close()
        return jsonify({'erro': 'Usuário não encontrado.'}), 404
    try:
        perfil = _perfil(payload.get('perfil', atual['perfil']))
        ativo = 1 if payload.get('ativo', atual['ativo']) else 0
        nome = str(payload.get('nome', atual['nome'])).strip()
        if not nome:
            raise ValueError('Nome obrigatório.')
        if id == g.usuario['id'] and not ativo:
            raise ValueError('O administrador não pode desativar a própria sessão.')
        campos = {'nome': nome, 'perfil': perfil, 'ativo': ativo}
        if payload.get('senha'):
            from werkzeug.security import generate_password_hash
            campos['senha_hash'] = generate_password_hash(payload['senha'])
        assignments = ', '.join(f'{campo}=?' for campo in campos)
        conn.execute(f'UPDATE usuarios SET {assignments}, atualizado_em=CURRENT_TIMESTAMP WHERE id=?', (*campos.values(), id))
        registrar_evento(conn, 'usuário alterado', usuario=g.usuario['usuario'], status='sucesso', valor_anterior={'nome': atual['nome'], 'perfil': atual['perfil'], 'ativo': atual['ativo']}, valor_novo={'id': id, **{k: v for k, v in campos.items() if k != 'senha_hash'}})
        conn.commit()
        return jsonify({'status': 'atualizado'})
    except ValueError as exc:
        conn.rollback()
        return jsonify({'erro': str(exc)}), 400
    finally:
        conn.close()


@app.route('/api/orgaos', methods=['GET', 'POST'])
def orgaos_api():
    conn = get_db()
    conn.execute('CREATE TABLE IF NOT EXISTS orgaos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE, ordem INTEGER NOT NULL UNIQUE)')
    if request.method == 'GET':
        rows = conn.execute('SELECT * FROM orgaos ORDER BY ordem').fetchall()
        conn.close()
        return jsonify([dict(row) for row in rows])
    payload = request.get_json(silent=True) or {}
    nome = str(payload.get('nome', '')).strip()
    ordem = payload.get('ordem')
    if not nome or ordem is None:
        conn.close()
        return jsonify({'erro': 'Nome e ordem são obrigatórios.'}), 400
    try:
        cur = conn.execute('INSERT INTO orgaos (nome, ordem) VALUES (?, ?)', (nome, int(ordem)))
        registrar_evento(conn, 'órgão criado', usuario=g.usuario['usuario'], status='sucesso', valor_novo={'id': cur.lastrowid, 'nome': nome, 'ordem': ordem})
        conn.commit()
        return jsonify({'id': cur.lastrowid}), 201
    except (ValueError, sqlite3.IntegrityError) as exc:
        conn.rollback()
        return jsonify({'erro': str(exc)}), 400
    finally:
        conn.close()


@app.route('/api/orgaos/<int:id>', methods=['PUT'])
def atualizar_orgao(id):
    payload = request.get_json(silent=True) or {}
    conn = get_db()
    atual = conn.execute('SELECT * FROM orgaos WHERE id=?', (id,)).fetchone()
    if not atual:
        conn.close()
        return jsonify({'erro': 'Órgão não encontrado.'}), 404
    campos = {}
    if 'nome' in payload and str(payload['nome']).strip(): campos['nome'] = str(payload['nome']).strip()
    if 'ordem' in payload: campos['ordem'] = int(payload['ordem'])
    if not campos:
        conn.close()
        return jsonify({'erro': 'Nenhuma alteração informada.'}), 400
    try:
        assignments = ', '.join(f'{campo}=?' for campo in campos)
        conn.execute(f'UPDATE orgaos SET {assignments} WHERE id=?', (*campos.values(), id))
        registrar_evento(conn, 'órgão alterado', usuario=g.usuario['usuario'], status='sucesso', valor_anterior={'nome': atual['nome'], 'ordem': atual['ordem']}, valor_novo={'id': id, **campos})
        conn.commit()
        return jsonify({'status': 'atualizado'})
    except (ValueError, sqlite3.IntegrityError) as exc:
        conn.rollback()
        return jsonify({'erro': str(exc)}), 400
    finally:
        conn.close()


@app.route('/api/faturas/<int:id>/corrigir', methods=['POST'])
def corrigir_dados_extraidos(id):
    payload = request.get_json(silent=True) or {}
    permitidos = ('fornecedor', 'servico', 'complemento', 'competencia', 'numero_fatura', 'descricao_extraida')
    conn = get_db()
    fatura = conn.execute('SELECT * FROM faturas WHERE id=?', (id,)).fetchone()
    if not fatura:
        conn.close()
        return jsonify({'erro': 'Fatura não encontrada.'}), 404
    if str(fatura['status'] or '').upper() in {'LANÇADO', 'LANCADO', 'CONCILIADO', 'RECONCILIADO'}:
        registrar_evento(conn, 'alteração bloqueada', fatura_id=id, arquivo=fatura['nome_arquivo'], usuario=g.usuario['usuario'], status='negado', observacao='Tentativa de alterar lançamento conciliado')
        conn.commit()
        conn.close()
        return jsonify({'erro': 'Lançamento conciliado não pode ser alterado.'}), 409
    alteracoes = {campo: str(payload[campo]).strip() for campo in permitidos if campo in payload}
    proibidos = {'percentual', 'percentuais', 'orgao_beneficiario', 'planilha', 'valor_rateio', 'lancamento'} & set(payload)
    if proibidos:
        registrar_evento(conn, 'alteração bloqueada', fatura_id=id, arquivo=fatura['nome_arquivo'], usuario=g.usuario['usuario'], status='negado', valor_novo={campo: payload[campo] for campo in proibidos}, observacao='Campos protegidos não podem ser alterados pelo operador')
        conn.commit()
        conn.close()
        return jsonify({'erro': 'Percentuais, beneficiários, planilhas e lançamentos não podem ser alterados nesta operação.'}), 403
    if not alteracoes:
        conn.close()
        return jsonify({'erro': 'Nenhum dado extraído permitido foi informado.'}), 400
    anterior = {campo: fatura[campo] for campo in alteracoes if campo in fatura.keys()}
    assignments = ', '.join(f'{campo}=?' for campo in alteracoes)
    if 'atualizado_em' in {row[1] for row in conn.execute('PRAGMA table_info(faturas)').fetchall()}:
        assignments += ', atualizado_em=CURRENT_TIMESTAMP'
    conn.execute(f'UPDATE faturas SET {assignments} WHERE id=?', (*alteracoes.values(), id))
    registrar_evento(conn, 'alteração manual', fatura_id=id, arquivo=fatura['nome_arquivo'], usuario=g.usuario['usuario'], status='sucesso', valor_anterior=anterior, valor_novo=alteracoes, observacao='Correção de dados extraídos')
    conn.commit(); conn.close()
    return jsonify({'status': 'corrigido', 'fatura_id': id})


@app.route('/')
@app.route('/dashboard')
@app.route('/faturas')
@app.route('/faturas/todas')
@app.route('/faturas/compartilhadas')
@app.route('/faturas/exclusivas')
@app.route('/faturas/revisao')
@app.route('/regras-rateio')
@app.route('/exportar-relatorio')
@app.route('/logs')
@app.route('/cobrancas')
@app.route('/cobrancas/pendentes')
@app.route('/cobrancas/proximas-vencimento')
@app.route('/cobrancas/vencidas')
@app.route('/cobrancas/regras')
@app.route('/cobrancas/destinatarios')
@app.route('/cobrancas/mensagens')
def routes_frontend():
    return send_from_directory('static', 'index.html')


@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(load_config())


@app.route('/api/config', methods=['POST'])
def save_config():
    payload = request.get_json(silent=True) or {}
    anterior = load_config()
    try:
        _backup_antes('alteracao_configuracao')
    except (OSError, sqlite3.Error, ValueError) as exc:
        return jsonify({'erro': f'Backup obrigatório não criado: {exc}'}), 503
    salvo = salvar_configuracao(payload, BASE_PATH)
    conn = get_db()
    registrar_evento(conn, 'alteração de regra', usuario=g.usuario['usuario'],
                     valor_anterior=anterior, valor_novo=salvo,
                     observacao='Configuração operacional alterada')
    conn.commit(); conn.close()
    ok, mensagem = validar_configuracao(salvo)
    return jsonify({'status': 'ok' if ok else 'pendente', 'config': salvo, 'mensagem': mensagem})


@app.route('/api/integracao-whatsapp/configuracao', methods=['GET', 'POST'])
def configuracao_whatsapp_api():
    if request.method == 'GET':
        config = load_config()
        return jsonify(validar_configuracao_whatsapp(config))
    payload = request.get_json(silent=True) or {}
    if any(chave in payload for chave in ('cobrancas_whatsapp_access_token', 'cobrancas_whatsapp_webhook_verify_token')):
        return jsonify({'erro': 'Segredos devem ser fornecidos por variáveis de ambiente; somente o nome da variável é aceito.'}), 400
    atual = load_config()
    candidato = {**atual, **payload}
    validacao = validar_configuracao_whatsapp(candidato)
    if validacao['status'] == 'producao_bloqueada':
        return jsonify(validacao), 409
    try:
        _backup_antes('configuracao_whatsapp')
        salvo = salvar_configuracao(candidato, BASE_PATH)
        conn = get_db()
        registrar_evento(conn, 'configuração_whatsapp', usuario=g.usuario['usuario'], status=validacao['status'], valor_novo=configuracao_auditoria(salvo), observacao='Configuração segura do adaptador oficial')
        conn.commit(); conn.close()
        return jsonify(validar_configuracao_whatsapp(salvo))
    except (OSError, sqlite3.Error, ValueError) as exc:
        return jsonify({'erro': f'Configuração não alterada: {exc}'}), 503


def normalizar_classificacao(valor):
    if valor is None:
        return 'SEM_CLASSIFICACAO'
    texto = str(valor).strip().upper()
    texto = texto.replace('REVIS?O', 'REVISÃO')
    texto = texto.replace('REVISAO', 'REVISÃO')
    texto = texto.replace('REVISÃO', 'REVISÃO')
    texto = texto.replace('REVISAO', 'REVISÃO')
    texto = texto.replace('?', '')
    if texto == 'SEM_CLASSIFICACAO':
        return 'SEM_CLASSIFICACAO'
    return texto


def _classificacao_sql():
    return {
        'compartilhadas': "UPPER(COALESCE(f.classificacao, '')) = 'COMPARTILHADA'",
        'exclusivas': "UPPER(COALESCE(f.classificacao, '')) = 'EXCLUSIVA'",
        'revisao': "UPPER(COALESCE(f.classificacao, '')) IN ('AGUARDANDO_REVISÃO', 'AGUARDANDO_REVISAO', 'REVISAO', 'REVISÃO') OR UPPER(COALESCE(f.status, '')) IN ('AGUARDANDO_REVISÃO', 'AGUARDANDO_REVISAO', 'REVISAO', 'REVISÃO')",
        'erros': "UPPER(COALESCE(f.classificacao, '')) LIKE 'ERRO%' OR UPPER(COALESCE(f.status, '')) LIKE 'ERRO%'",
        'duplicadas': "UPPER(COALESCE(f.classificacao, '')) LIKE 'DUPLICAD%' OR UPPER(COALESCE(f.status, '')) LIKE 'DUPLICAD%'",
    }


@app.route('/api/stats')
def get_stats():
    conn = get_db()
    cur = conn.cursor()
    valor_expr = 'COALESCE(f.valor_base, f.valor_total, 0)'
    cur.execute(f'SELECT COUNT(*), COALESCE(SUM({valor_expr}), 0) FROM faturas f')
    total_quantidade, total_valor = cur.fetchone()
    classificacoes = {}
    for chave, filtro in _classificacao_sql().items():
        cur.execute(f'SELECT COUNT(*), COALESCE(SUM({valor_expr}), 0) FROM faturas f WHERE {filtro}')
        quantidade, valor = cur.fetchone()
        classificacoes[chave] = {'quantidade': quantidade, 'valor': round(valor or 0, 2)}
    cur.execute('SELECT status, COUNT(*) FROM faturas GROUP BY status')
    by_status = {row[0] or 'SEM_STATUS': row[1] for row in cur.fetchall()}
    config = load_config()
    entrada = Path(config.get('entrada_path', '')) if config.get('entrada_path') else None
    pendentes = sum(1 for item in entrada.iterdir() if item.is_file()) if entrada and entrada.is_dir() else 0
    logs_exists = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='logs_processamento'").fetchone()
    ultima = cur.execute('SELECT MAX(criado_em) FROM logs_processamento').fetchone()[0] if logs_exists else None
    cur.execute(f"SELECT COALESCE(NULLIF(f.servico, ''), s.nome, 'Não identificado') AS nome, COUNT(*) AS quantidade, COALESCE(SUM({valor_expr}), 0) AS valor FROM faturas f LEFT JOIN servicos s ON s.id=f.servico_id GROUP BY 1 ORDER BY 3 DESC")
    servicos = [dict(row) for row in cur.fetchall()]
    cur.execute(f"SELECT COALESCE(NULLIF(competencia, ''), substr(CAST(criado_em AS TEXT), 1, 7), 'Não identificado') AS mes, COUNT(*) AS quantidade, COALESCE(SUM({valor_expr}), 0) AS valor FROM faturas f GROUP BY 1 ORDER BY 1")
    meses = [dict(row) for row in cur.fetchall()]
    cur.execute("SELECT UPPER(COALESCE(NULLIF(classificacao, ''), 'SEM_CLASSIFICACAO')) AS classificacao, COUNT(*) AS quantidade, COALESCE(SUM(COALESCE(valor_base, valor_total, 0)), 0) AS valor FROM faturas GROUP BY 1 ORDER BY 2 DESC")
    classificacoes_grafico = []
    for row in cur.fetchall():
        item = dict(row)
        item['classificacao'] = normalizar_classificacao(item.get('classificacao'))
        classificacoes_grafico.append(item)
    cur.execute("SELECT o.nome, COUNT(DISTINCT r.fatura_id) AS quantidade, COALESCE(SUM(r.valor_rateio), 0) AS valor FROM rateios_calculados r JOIN orgaos o ON o.id=r.orgao_id GROUP BY o.id, o.nome ORDER BY valor DESC")
    orgaos = [dict(row) for row in cur.fetchall()]
    resposta = {
        'total_faturas': total_quantidade or 0,
        'valor_total': round(total_valor or 0, 2),
        'classificacoes': classificacoes,
        'status': by_status,
        'pendentes_entrada': pendentes,
        'ultima_execucao': ultima,
        'backend': {'status': 'online', 'timestamp': datetime.now().isoformat()},
        'graficos': {'servicos': servicos, 'orgaos': orgaos, 'meses': meses, 'classificacoes': classificacoes_grafico},
        'filtros': {
            'competencias': [r[0] for r in cur.execute("SELECT DISTINCT competencia FROM faturas WHERE competencia IS NOT NULL AND competencia<>'' ORDER BY competencia DESC")],
            'fornecedores': [r[0] for r in cur.execute("SELECT DISTINCT COALESCE(NULLIF(fornecedor,''), fornecedor_extraido) FROM faturas WHERE COALESCE(NULLIF(fornecedor,''), fornecedor_extraido) IS NOT NULL ORDER BY 1")],
            'servicos': [r[0] for r in cur.execute("SELECT DISTINCT COALESCE(NULLIF(f.servico,''), s.nome) FROM faturas f LEFT JOIN servicos s ON s.id=f.servico_id WHERE COALESCE(NULLIF(f.servico,''), s.nome) IS NOT NULL ORDER BY 1")],
            'orgaos': [r[0] for r in cur.execute('SELECT nome FROM orgaos ORDER BY ordem')],
            'status': [r[0] for r in cur.execute("SELECT DISTINCT status FROM faturas WHERE status IS NOT NULL AND status<>'' ORDER BY status")],
            'classificacoes': [r[0] for r in cur.execute("SELECT DISTINCT classificacao FROM faturas WHERE classificacao IS NOT NULL AND classificacao<>'' ORDER BY classificacao")],
        },
    }
    conn.close()
    return jsonify(resposta)


@app.route('/api/rateios')
def get_rateios():
    conn = get_db()
    rows = conn.execute('SELECT p.orgao_id, p.percentual, o.nome AS orgao_nome, p.nome AS padrao FROM padroes_rateio p JOIN orgaos o ON o.id=p.orgao_id ORDER BY o.ordem').fetchall()
    conn.close()
    return jsonify({'padrao_a': [dict(r) for r in rows if r['padrao'] == 'A'], 'padrao_b': [dict(r) for r in rows if r['padrao'] == 'B']})


@app.route('/api/rateios/<padrao>/<int:orgao_id>', methods=['PUT'])
def atualizar_rateio(padrao, orgao_id):
    padrao = str(padrao).strip().upper()
    payload = request.get_json(silent=True) or {}
    try:
        percentual = float(payload.get('percentual'))
    except (TypeError, ValueError):
        return jsonify({'erro': 'Percentual inválido.'}), 400
    if padrao not in {'A', 'B'} or not 0 <= percentual <= 100:
        return jsonify({'erro': 'Informe um percentual entre 0 e 100.'}), 400
    conn = get_db()
    atual = conn.execute('SELECT id FROM padroes_rateio WHERE nome=? AND orgao_id=?', (padrao, orgao_id)).fetchone()
    if not atual:
        conn.close()
        return jsonify({'erro': 'Rateio não encontrado.'}), 404
    total = conn.execute('SELECT COALESCE(SUM(percentual), 0) FROM padroes_rateio WHERE nome=? AND orgao_id<>?', (padrao, orgao_id)).fetchone()[0]
    total_com_novo = round(total + percentual, 2)
    if not 99.99 <= total_com_novo <= 100.01:
        conn.close()
        return jsonify({'erro': f'O padrão {padrao} deve totalizar 100%. Total informado: {total + percentual:.2f}%.'}), 400
    conn.execute('UPDATE padroes_rateio SET percentual=? WHERE nome=? AND orgao_id=?', (round(percentual, 2), padrao, orgao_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'atualizado', 'padrao': padrao, 'orgao_id': orgao_id, 'percentual': round(percentual, 2)})


@app.route('/api/faturas')
def get_faturas():
    params = request.args
    conn = get_db()
    query = 'SELECT f.*, s.nome AS servico_nome FROM faturas f LEFT JOIN servicos s ON f.servico_id=s.id'
    where, values = [], []
    status = params.get('status')
    if status:
        if status.upper() == 'AGUARDANDO_REVISÃO':
            where.append("UPPER(COALESCE(f.status,'')) IN ('AGUARDANDO_REVISÃO','AGUARDANDO_REVISAO','REVISAO','REVISÃO')")
        else:
            where.append("UPPER(COALESCE(f.status,''))=UPPER(?)"); values.append(status)
    if params.get('classificacao'):
        where.append("UPPER(COALESCE(f.classificacao,''))=UPPER(?)"); values.append(params['classificacao'])
    for campo in ('competencia',):
        if params.get(campo):
            where.append(f'f.{campo}=?'); values.append(params[campo])
    if params.get('fornecedor'):
        where.append("UPPER(COALESCE(NULLIF(f.fornecedor,''), f.fornecedor_extraido,'')) LIKE UPPER(?)"); values.append(f"%{params['fornecedor']}%")
    if params.get('servico'):
        where.append("UPPER(COALESCE(NULLIF(f.servico,''), s.nome,'')) LIKE UPPER(?)"); values.append(f"%{params['servico']}%")
    if params.get('orgao'):
        where.append("(UPPER(COALESCE(f.orgao_beneficiario,''))=UPPER(?) OR EXISTS (SELECT 1 FROM rateios_calculados rf JOIN orgaos oo ON oo.id=rf.orgao_id WHERE rf.fatura_id=f.id AND UPPER(oo.nome)=UPPER(?)))")
        values.extend([params['orgao'], params['orgao']])
    if where:
        query += ' WHERE ' + ' AND '.join(where)
    rows = conn.execute(query + ' ORDER BY f.criado_em DESC', values).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


def _registrar_revisao(conn, fatura_id, acao, usuario, justificativa, anterior, novo):
    conn.execute(
        '''INSERT INTO auditoria
           (tabela_origem, registro_id, acao, usuario, dados_anterior, dados_novo, observacao, resultado)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        ('faturas', fatura_id, acao, usuario, json.dumps(anterior, ensure_ascii=False), json.dumps(novo, ensure_ascii=False), justificativa, 'decisão manual'),
    )
    registrar_evento(conn, 'alteração manual', fatura_id=fatura_id, usuario=usuario,
                     status='registrada', valor_anterior=anterior, valor_novo=novo,
                     observacao=justificativa)
    registrar_evento(conn, 'aprovação' if acao == 'revisao' else 'rejeição',
                     fatura_id=fatura_id, usuario=usuario, status=novo.get('status'),
                     valor_anterior=anterior, valor_novo=novo, observacao=justificativa)


def _garantir_colunas_revisao(conn):
    existentes = {row[1] for row in conn.execute('PRAGMA table_info(faturas)').fetchall()}
    for nome, tipo in (('complemento', 'TEXT'), ('regra_utilizada', 'TEXT'), ('motivo_revisao', 'TEXT'),):
        if nome not in existentes:
            conn.execute(f'ALTER TABLE faturas ADD COLUMN {nome} {tipo}')


def _garantir_regras_administrativas(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS regras_administrativas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id INTEGER NOT NULL,
            versao INTEGER NOT NULL,
            servico TEXT,
            fornecedor TEXT,
            complemento TEXT,
            secao TEXT,
            classificacao TEXT,
            unidade TEXT,
            endereco TEXT,
            orgao_beneficiario TEXT,
            percentuais TEXT,
            vigencia_inicio TEXT NOT NULL,
            vigencia_fim TEXT,
            observacoes TEXT,
            ativo INTEGER NOT NULL DEFAULT 1,
            usuario TEXT NOT NULL,
            justificativa TEXT NOT NULL,
            criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(grupo_id, versao)
        )
    ''')


def _regra_payload(payload):
    campos = ('servico', 'fornecedor', 'complemento', 'secao', 'classificacao', 'unidade', 'endereco', 'orgao_beneficiario', 'percentuais', 'vigencia_inicio', 'vigencia_fim', 'observacoes')
    return {campo: payload.get(campo) for campo in campos}


COBRANCA_RULE_FIELDS = (
    'nome', 'descricao', 'dias_antes_vencimento', 'dias_depois_vencimento', 'cobrar_vencidas',
    'cobrar_proximas', 'valor_minimo', 'servicos_json', 'fornecedores_json', 'orgaos_json',
    'destinatarios_json', 'modelo_mensagem', 'exigir_aprovacao', 'limite_diario',
    'intervalo_minimo_segundos', 'horario_permitido',
)


def _garantir_cobranca_api(conn):
    tabelas = {'contas', 'regras_cobranca', 'destinatarios', 'mapeamentos_planilha'}
    existentes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if not tabelas <= existentes:
        _backup_antes('migracao_banco')
    ensure_cobrancas_tables(conn)
    conn.commit()


def _cobranca_rule_payload(payload):
    dados = {campo: payload.get(campo) for campo in COBRANCA_RULE_FIELDS if campo in payload}
    for campo in ('servicos_json', 'fornecedores_json', 'orgaos_json', 'destinatarios_json'):
        if campo in dados and isinstance(dados[campo], (list, dict)):
            dados[campo] = json.dumps(dados[campo], ensure_ascii=False)
    return dados


def _registrar_auditoria_cobranca(conn, acao, registro_id, anterior, novo, usuario, observacao=''):
    conn.execute('''INSERT INTO auditoria_cobranca
        (tabela_origem, registro_id, acao, usuario, dados_anterior, dados_novo, origem, observacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        ('regras_cobranca', registro_id, acao, usuario, json.dumps(anterior, ensure_ascii=False, default=str),
         json.dumps(novo, ensure_ascii=False, default=str), 'api', observacao))


@app.route('/api/regras-cobranca', methods=['GET', 'POST'])
def regras_cobranca_api():
    conn = get_db()
    _garantir_cobranca_api(conn)
    if request.method == 'GET':
        ativas = request.args.get('ativas')
        query = 'SELECT * FROM regras_cobranca'
        valores = []
        if ativas in {'true', 'false'}:
            query += ' WHERE ativa=?'; valores.append(1 if ativas == 'true' else 0)
        rows = conn.execute(query + ' ORDER BY nome', valores).fetchall()
        conn.close()
        return jsonify([dict(row) for row in rows])

    payload = request.get_json(silent=True) or {}
    dados = _cobranca_rule_payload(payload)
    if not str(dados.get('nome') or '').strip():
        conn.close(); return jsonify({'erro': 'Nome da regra é obrigatório.'}), 400
    ativa = bool(payload.get('ativa', False))
    if ativa and not payload.get('confirmacao_previa'):
        conn.close(); return jsonify({'erro': 'Prévia obrigatória antes de ativar a regra.', 'preview_obrigatoria': True}), 409
    usuario = g.usuario['usuario']
    dados['ativa'] = 1 if ativa else 0
    dados['usuario_criador'] = usuario
    try:
        _backup_antes('alteracao_regra_cobranca')
        cur = conn.execute('''INSERT INTO regras_cobranca
            (nome, descricao, dias_antes_vencimento, dias_depois_vencimento, cobrar_vencidas, cobrar_proximas,
             valor_minimo, servicos_json, fornecedores_json, orgaos_json, destinatarios_json, modelo_mensagem,
             exigir_aprovacao, limite_diario, intervalo_minimo_segundos, horario_permitido, ativa, usuario_criador)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            tuple(dados.get(campo) for campo in ('nome', 'descricao', 'dias_antes_vencimento', 'dias_depois_vencimento', 'cobrar_vencidas', 'cobrar_proximas', 'valor_minimo', 'servicos_json', 'fornecedores_json', 'orgaos_json', 'destinatarios_json', 'modelo_mensagem', 'exigir_aprovacao', 'limite_diario', 'intervalo_minimo_segundos', 'horario_permitido')) + (dados['ativa'], usuario))
        registro_id = cur.lastrowid
        _registrar_auditoria_cobranca(conn, 'criação', registro_id, {}, dados, usuario)
        conn.commit()
        return jsonify({'status': 'criada', 'id': registro_id}), 201
    except (OSError, sqlite3.Error, ValueError) as exc:
        conn.rollback(); return jsonify({'erro': str(exc)}), 409
    finally:
        conn.close()


@app.route('/api/regras-cobranca/<int:id>', methods=['GET', 'PUT', 'DELETE'])
def regra_cobranca_api(id):
    conn = get_db(); _garantir_cobranca_api(conn)
    atual = conn.execute('SELECT * FROM regras_cobranca WHERE id=?', (id,)).fetchone()
    if not atual:
        conn.close(); return jsonify({'erro': 'Regra de cobrança não encontrada.'}), 404
    anterior = dict(atual)
    if request.method == 'GET':
        conn.close(); return jsonify(anterior)
    usuario = g.usuario['usuario']
    if request.method == 'DELETE':
        try:
            _backup_antes('alteracao_regra_cobranca')
        except (OSError, sqlite3.Error, ValueError) as exc:
            conn.close(); return jsonify({'erro': f'Backup obrigatório não criado: {exc}'}), 503
        conn.execute('UPDATE regras_cobranca SET ativa=0, alterada_em=CURRENT_TIMESTAMP WHERE id=?', (id,))
        _registrar_auditoria_cobranca(conn, 'desativação', id, anterior, {'ativa': 0}, usuario)
    else:
        payload = request.get_json(silent=True) or {}
        dados = _cobranca_rule_payload(payload)
        if 'ativa' in payload:
            dados['ativa'] = 1 if payload['ativa'] else 0
        if dados.get('ativa') == 1 and not payload.get('confirmacao_previa') and not anterior['ativa']:
            conn.close(); return jsonify({'erro': 'Prévia obrigatória antes de ativar a regra.', 'preview_obrigatoria': True}), 409
        if not dados:
            conn.close(); return jsonify({'erro': 'Nenhum campo para alterar.'}), 400
        try:
            _backup_antes('alteracao_regra_cobranca')
        except (OSError, sqlite3.Error, ValueError) as exc:
            conn.close(); return jsonify({'erro': f'Backup obrigatório não criado: {exc}'}), 503
        assignments = ', '.join(f'{campo}=?' for campo in dados)
        conn.execute(f'UPDATE regras_cobranca SET {assignments}, alterada_em=CURRENT_TIMESTAMP WHERE id=?', (*dados.values(), id))
        _registrar_auditoria_cobranca(conn, 'alteração', id, anterior, dados, usuario)
    conn.commit(); conn.close()
    return jsonify({'status': 'atualizada', 'id': id})


@app.route('/api/regras-cobranca/<int:id>/preview', methods=['POST'])
def preview_regra_cobranca(id):
    conn = get_db(); _garantir_cobranca_api(conn)
    regra = conn.execute('SELECT * FROM regras_cobranca WHERE id=?', (id,)).fetchone()
    if not regra:
        conn.close(); return jsonify({'erro': 'Regra de cobrança não encontrada.'}), 404
    where = ['COALESCE(valor_pendente, 0) > 0']
    valores = []
    if regra['valor_minimo'] is not None:
        where.append('COALESCE(valor_pendente, 0) >= ?'); valores.append(regra['valor_minimo'])
    rows = conn.execute('SELECT id, identificador, orgao, unidade, fornecedor, servico, competencia, data_vencimento, valor_pendente, status FROM contas WHERE ' + ' AND '.join(where) + ' ORDER BY data_vencimento, id LIMIT 500', valores).fetchall()
    resultado = {'regra_id': id, 'quantidade': len(rows), 'contas': [dict(row) for row in rows], 'somente_previa': True}
    conn.close()
    return jsonify(resultado)


@app.route('/api/destinatarios', methods=['GET', 'POST'])
def destinatarios_api():
    conn = get_db(); _garantir_cobranca_api(conn)
    if request.method == 'GET':
        rows = conn.execute('SELECT * FROM destinatarios ORDER BY nome').fetchall()
        conn.close()
        return jsonify([_proteger_telefone(row) for row in rows])
    payload = request.get_json(silent=True) or {}
    nome = str(payload.get('nome') or '').strip()
    tipo = str(payload.get('tipo') or '').strip()
    if not nome or not tipo:
        conn.close(); return jsonify({'erro': 'Nome e tipo são obrigatórios.'}), 400
    try:
        telefone = _normalizar_telefone(payload.get('telefone'))
    except ValueError as exc:
        conn.close(); return jsonify({'erro': str(exc)}), 400
    try:
        _backup_antes('alteracao_destinatario')
        cur = conn.execute('''INSERT INTO destinatarios
            (nome, orgao, unidade, telefone, tipo, ativo, autorizacao_registrada, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (nome, payload.get('orgao'), payload.get('unidade'), telefone, tipo,
             1 if payload.get('ativo', True) else 0, 1 if payload.get('autorizacao_registrada') else 0,
             payload.get('observacao')))
        _auditar_destinatario(conn, 'criação', cur.lastrowid, None, {
            'id': cur.lastrowid, 'nome': nome, 'orgao': payload.get('orgao'),
            'unidade': payload.get('unidade'), 'telefone': telefone, 'tipo': tipo,
            'ativo': 1 if payload.get('ativo', True) else 0,
            'autorizacao_registrada': 1 if payload.get('autorizacao_registrada') else 0,
            'observacao': payload.get('observacao'),
        }, g.usuario['usuario'])
        conn.commit()
        return jsonify({'id': cur.lastrowid}), 201
    except (OSError, sqlite3.Error, ValueError) as exc:
        conn.rollback(); return jsonify({'erro': f'Não foi possível cadastrar destinatário: {exc}'}), 409
    finally:
        conn.close()


@app.route('/api/destinatarios/<int:id>', methods=['PUT'])
def atualizar_destinatario(id):
    payload = request.get_json(silent=True) or {}
    conn = get_db(); _garantir_cobranca_api(conn)
    atual = conn.execute('SELECT * FROM destinatarios WHERE id=?', (id,)).fetchone()
    if not atual:
        conn.close(); return jsonify({'erro': 'Destinatário não encontrado.'}), 404
    campos = {campo: payload[campo] for campo in ('nome', 'orgao', 'unidade', 'telefone', 'tipo', 'ativo', 'autorizacao_registrada', 'observacao') if campo in payload}
    if not campos:
        conn.close(); return jsonify({'erro': 'Nenhuma alteração informada.'}), 400
    try:
        if 'telefone' in campos:
            campos['telefone'] = _normalizar_telefone(campos['telefone'])
    except ValueError as exc:
        conn.close(); return jsonify({'erro': str(exc)}), 400
    try:
        _backup_antes('alteracao_destinatario')
        assignments = ', '.join(f'{campo}=?' for campo in campos)
        conn.execute(f'UPDATE destinatarios SET {assignments}, atualizado_em=CURRENT_TIMESTAMP WHERE id=?', (*campos.values(), id))
        novo = dict(atual); novo.update(campos)
        acao = 'desativação' if 'ativo' in campos and not campos['ativo'] else 'alteração'
        _auditar_destinatario(conn, acao, id, dict(atual), novo, g.usuario['usuario'])
        conn.commit()
        return jsonify({'status': 'atualizado'})
    except (OSError, sqlite3.Error, ValueError) as exc:
        conn.rollback(); return jsonify({'erro': f'Não foi possível alterar destinatário: {exc}'}), 409
    finally:
        conn.close()


@app.route('/api/mapeamentos-planilha', methods=['GET', 'POST'])
def mapeamentos_planilha_api():
    conn = get_db(); _garantir_cobranca_api(conn)
    if request.method == 'GET':
        rows = conn.execute('SELECT * FROM mapeamentos_planilha ORDER BY versao DESC').fetchall()
        conn.close(); return jsonify([dict(row) for row in rows])
    payload = request.get_json(silent=True) or {}
    versao = payload.get('versao')
    aba = str(payload.get('aba') or '').strip()
    colunas = payload.get('colunas_json', payload.get('colunas'))
    if versao is None or not aba or colunas is None:
        conn.close(); return jsonify({'erro': 'Versão, aba e colunas são obrigatórios.'}), 400
    try:
        _backup_antes('alteracao_mapeamento')
        cur = conn.execute('''INSERT INTO mapeamentos_planilha
            (versao, aba, colunas_json, observacoes, usuario, ativa)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (int(versao), aba, json.dumps(colunas, ensure_ascii=False) if not isinstance(colunas, str) else colunas,
             payload.get('observacoes'), g.usuario['usuario'], 1 if payload.get('ativa') else 0))
        conn.commit(); return jsonify({'id': cur.lastrowid}), 201
    except (OSError, sqlite3.Error, ValueError) as exc:
        conn.rollback(); return jsonify({'erro': f'Não foi possível cadastrar mapeamento: {exc}'}), 409
    finally:
        conn.close()


@app.route('/api/regras-administrativas', methods=['GET'])
def listar_regras_administrativas():
    conn = get_db()
    _garantir_regras_administrativas(conn)
    somente_ativas = request.args.get('ativas', 'true').lower() != 'false'
    query = 'SELECT * FROM regras_administrativas'
    if somente_ativas:
        query += ' WHERE ativo = 1'
    rows = conn.execute(query + ' ORDER BY grupo_id, versao DESC').fetchall()
    conn.commit(); conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/api/regras-administrativas', methods=['POST'])
def cadastrar_regra_administrativa():
    payload = request.get_json(silent=True) or {}
    usuario = g.usuario['usuario']
    justificativa = str(payload.get('justificativa', '')).strip()
    if not payload.get('confirmacao'):
        return jsonify({'erro': 'Confirmação explícita obrigatória.'}), 400
    if not usuario or not justificativa:
        return jsonify({'erro': 'Usuário e justificativa são obrigatórios.'}), 400
    dados = _regra_payload(payload)
    if not dados['vigencia_inicio']:
        return jsonify({'erro': 'Vigência inicial obrigatória.'}), 400
    try:
        _backup_antes('alteracao_regra')
    except (OSError, sqlite3.Error, ValueError) as exc:
        return jsonify({'erro': f'Backup obrigatório não criado: {exc}'}), 503
    conn = get_db(); _garantir_regras_administrativas(conn)
    grupo_id = payload.get('grupo_id')
    if grupo_id is None:
        grupo_id = conn.execute('SELECT COALESCE(MAX(grupo_id), 0) + 1 FROM regras_administrativas').fetchone()[0]
    ultima = conn.execute('SELECT COALESCE(MAX(versao), 0) FROM regras_administrativas WHERE grupo_id = ?', (grupo_id,)).fetchone()[0]
    versao = int(payload.get('versao') or ultima + 1)
    if versao <= ultima:
        conn.close(); return jsonify({'erro': 'Versão deve ser maior que a versão atual.'}), 409
    colunas = ', '.join(['grupo_id', 'versao', *dados.keys(), 'usuario', 'justificativa'])
    placeholders = ', '.join('?' for _ in range(2 + len(dados) + 2))
    valores = [grupo_id, versao, *dados.values(), usuario, justificativa]
    cur = conn.execute(f'INSERT INTO regras_administrativas ({colunas}) VALUES ({placeholders})', valores)
    registrar_evento(conn, 'alteração de regra', usuario=usuario, status='cadastrada',
                     valor_novo={'grupo_id': grupo_id, 'versao': versao, **dados},
                     observacao=justificativa)
    conn.commit(); conn.close()
    return jsonify({'status': 'cadastrada', 'id': cur.lastrowid, 'grupo_id': grupo_id, 'versao': versao}), 201


@app.route('/api/faturas/revisao')
def listar_faturas_revisao():
    conn = get_db()
    rows = conn.execute('''
        SELECT f.*, COALESCE(NULLIF(f.servico, ''), s.nome) AS servico_nome
        FROM faturas f LEFT JOIN servicos s ON s.id = f.servico_id
        WHERE UPPER(COALESCE(f.status, '')) IN ('REVISAO', 'REVISÃO', 'AGUARDANDO_REVISÃO', 'AGUARDANDO_REVISAO')
           OR UPPER(COALESCE(f.classificacao, '')) IN ('REVISAO', 'REVISÃO', 'AGUARDANDO_REVISÃO', 'AGUARDANDO_REVISAO')
        ORDER BY f.criado_em ASC
    ''').fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/api/faturas/<int:id>/revisao', methods=['POST'])
def decidir_revisao(id):
    payload = request.get_json(silent=True) or {}
    acao = str(payload.get('acao', '')).strip().lower()
    usuario = g.usuario['usuario']
    justificativa = str(payload.get('justificativa', '')).strip()
    permitidas = {'aprovar_compartilhada', 'aprovar_exclusiva', 'rejeitar', 'reenviar'}
    if acao not in permitidas:
        return jsonify({'erro': 'Ação de revisão inválida.'}), 400
    if not justificativa:
        return jsonify({'erro': 'Justificativa obrigatória.'}), 400
    conn = get_db()
    _garantir_colunas_revisao(conn)
    fatura = conn.execute('SELECT * FROM faturas WHERE id = ?', (id,)).fetchone()
    if not fatura:
        conn.close()
        return jsonify({'erro': 'Fatura não encontrada.'}), 404
    anterior = dict(fatura)
    if str(fatura['status'] or '').upper() not in {'REVISAO', 'REVISÃO', 'AGUARDANDO_REVISÃO', 'AGUARDANDO_REVISAO'} and str(fatura['classificacao'] or '').upper() not in {'REVISAO', 'REVISÃO', 'AGUARDANDO_REVISÃO', 'AGUARDANDO_REVISAO'}:
        conn.close()
        return jsonify({'erro': 'A fatura não está em revisão.'}), 409

    campos = {
        chave: payload[chave].strip() for chave in ('fornecedor', 'servico', 'complemento', 'competencia', 'orgao_beneficiario', 'regra_utilizada')
        if isinstance(payload.get(chave), str) and payload[chave].strip()
    }
    if acao in {'aprovar_compartilhada', 'aprovar_exclusiva'}:
        if not campos.get('fornecedor') or not campos.get('servico') or not campos.get('competencia'):
            conn.close()
            return jsonify({'erro': 'Fornecedor, serviço e competência são obrigatórios para aprovação.'}), 400
        if acao == 'aprovar_exclusiva' and not campos.get('orgao_beneficiario'):
            conn.close()
            return jsonify({'erro': 'Órgão beneficiário é obrigatório para aprovação exclusiva.'}), 400
        classificacao = 'COMPARTILHADA' if acao == 'aprovar_compartilhada' else 'EXCLUSIVA'
        campos['classificacao'] = classificacao
        campos['status'] = 'REPROCESSAMENTO_PENDENTE'
        campos['motivo_revisao'] = None
        # A fatura sai de revisão, mas permanece bloqueada para lançamento até o reprocessamento validado.
        assignments = ', '.join(f'{chave} = ?' for chave in campos)
        conn.execute(f'UPDATE faturas SET {assignments}, atualizado_em = CURRENT_TIMESTAMP WHERE id = ?', (*campos.values(), id))
        _registrar_revisao(conn, id, 'revisao', usuario, justificativa, anterior, campos)
        conn.commit()
        conn.close()
        return jsonify({'status': 'REPROCESSAMENTO_PENDENTE', 'mensagem': 'Aprovação registrada. Cálculo, validação e lançamento aguardam reprocessamento validado.', 'fatura_id': id})

    if acao == 'rejeitar':
        campos = {'status': 'REJEITADA', 'classificacao': 'REJEITADA', 'motivo_revisao': justificativa}
    else:
        campos = {'status': 'REVISAO', 'classificacao': 'AGUARDANDO_REVISÃO', 'motivo_revisao': justificativa}
    assignments = ', '.join(f'{chave} = ?' for chave in campos)
    conn.execute(f'UPDATE faturas SET {assignments}, atualizado_em = CURRENT_TIMESTAMP WHERE id = ?', (*campos.values(), id))
    _registrar_revisao(conn, id, 'rejeicao' if acao == 'rejeitar' else 'revisao', usuario, justificativa, anterior, campos)
    conn.commit()
    conn.close()
    return jsonify({'status': campos['status'], 'fatura_id': id})


@app.route('/api/faturas/<int:id>/detalhes')
def get_fatura_detalhes(id):
    conn = get_db()
    rows = conn.execute('SELECT r.*, o.nome AS orgao_nome FROM rateios_calculados r JOIN orgaos o ON r.orgao_id=o.id WHERE r.fatura_id=? ORDER BY o.ordem', (id,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


def _tabela_existe(conn, nome):
    if os.getenv('DB_PROVIDER', 'sqlite').strip().lower() in {'postgres', 'postgresql'}:
        return conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() AND table_name=?",
            (nome,),
        ).fetchone() is not None
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone() is not None


def _data_alerta(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or '').strip()
    for formato in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(texto[:10], formato).date()
        except ValueError:
            continue
    return None


def _valor_alerta(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        texto = str(valor).strip().replace('R$', '').replace(' ', '')
        if ',' in texto:
            texto = texto.replace('.', '').replace(',', '.')
        resultado = Decimal(texto)
        return resultado if resultado.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _inteiro_config_alerta(config, chave, padrao=0):
    try:
        return max(0, int(str(config.get(chave, padrao)).strip()))
    except (TypeError, ValueError):
        return padrao


def _enriquecer_alerta_conta(conta, data_referencia, config):
    resultado = dict(conta)
    status = str(conta.get('status') or '').strip().upper()
    valor_pendente = _valor_alerta(conta.get('valor_pendente'))
    vencimento = _data_alerta(conta.get('data_vencimento'))
    dias = (vencimento - data_referencia).days if vencimento else None
    prioridade = 'NORMAL'
    motivo = 'Sem urgência identificada.'

    if status == 'DIVERGENTE':
        prioridade = 'URGENTE'
        motivo = 'Conta divergente; tratamento requer conferência.'
    elif status in {'SEM_DATA_DE_VENCIMENTO', 'SEM_VALOR', 'AGUARDANDO_REVISAO'} or not vencimento or valor_pendente is None:
        prioridade = 'URGENTE'
        motivo = 'Informação crítica ausente ou pendente de revisão.'
    elif status != 'PAGA' and valor_pendente > 0:
        if status == 'VENCIDA' or dias < 0:
            prioridade = 'URGENTE'
            motivo = 'Conta vencida com valor pendente.'
        elif dias <= 1:
            prioridade = 'URGENTE'
            motivo = 'Vencimento hoje ou amanhã.'
        elif dias <= 7:
            prioridade = 'ATENCAO'
            motivo = 'Vencimento entre 2 e 7 dias.'
        elif status == 'PROXIMA_DO_VENCIMENTO':
            prioridade = 'ATENCAO'
            motivo = 'Conta dentro da janela configurada de acompanhamento.'

    resultado.update({
        'data_referencia_alerta': data_referencia.isoformat(),
        'dias_para_vencimento': dias,
        'prioridade_visual': prioridade,
        'motivo_alerta': motivo,
    })
    return resultado


@app.route('/api/cobrancas/contas')
def listar_contas_cobranca():
    conn = get_db()
    if not _tabela_existe(conn, 'contas'):
        conn.close()
        return jsonify({'contas': [], 'total': 0, 'pagina': 1, 'por_pagina': 25, 'paginas': 0, 'estrutura_disponivel': False})
    params = request.args
    where, valores = [], []
    busca = str(params.get('busca', '')).strip()
    if busca:
        where.append("(orgao LIKE ? OR unidade LIKE ? OR servico LIKE ? OR fornecedor LIKE ? OR competencia LIKE ? OR identificador LIKE ?)")
        valores.extend([f'%{busca}%'] * 6)
    for campo in ('status', 'orgao', 'unidade', 'servico', 'fornecedor'):
        if params.get(campo):
            if campo == 'status' and params[campo] == 'PRÓXIMA_DO_VENCIMENTO':
                where.append("status IN (?, ?)"); valores.extend(['PRÓXIMA_DO_VENCIMENTO', 'PROXIMA_DO_VENCIMENTO'])
            elif campo == 'status' and params[campo] == 'AGUARDANDO_REVISÃO':
                where.append("status IN (?, ?)"); valores.extend(['AGUARDANDO_REVISÃO', 'AGUARDANDO_REVISAO'])
            else:
                where.append(f'{campo} = ?'); valores.append(params[campo])
    filtro = (' WHERE ' + ' AND '.join(where)) if where else ''
    ordenaveis = {'orgao', 'unidade', 'servico', 'fornecedor', 'competencia', 'data_vencimento', 'valor_pendente', 'status'}
    ordenar = params.get('ordenar', 'data_vencimento') if params.get('ordenar') in ordenaveis else 'data_vencimento'
    direcao = 'DESC' if str(params.get('direcao', '')).lower() == 'desc' else 'ASC'
    try:
        pagina = max(1, int(params.get('pagina', 1)))
        por_pagina = min(100, max(1, int(params.get('por_pagina', 25))))
    except ValueError:
        conn.close(); return jsonify({'erro': 'Paginação inválida.'}), 400
    total = conn.execute('SELECT COUNT(*) FROM contas' + filtro, valores).fetchone()[0]
    rows = conn.execute(f'SELECT * FROM contas{filtro} ORDER BY {ordenar} {direcao}, id ASC LIMIT ? OFFSET ?', (*valores, por_pagina, (pagina - 1) * por_pagina)).fetchall()
    conn.close()
    data_referencia = datetime.now().date()
    config = load_config()
    contas = [_enriquecer_alerta_conta(_proteger_telefone(row), data_referencia, config) for row in rows]
    return jsonify({
        'contas': contas,
        'total': total,
        'pagina': pagina,
        'por_pagina': por_pagina,
        'paginas': (total + por_pagina - 1) // por_pagina,
        'estrutura_disponivel': True,
        'alertas': {
            'data_referencia': data_referencia.isoformat(),
            'dias_antecedencia': _inteiro_config_alerta(config, 'cobrancas_dias_antecedencia'),
            'dias_vencida': _inteiro_config_alerta(config, 'cobrancas_dias_vencida'),
        },
    })


@app.route('/api/cobrancas/planilha/ler', methods=['POST'])
def ler_planilha_cobrancas_api():
    try:
        resultado = executar_integracao_planilha(
            get_db(), load_config(), raiz=Path(BASE_PATH),
            usuario=g.usuario['usuario'], data_atual=datetime.now().date(),
        )
        status_http = 200 if resultado.get('status') == 'sucesso' else 422
        return jsonify(resultado), status_http
    except (OSError, sqlite3.Error, ValueError) as exc:
        return jsonify({'status': 'AGUARDANDO_REVISÃO', 'erro': str(exc)}), 422


@app.route('/api/cobrancas/contas/<int:id>')
def detalhe_conta_cobranca(id):
    conn = get_db()
    if not _tabela_existe(conn, 'contas'):
        conn.close(); return jsonify({'erro': 'Estrutura de contas ainda não disponível.'}), 404
    row = conn.execute('SELECT * FROM contas WHERE id=?', (id,)).fetchone()
    conn.close()
    return jsonify(_proteger_telefone(row)) if row else (jsonify({'erro': 'Conta não encontrada.'}), 404)


@app.route('/api/cobrancas/contas/<int:id>/previa', methods=['POST'])
def gerar_previa_conta_cobranca(id):
    payload = request.get_json(silent=True) or {}
    regra_id = payload.get('regra_id')
    destinatario_id = payload.get('destinatario_id')
    conn = get_db()
    if not all(_tabela_existe(conn, tabela) for tabela in ('contas', 'regras_cobranca', 'destinatarios')):
        conn.close()
        return jsonify({'erro': 'Estrutura de cobranças ainda não disponível.'}), 503
    conta = conn.execute('SELECT * FROM contas WHERE id=?', (id,)).fetchone()
    regra = conn.execute('SELECT * FROM regras_cobranca WHERE id=? AND ativa=1', (regra_id,)).fetchone()
    destinatario = conn.execute('SELECT * FROM destinatarios WHERE id=? AND ativo=1', (destinatario_id,)).fetchone()
    if not conta:
        conn.close(); return jsonify({'erro': 'Conta não encontrada.'}), 404
    if not regra:
        conn.close(); return jsonify({'erro': 'Regra ativa não encontrada.'}), 404
    if not destinatario:
        conn.close(); return jsonify({'erro': 'Destinatário ativo não encontrado.'}), 404
    try:
        previa = gerar_previa_cobranca(dict(conta), dict(destinatario), dict(regra), data_atual=datetime.now().date())
        return jsonify(previa)
    except ErroPreviaCobranca as exc:
        return jsonify(exc.as_dict()), 422
    finally:
        conn.close()


def _aprovar_mensagem(conn, mensagem_id, acao, usuario, justificativa):
    tabelas = ('mensagens', 'contas', 'destinatarios')
    if not all(_tabela_existe(conn, tabela) for tabela in tabelas):
        raise ErroAprovacaoMensagem('estrutura_indisponivel', 'Estrutura de mensagens, contas ou destinatários não disponível.')
    colunas = {row[1] for row in conn.execute('PRAGMA table_info(mensagens)').fetchall()}
    necessarias = {'justificativa', 'alterado_por', 'alterada_em'}
    if not necessarias <= colunas:
        raise ErroAprovacaoMensagem('migracao_pendente', 'Campos de auditoria da aprovação ainda não foram migrados.')
    mensagem = conn.execute('SELECT * FROM mensagens WHERE id=?', (mensagem_id,)).fetchone()
    if not mensagem:
        raise ErroAprovacaoMensagem('mensagem_nao_encontrada', 'Mensagem não encontrada.')
    conta = conn.execute('SELECT valor_pendente, status FROM contas WHERE id=?', (mensagem['conta_id'],)).fetchone()
    destinatario = conn.execute('SELECT ativo FROM destinatarios WHERE id=?', (mensagem['destinatario_id'],)).fetchone()
    conta_pendente = bool(conta and conta['valor_pendente'] is not None and float(conta['valor_pendente']) > 0 and str(conta['status']).upper() != 'PAGA')
    resultado = transicionar_mensagem(dict(mensagem), acao, usuario=usuario, justificativa=justificativa, conta_pendente=conta_pendente, destinatario_ativo=bool(destinatario and destinatario['ativo']))
    agora = resultado['data']
    conn.execute('''UPDATE mensagens SET status=?, usuario_aprovou=?, aprovada_em=?, justificativa=?, alterado_por=?, alterada_em=?, erro=? WHERE id=?''',
                 (resultado['status_armazenamento'], usuario if acao == 'aprovar' else None, agora if acao == 'aprovar' else None, resultado['justificativa'] or None, usuario, agora, resultado['justificativa'] or None, mensagem_id))
    if _tabela_existe(conn, 'auditoria_cobranca'):
        conn.execute('''INSERT INTO auditoria_cobranca (tabela_origem, registro_id, acao, usuario, dados_anterior, dados_novo, origem, observacao) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                     ('mensagens', mensagem_id, acao, usuario, json.dumps(dict(mensagem), ensure_ascii=False, default=str), json.dumps(resultado, ensure_ascii=False), 'api', resultado['justificativa']))
    return resultado


@app.route('/api/cobrancas/mensagens/<int:id>/aprovacao', methods=['POST'])
def aprovar_mensagem_cobranca(id):
    payload = request.get_json(silent=True) or {}
    try:
        conn = get_db()
        resultado = _aprovar_mensagem(conn, id, payload.get('acao', ''), g.usuario['usuario'], payload.get('justificativa', ''))
        conn.commit(); conn.close()
        return jsonify(resultado)
    except ErroAprovacaoMensagem as exc:
        if 'conn' in locals(): conn.rollback(); conn.close()
        return jsonify(exc.as_dict()), 409


@app.route('/api/cobrancas/mensagens/aprovacao-lote', methods=['POST'])
def aprovar_lote_mensagens_cobranca():
    payload = request.get_json(silent=True) or {}
    try:
        ids = validar_lote(payload.get('ids', []))
        conn = get_db(); resultados = []
        for mensagem_id in ids:
            resultados.append({'id': mensagem_id, **_aprovar_mensagem(conn, mensagem_id, payload.get('acao', ''), g.usuario['usuario'], payload.get('justificativa', ''))})
        conn.commit(); conn.close()
        return jsonify({'status': 'processado', 'resultados': resultados})
    except ErroAprovacaoMensagem as exc:
        if 'conn' in locals(): conn.rollback(); conn.close()
        return jsonify(exc.as_dict()), 409


@app.route('/api/cobrancas/mensagens/historico')
def historico_mensagens_cobranca():
    conn = get_db()
    if not _tabela_existe(conn, 'mensagens'):
        conn.close(); return jsonify({'mensagens': [], 'estrutura_disponivel': False})
    params = request.args
    where, valores = [], []
    for campo in ('m.status', 'c.arquivo_origem', 'c.orgao'):
        chave = campo.split('.')[1]
        if params.get(chave): where.append(f"LOWER(COALESCE({campo}, '')) LIKE LOWER(?)"); valores.append(f"%{params[chave]}%")
    if params.get('usuario'):
        where.append("LOWER(COALESCE(m.usuario_aprovou, m.alterado_por, '')) LIKE LOWER(?)"); valores.append(f"%{params['usuario']}%")
    if params.get('data_inicio'):
        where.append('COALESCE(m.enviada_em, m.criada_em) >= ?'); valores.append(params['data_inicio'] + 'T00:00:00')
    if params.get('data_fim'):
        where.append('COALESCE(m.enviada_em, m.criada_em) <= ?'); valores.append(params['data_fim'] + 'T23:59:59')
    query = '''SELECT m.id, m.conta_id, m.destinatario_id, m.regra_id, m.competencia, m.tipo_alerta,
        m.texto, m.status, m.provedor, m.identificador_externo, m.tentativa, m.criada_em, m.enviada_em,
        m.resposta_provedor, m.erro, m.usuario_aprovou, m.aprovada_em, m.justificativa,
        c.orgao, c.arquivo_origem, c.identificador AS conta_identificador
        FROM mensagens m LEFT JOIN contas c ON c.id=m.conta_id'''
    if where: query += ' WHERE ' + ' AND '.join(where)
    rows = conn.execute(query + ' ORDER BY COALESCE(m.enviada_em, m.criada_em) DESC, m.id DESC LIMIT 500', valores).fetchall()
    conn.close()
    return jsonify({'mensagens': [dict(row) for row in rows], 'estrutura_disponivel': True})


@app.route('/api/cobrancas/auditoria')
def auditoria_cobranca_api():
    conn = get_db()
    if not _tabela_existe(conn, 'auditoria_cobranca'):
        conn.close(); return jsonify({'eventos': [], 'estrutura_disponivel': False})
    filtros = {chave: request.args.get(chave) for chave in ('usuario', 'arquivo_origem', 'orgao', 'status', 'tipo_evento', 'data_inicio', 'data_fim')}
    eventos = listar_auditoria(conn, filtros)
    conn.close()
    return jsonify({'eventos': eventos, 'estrutura_disponivel': True})


@app.route('/api/logs')
def get_logs():
    conn = get_db()
    params = request.args
    where, values = [], []
    for campo in ('usuario', 'arquivo', 'status', 'tipo_evento'):
        if params.get(campo):
            coluna = 'arquivo' if campo == 'arquivo' else campo
            where.append(f"UPPER(COALESCE({coluna}, '')) LIKE UPPER(?)")
            values.append(f"%{params[campo]}%")
    if params.get('data_inicio'):
        where.append('data_hora >= ?'); values.append(params['data_inicio'] + 'T00:00:00')
    if params.get('data_fim'):
        where.append('data_hora < ?'); values.append(params['data_fim'] + 'T23:59:59')
    query = 'SELECT * FROM auditoria_eventos'
    if where:
        query += ' WHERE ' + ' AND '.join(where)
    rows = conn.execute(query + ' ORDER BY data_hora DESC, id DESC LIMIT 500', values).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


def _parametros_exportacao():
    tipo = request.args.get('tipo', 'faturas')
    formato = request.args.get('formato', 'xlsx').lower()
    if tipo not in TIPOS:
        raise ValueError('Tipo de exportação inválido.')
    if formato not in {'xlsx', 'csv'}:
        raise ValueError('Formato inválido. Use xlsx ou csv.')
    return tipo, formato, request.args.get('competencia'), request.args.get('orgao')


@app.route('/api/export/validar')
def validar_exportacao():
    try:
        tipo, _, competencia, orgao = _parametros_exportacao()
        conn = get_db()
        resultado = resumo_exportacao(conn, tipo, competencia, orgao)
        conn.close()
        return jsonify(resultado)
    except ValueError as exc:
        return jsonify({'erro': str(exc)}), 400


@app.route('/api/export')
def exportar():
    try:
        tipo, formato, competencia, orgao = _parametros_exportacao()
        conn = get_db()
        nome = f'{tipo}_{competencia or "todos"}_{orgao or "todos"}.{formato}'.replace(' ', '_').replace('/', '_')
        arquivo = os.path.join(BASE_PATH, 'Relatorios', nome)
        resultado = gerar_exportacao(conn, tipo, formato, arquivo, competencia, orgao)
        conn.close()
        resposta = send_file(arquivo, as_attachment=True, download_name=nome,
                             mimetype='text/csv; charset=utf-8' if formato == 'csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resposta.headers['X-Total-Exibido'] = resultado['total_exibido']
        resposta.headers['X-Total-Exportado'] = resultado['total_exportado']
        resposta.headers['X-Total-Validado'] = str(resultado['valido']).lower()
        return resposta
    except ValueError as exc:
        return jsonify({'erro': str(exc)}), 400


@app.route('/api/export/<mes>')
def exportar_compatibilidade(mes):
    conn = get_db()
    arquivo = os.path.join(BASE_PATH, 'Relatorios', f'Despesas_{mes.replace("-", "_")}.xlsx')
    gerar_exportacao(conn, 'lancamentos_competencia', 'xlsx', arquivo, mes)
    conn.close()
    return send_file(arquivo, as_attachment=True) if os.path.exists(arquivo) else (jsonify({'erro': 'Arquivo não gerado'}), 404)


@app.route('/api/upload', methods=['POST'])
def upload_faturas():
    if 'files' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    saved, errors = [], []
    input_dir = os.path.join(BASE_PATH, 'Faturas_entrada')
    script_path = os.path.join(BASE_PATH, 'Scripts', 'processar_fatura.py')
    os.makedirs(input_dir, exist_ok=True)
    for uploaded in files:
        filename = uploaded.filename or 'unnamed.pdf'
        if not filename.lower().endswith('.pdf'):
            errors.append({'file': filename, 'status': 'ignored', 'message': 'Formato não suportado'})
            continue
        safe_name = os.path.basename(filename)
        destino = os.path.join(input_dir, safe_name)
        base, ext = os.path.splitext(safe_name)
        contador = 1
        while os.path.exists(destino):
            destino = os.path.join(input_dir, f'{base}_{contador}{ext}')
            contador += 1
        uploaded.save(destino)
        processo = subprocess.run([sys.executable, script_path, BASE_PATH, destino], capture_output=True, text=True)
        item = {'file': filename, 'saved_as': os.path.basename(destino), 'returncode': processo.returncode, 'stdout': processo.stdout.strip(), 'stderr': processo.stderr.strip(), 'status': 'sucesso' if processo.returncode == 0 else 'erro'}
        if item['status'] == 'erro':
            errors.append({'file': filename, 'status': 'erro', 'message': item['stderr'] or 'Erro interno'})
        saved.append(item)
    return jsonify({'processed': saved, 'errors': errors, 'success': sum(item['status'] == 'sucesso' for item in saved), 'failed': len(errors)})


if __name__ == '__main__':
    print('SAMF PRO SERVER ONLINE - Porta 5000')
    app.run(host='0.0.0.0', port=5000, debug=True)