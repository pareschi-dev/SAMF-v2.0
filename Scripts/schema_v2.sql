-- SAMF v2.0 - Schema Expandido com Classificação e Auditoria
-- Compatível com SQLite3

-- ============================================
-- TABELAS PRINCIPAIS
-- ============================================

-- Órgãos e beneficiários
CREATE TABLE IF NOT EXISTS orgaos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    sigla TEXT UNIQUE,
    tipo TEXT CHECK(tipo IN ('orgao', 'unidade', 'endereco')),
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Fornecedores cadastrados
CREATE TABLE IF NOT EXISTS fornecedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    nome_normalizado TEXT,
    categoria_padrao TEXT CHECK(categoria_padrao IN ('compartilhado', 'exclusivo', 'indeterminado')),
    ativo INTEGER DEFAULT 1,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Serviços / Tipos de despesa
CREATE TABLE IF NOT EXISTS servicos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    categoria TEXT CHECK(categoria IN ('compartilhado', 'exclusivo', 'indeterminado')),
    descricao TEXT,
    fornecedor_id INTEGER REFERENCES fornecedores(id),
    ativo INTEGER DEFAULT 1,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Regras de Rateio (matriz de distribuição)
CREATE TABLE IF NOT EXISTS regras_rateio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    servico_id INTEGER NOT NULL REFERENCES servicos(id),
    fornecedor_id INTEGER NOT NULL REFERENCES fornecedores(id),
    tipo_rateio TEXT NOT NULL CHECK(tipo_rateio IN ('compartilhado', 'exclusivo')),
    complemento TEXT,
    orgao_id INTEGER REFERENCES orgaos(id),
    percentual REAL,
    valor_fixo REAL,
    criterio TEXT,
    prioridade INTEGER DEFAULT 100,
    ativo INTEGER DEFAULT 1,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(servico_id, fornecedor_id, tipo_rateio, complemento, orgao_id)
);

-- Faturas processadas
CREATE TABLE IF NOT EXISTS faturas_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_arquivo TEXT UNIQUE NOT NULL,
    nome_arquivo TEXT NOT NULL,
    caminho_arquivo TEXT NOT NULL,
    
    -- Dados extraídos
    fornecedor_id INTEGER REFERENCES fornecedores(id),
    fornecedor_nome_original TEXT,
    servico_id INTEGER REFERENCES servicos(id),
    numero_fatura TEXT,
    descricao TEXT,
    
    -- Valores
    valor_total REAL NOT NULL,
    valor_processado REAL,
    
    -- Datas e competências
    data_fatura DATE,
    data_vencimento DATE,
    competencia TEXT,
    periodo_referencia TEXT,
    
    -- Localização e endereço
    endereco TEXT,
    unidade TEXT,
    complemento_fatura TEXT,
    
    -- Órgão beneficiário (para exclusivas)
    orgao_beneficiario_id INTEGER REFERENCES orgaos(id),
    
    -- Classificação
    classificacao TEXT CHECK(classificacao IN ('compartilhado', 'exclusivo', 'revisao', 'erro', 'duplicado')),
    confianca_classificacao REAL,
    motivo_revisao TEXT,
    
    -- Status
    status TEXT CHECK(status IN ('pendente', 'processado', 'lançado', 'revisao', 'rejeitado', 'duplicado')),
    status_validacao TEXT,
    divergencia_detectada INTEGER DEFAULT 0,
    
    -- Auditoria
    processado_em DATETIME,
    revisado_por TEXT,
    revisado_em DATETIME,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Lançamentos de rateio (detalhe do que foi processado)
CREATE TABLE IF NOT EXISTS lancamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fatura_id INTEGER NOT NULL REFERENCES faturas_v2(id) ON DELETE CASCADE,
    orgao_id INTEGER NOT NULL REFERENCES orgaos(id),
    valor_lançado REAL NOT NULL,
    percentual_aplicado REAL,
    criterio_aplicado TEXT,
    regra_rateio_id INTEGER REFERENCES regras_rateio(id),
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Auditoria completa
CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fatura_id INTEGER REFERENCES faturas_v2(id) ON DELETE SET NULL,
    tipo_acao TEXT NOT NULL CHECK(tipo_acao IN ('leitura', 'classificacao', 'calculo', 'lancamento', 'validacao', 'revisao', 'alteracao', 'rejeicao')),
    usuario TEXT,
    dados_anterior TEXT,
    dados_novo TEXT,
    justificativa TEXT,
    resultado TEXT,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Validações e divergências
CREATE TABLE IF NOT EXISTS divergencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fatura_id INTEGER NOT NULL REFERENCES faturas_v2(id) ON DELETE CASCADE,
    tipo_divergencia TEXT NOT NULL CHECK(tipo_divergencia IN ('soma_inconsistente', 'valor_zerado', 'fornecedor_ambiguo', 'servico_ambiguo', 'orgao_nao_identificado', 'duplicada', 'pdf_ilegivel', 'complemento_insuficiente')),
    descricao TEXT,
    valor_esperado REAL,
    valor_obtido REAL,
    resolvido INTEGER DEFAULT 0,
    resolvido_em DATETIME,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Logs de processamento
CREATE TABLE IF NOT EXISTS logs_processamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fatura_id INTEGER REFERENCES faturas_v2(id) ON DELETE SET NULL,
    nivel TEXT CHECK(nivel IN ('debug', 'info', 'warning', 'error')),
    mensagem TEXT,
    contexto TEXT,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
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

-- ============================================
-- ÍNDICES PARA PERFORMANCE
-- ============================================

CREATE INDEX IF NOT EXISTS idx_faturas_v2_status ON faturas_v2(status);
CREATE INDEX IF NOT EXISTS idx_faturas_v2_classificacao ON faturas_v2(classificacao);
CREATE INDEX IF NOT EXISTS idx_faturas_v2_competencia ON faturas_v2(competencia);
CREATE INDEX IF NOT EXISTS idx_faturas_v2_fornecedor ON faturas_v2(fornecedor_id);
CREATE INDEX IF NOT EXISTS idx_faturas_v2_servico ON faturas_v2(servico_id);
CREATE INDEX IF NOT EXISTS idx_lancamentos_fatura ON lancamentos(fatura_id);
CREATE INDEX IF NOT EXISTS idx_lancamentos_orgao ON lancamentos(orgao_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_fatura ON auditoria(fatura_id);
CREATE INDEX IF NOT EXISTS idx_divergencias_fatura ON divergencias(fatura_id);

-- ============================================
-- DADOS INICIAIS (CONFIGURAÇÃO OFICIAL)
-- ============================================

-- Órgãos
INSERT OR IGNORE INTO orgaos (nome, sigla, tipo) VALUES
('SRA', 'SRA', 'orgao'),
('DRF', 'DRF', 'orgao'),
('PFN', 'PFN', 'orgao'),
('PSFN', 'PSFN', 'orgao'),
('SPU', 'SPU', 'orgao'),
('CGU', 'CGU', 'orgao'),
('BB', 'BB', 'orgao'),
('SERPRO', 'SERPRO', 'orgao'),
('ABIN', 'ABIN', 'orgao'),
('Alfândega', 'ALF', 'orgao'),
('SRT', 'SRT', 'orgao'),
('AGU (PF)', 'AGU-PF', 'orgao'),
('AGU (CJU)', 'AGU-CJU', 'orgao'),
('AGU (PU)', 'AGU-PU', 'orgao'),
('FUNDACENTRO', 'FUNDACENTRO', 'orgao'),
('ASSEFAZ', 'ASSEFAZ', 'orgao'),
('IBGE', 'IBGE', 'orgao');

-- Fornecedores - COMPARTILHADOS
INSERT OR IGNORE INTO fornecedores (nome, categoria_padrao) VALUES
('CESAN', 'indeterminado'),
('P.M.V.', 'indeterminado'),
('ACX - STAR GREEN', 'compartilhado'),
('AJP', 'indeterminado'),
('EDP', 'indeterminado'),
('PGE', 'compartilhado'),
('PREVIEW', 'compartilhado'),
('ELEVADORES MILÊNIO', 'compartilhado'),
('ANATOVI', 'compartilhado'),
('SUDESTE', 'indeterminado'),
('ROTACIONAL - DND', 'compartilhado'),
('VIVO', 'indeterminado'),
('JCA', 'indeterminado'),
('MÁXIMA', 'indeterminado'),
('SEI', 'indeterminado'),
('BRK', 'exclusivo'),
('SAAE', 'exclusivo'),
('LINK CARD', 'exclusivo'),
('ECT', 'exclusivo'),
('RESULT', 'exclusivo'),
('SAFIRA ENGENHARIA', 'exclusivo'),
('ALLGED', 'exclusivo'),
('XP3 - HALF', 'exclusivo'),
('EBC', 'exclusivo'),
('AGUIAR & MANTOVANI', 'exclusivo'),
('LUZ E FORÇA SANTA MARIA', 'exclusivo');

-- Serviços
INSERT OR IGNORE INTO servicos (nome, categoria) VALUES
('Água e esgoto', 'indeterminado'),
('Aluguéis + taxas (IPTU)', 'indeterminado'),
('Combustível de gerador', 'compartilhado'),
('Dedetização', 'indeterminado'),
('Energia elétrica', 'indeterminado'),
('Manutenção de ar-condicionado central', 'compartilhado'),
('Manutenção central de alarme', 'compartilhado'),
('Manutenção de elevadores', 'compartilhado'),
('Manutenção de jardins', 'compartilhado'),
('Manutenção predial', 'compartilhado'),
('Manutenção de telefonia', 'compartilhado'),
('Manutenção de vídeo-monitoramento', 'compartilhado'),
('Serviço de limpeza', 'compartilhado'),
('Telefonia fixa', 'indeterminado'),
('Telefonia móvel', 'indeterminado'),
('Telefonista', 'indeterminado'),
('Vigilância/segurança', 'indeterminado'),
('Limpeza e higienização', 'exclusivo'),
('Locação de imóveis', 'exclusivo'),
('Manutenção de veículos', 'exclusivo'),
('Material de consumo', 'exclusivo'),
('Motorista', 'exclusivo'),
('Auxiliar administrativo', 'exclusivo'),
('Auxiliar de informática', 'exclusivo'),
('Copeiragem', 'exclusivo'),
('Publicidade legal', 'exclusivo'),
('Avaliação de imóveis', 'exclusivo'),
('Avaliação de insalubridade', 'exclusivo'),
('Locação de equipamentos', 'exclusivo'),
('Vigilância eletrônica', 'exclusivo'),
('Correios', 'exclusivo');

