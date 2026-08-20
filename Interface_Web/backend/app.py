import os
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory, g
from flask_cors import CORS
from datetime import datetime

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

app = Flask(__name__, static_folder='static')
CORS(app)
BASE_PATH = r'c:\code\SAMF-HUB-v1.1'
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


@app.before_request
def autenticar_requisicao():
    if not request.path.startswith('/api/') or request.path.startswith('/api/auth/'):
        return None
    conn = get_db()
    g.auth_conn = conn
    g.usuario = usuario_da_requisicao(conn)
    permissao = 'consultar'
    if request.path.startswith('/api/export'):
        permissao = 'exportar'
    elif request.path == '/api/upload':
        permissao = 'processar'
    elif request.path == '/api/config':
        permissao = 'gerenciar_configuracoes'
    elif request.path.startswith('/api/regras-administrativas'):
        permissao = 'gerenciar_regras' if request.method != 'GET' else 'consultar'
    elif request.path.startswith('/api/orgaos'):
        permissao = 'gerenciar_orgaos' if request.method != 'GET' else 'consultar'
    elif request.path.startswith('/api/usuarios'):
        permissao = 'gerenciar_usuarios'
    elif request.path.startswith('/api/faturas/') and request.path.endswith('/corrigir'):
        permissao = 'corrigir_dados'
    elif request.path.startswith('/api/faturas/') and request.path.endswith('/revisao'):
        permissao = 'decidir_revisao'
    if not g.usuario:
        registrar_evento(conn, 'autorização negada', usuario='anônimo', status='negado', observacao=f'{request.method} {request.path} requer autenticação')
        conn.commit()
        conn.close()
        g.auth_conn = None
        return jsonify({'erro': 'Autenticação obrigatória.'}), 401
    if permissao not in PERFIS[g.usuario['perfil']]:
        registrar_evento(conn, 'autorização negada', usuario=g.usuario['usuario'], status='negado', observacao=f'{request.method} {request.path} requer {permissao}')
        conn.commit(); conn.close(); g.auth_conn = None
        return jsonify({'erro': 'Permissão insuficiente.'}), 403
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
    cur.execute(f"SELECT COALESCE(NULLIF(f.servico, ''), s.nome, 'Não identificado') AS nome, COUNT(*) AS quantidade, COALESCE(SUM({valor_expr}), 0) AS valor FROM faturas f LEFT JOIN servicos s ON s.id=f.servico_id GROUP BY nome ORDER BY valor DESC")
    servicos = [dict(row) for row in cur.fetchall()]
    cur.execute(f"SELECT COALESCE(NULLIF(competencia, ''), substr(criado_em, 1, 7), 'Não identificado') AS mes, COUNT(*) AS quantidade, COALESCE(SUM({valor_expr}), 0) AS valor FROM faturas f GROUP BY mes ORDER BY mes")
    meses = [dict(row) for row in cur.fetchall()]
    cur.execute("SELECT UPPER(COALESCE(NULLIF(classificacao, ''), 'SEM_CLASSIFICACAO')) AS classificacao, COUNT(*) AS quantidade, COALESCE(SUM(COALESCE(valor_base, valor_total, 0)), 0) AS valor FROM faturas GROUP BY classificacao ORDER BY quantidade DESC")
    classificacoes_grafico = [dict(row) for row in cur.fetchall()]
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