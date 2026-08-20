import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps

from werkzeug.security import check_password_hash, generate_password_hash
from flask import jsonify, request, g

from auditoria import garantir_tabela, registrar_evento

PERFIS = {
    'visualizador': {'consultar', 'exportar', 'visualizar_cobrancas', 'consultar_historico_cobranca'},
    'operador': {'consultar', 'exportar', 'processar', 'corrigir_dados', 'visualizar_cobrancas', 'gerar_previas_cobranca', 'consultar_historico_cobranca'},
    'aprovador': {'consultar', 'exportar', 'decidir_revisao', 'visualizar_cobrancas', 'gerar_previas_cobranca', 'aprovar_mensagens_cobranca', 'consultar_historico_cobranca'},
    'administrador': {'consultar', 'exportar', 'processar', 'corrigir_dados', 'decidir_revisao', 'visualizar_cobrancas', 'visualizar_telefone_destinatario', 'editar_regras_cobranca', 'cadastrar_destinatarios_cobranca', 'gerar_previas_cobranca', 'aprovar_mensagens_cobranca', 'enviar_mensagens_cobranca', 'consultar_historico_cobranca', 'alterar_integracao_cobranca', 'gerenciar_regras', 'gerenciar_orgaos', 'gerenciar_caminhos', 'gerenciar_usuarios', 'gerenciar_configuracoes'},
}
PERFIS_ALIASES = {'visualizador': 'visualizador', 'operador': 'operador', 'aprovador': 'aprovador', 'administrador': 'administrador', 'admin': 'administrador'}


def garantir_tabelas(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            senha_hash TEXT NOT NULL,
            perfil TEXT NOT NULL CHECK(perfil IN ('visualizador', 'operador', 'aprovador', 'administrador')),
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sessoes_usuario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expira_em TEXT NOT NULL,
            encerrada_em TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_sessoes_token ON sessoes_usuario(token_hash)')


def _perfil(perfil):
    perfil = PERFIS_ALIASES.get(str(perfil or '').strip().lower())
    if not perfil:
        raise ValueError('Perfil inválido.')
    return perfil


def quantidade_usuarios(conn):
    garantir_tabelas(conn)
    return conn.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0]


def criar_usuario(conn, usuario, nome, senha, perfil):
    perfil = _perfil(perfil)
    usuario = str(usuario or '').strip().lower()
    nome = str(nome or '').strip()
    if len(usuario) < 3 or len(senha or '') < 8 or not nome:
        raise ValueError('Usuário, nome e senha (mínimo de 8 caracteres) são obrigatórios.')
    garantir_tabelas(conn)
    cur = conn.execute('INSERT INTO usuarios (usuario, nome, senha_hash, perfil) VALUES (?, ?, ?, ?)', (usuario, nome, generate_password_hash(senha), perfil))
    return cur.lastrowid, perfil


def autenticar(conn, usuario, senha):
    garantir_tabelas(conn)
    row = conn.execute('SELECT * FROM usuarios WHERE usuario=? AND ativo=1', (str(usuario or '').strip().lower(),)).fetchone()
    if not row or not check_password_hash(row['senha_hash'], senha or ''):
        return None
    token = secrets.token_urlsafe(32)
    expira = datetime.utcnow() + timedelta(hours=8)
    conn.execute('INSERT INTO sessoes_usuario (usuario_id, token_hash, expira_em) VALUES (?, ?, ?)', (row['id'], hashlib.sha256(token.encode()).hexdigest(), expira.isoformat(timespec='seconds')))
    return token, dict(row)


def usuario_da_requisicao(conn):
    garantir_tabelas(conn)
    cabecalho = request.headers.get('Authorization', '')
    if not cabecalho.startswith('Bearer '):
        return None
    token_hash = hashlib.sha256(cabecalho[7:].strip().encode()).hexdigest()
    row = conn.execute('''
        SELECT u.id, u.usuario, u.nome, u.perfil, s.id AS sessao_id
        FROM sessoes_usuario s JOIN usuarios u ON u.id=s.usuario_id
        WHERE s.token_hash=? AND s.encerrada_em IS NULL AND s.expira_em > ? AND u.ativo=1
    ''', (token_hash, datetime.utcnow().isoformat(timespec='seconds'))).fetchone()
    return dict(row) if row else None


def exigir(permissao):
    def decorador(funcao):
        @wraps(funcao)
        def wrapper(*args, **kwargs):
            conn = g.get('auth_conn')
            usuario = g.get('usuario')
            if not usuario or permissao not in PERFIS[usuario['perfil']]:
                if conn:
                    registrar_evento(conn, 'autorização negada', usuario=(usuario or {}).get('usuario', 'anônimo'), status='negado', observacao=f'{request.method} {request.path} requer {permissao}')
                    conn.commit()
                return jsonify({'erro': 'Permissão insuficiente.'}), 403 if usuario else 401
            return funcao(*args, **kwargs)
        return wrapper
    return decorador
