-- SAMF – Schema para SQLite

CREATE TABLE IF NOT EXISTS orgaos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL UNIQUE,
    ordem       INTEGER NOT NULL UNIQUE,
    criado_em   DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO orgaos (nome, ordem) VALUES
    ('SRA', 1), ('SRT', 2), ('AGU (PF)', 3), ('AGU (CJU)', 4), ('AGU (PU)', 5),
    ('SPU', 6), ('CGU', 7), ('SERPRO', 8), ('ABIN', 9), ('DRF', 10),
    ('PFN', 11), ('FUNDACENTRO', 12), ('ASSEFAZ', 13), ('IBGE', 14), ('SIG', 15);

CREATE TABLE IF NOT EXISTS padroes_rateio (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    orgao_id    INTEGER NOT NULL REFERENCES orgaos(id),
    percentual  REAL NOT NULL,
    criado_em   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (nome, orgao_id)
);

CREATE TABLE IF NOT EXISTS servicos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT NOT NULL UNIQUE,
    fornecedor      TEXT NOT NULL,
    padrao          TEXT NOT NULL,
    regex_valor     TEXT NOT NULL DEFAULT 'Total\D*(\d{1,3}(?:\.\d{3})*,\d{2})',
    regex_vencimento TEXT NOT NULL DEFAULT 'Vencimento:\s*(\d{2}/\d{2}/\d{4})',
    palavras_chave  TEXT NOT NULL,
    criado_em       DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS faturas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_arquivo    TEXT UNIQUE NOT NULL,
    caminho_arquivo TEXT NOT NULL,
    nome_arquivo    TEXT NOT NULL,
    servico_id      INTEGER REFERENCES servicos(id),
    fornecedor_extraido TEXT,
    valor_total     REAL,
    data_vencimento TEXT,
    confianca       REAL,
    status          TEXT NOT NULL,
    criado_em       DATETIME DEFAULT CURRENT_TIMESTAMP,
    atualizado_em   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rateios_calculados (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fatura_id       INTEGER NOT NULL REFERENCES faturas(id) ON DELETE CASCADE,
    orgao_id        INTEGER NOT NULL REFERENCES orgaos(id),
    percentual      REAL NOT NULL,
    valor_rateio    REAL NOT NULL,
    criado_em       DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (fatura_id, orgao_id)
);

CREATE TABLE IF NOT EXISTS logs_processamento (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fatura_id       INTEGER REFERENCES faturas(id) ON DELETE SET NULL,
    status          TEXT NOT NULL,
    mensagem        TEXT,
    hash_arquivo    TEXT,
    criado_em       DATETIME DEFAULT CURRENT_TIMESTAMP
);

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
);

CREATE TRIGGER IF NOT EXISTS impedir_exclusao_auditoria
BEFORE DELETE ON auditoria_eventos
BEGIN
    SELECT RAISE(ABORT, 'Logs de auditoria não podem ser excluídos');
END;

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL CHECK(perfil IN ('visualizador', 'operador', 'aprovador', 'administrador')),
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessoes_usuario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_em TEXT NOT NULL,
    encerrada_em TEXT
);
