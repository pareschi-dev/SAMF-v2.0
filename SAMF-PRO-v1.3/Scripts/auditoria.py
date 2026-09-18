import json
from datetime import datetime


def garantir_tabela(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS auditoria_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fatura_id INTEGER,
            arquivo TEXT,
            tipo_evento TEXT NOT NULL,
            status TEXT,
            usuario TEXT NOT NULL DEFAULT 'sistema',
            data_hora TEXT NOT NULL,
            valor_anterior TEXT,
            valor_novo TEXT,
            observacao TEXT,
            criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_auditoria_eventos_data ON auditoria_eventos(data_hora)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_auditoria_eventos_tipo ON auditoria_eventos(tipo_evento)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_auditoria_eventos_usuario ON auditoria_eventos(usuario)')
    conn.execute('''
        CREATE TRIGGER IF NOT EXISTS impedir_exclusao_auditoria
        BEFORE DELETE ON auditoria_eventos
        BEGIN
            SELECT RAISE(ABORT, 'Logs de auditoria não podem ser excluídos');
        END
    ''')


def registrar_evento(conn, tipo_evento, *, fatura_id=None, arquivo=None, status=None,
                     usuario='sistema', valor_anterior=None, valor_novo=None,
                     observacao=None):
    garantir_tabela(conn)
    conn.execute('''
        INSERT INTO auditoria_eventos
        (fatura_id, arquivo, tipo_evento, status, usuario, data_hora,
         valor_anterior, valor_novo, observacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        fatura_id, arquivo, tipo_evento, status, str(usuario or 'sistema'),
        datetime.now().isoformat(timespec='seconds'),
        json.dumps(valor_anterior, ensure_ascii=False, default=str) if valor_anterior is not None else None,
        json.dumps(valor_novo, ensure_ascii=False, default=str) if valor_novo is not None else None,
        observacao,
    ))
