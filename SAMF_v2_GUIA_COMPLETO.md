# SAMF v2.0 - Sistema Profissional de Processamento de Faturas

## 📋 Resumo Executivo

O SAMF v2.0 é uma solução corporativa integrada para processar faturas em PDF, classificar despesas como **rateio compartilhado** ou **despesa exclusiva**, calcular distribuições entre órgãos federais, gerar relatórios e manter auditoria completa.

**Versão**: 2.0  
**Status**: Pronto para Implementação  
**Data**: Agosto 2026  

---

## 🎯 Objetivos Alcançados

✅ **Classificação Profissional**: Roteamento automático baseado em regras oficiais  
✅ **Auditoria Completa**: Registro de cada decisão e alteração  
✅ **Validações Robustas**: Detecção de divergências e inconsistências  
✅ **Interface Intuitiva**: Dashboard com múltiplas visualizações  
✅ **Escalabilidade**: Arquitetura modular preparada para crescimento  
✅ **Conformidade**: Sem apagar dados, sem sobrescrever sem confirmação  

---

## 📁 Arquivos Criados

### Backend (Python)

| Arquivo | Descrição |
|---------|-----------|
| `schema_v2.sql` | Schema SQLite com tabelas de classificação, auditoria e rateios |
| `classifier.py` | Motor inteligente de classificação de despesas |
| `app_v2.py` | API REST Flask com 15+ endpoints profissionais |

### Frontend (HTML/JavaScript)

| Arquivo | Descrição |
|---------|-----------|
| `index_v2.html` | Interface moderna responsiva com Tailwind CSS |
| `app_v2.js` | Lógica Vue.js para interação com API |

---

## 🚀 Como Implementar

### Fase 1: Preparação do Banco de Dados

```bash
# 1. Criar novo banco com schema v2
cd c:\code\SAMF-HUB-v1.1\Scripts
sqlite3 samf_v2.db < schema_v2.sql

# 2. Ou migrar existente
# Backup do samf.db atual
copy samf.db samf_backup.db

# 3. Executar schema_v2.sql (adiciona novas tabelas)
sqlite3 samf.db < schema_v2.sql
```

### Fase 2: Instalar Dependências

```bash
pip install -r requirements.txt
```

Verificar que `classifier.py` está em `Scripts/`.

### Fase 3: Iniciar Sistema v2

```bash
# Terminal 1: API Backend
cd c:\code\SAMF-HUB-v1.1\Interface_Web\backend
python app_v2.py

# Terminal 2: Watchdog (opcional - processa PDFs automaticamente)
cd c:\code\SAMF-HUB-v1.1\Scripts
python robo_vigia.py
```

### Fase 4: Acessar Interface

```
http://localhost:5000/static/index_v2.html
```

---

## 📊 Conceitos Principais

### Classificação de Despesas

**RATEIO COMPARTILHADO**
- Despesa dividida entre múltiplos órgãos
- Exemplo: Energia elétrica do edifício-sede
- Aplicar percentuais/critérios definidos na planilha

**DESPESA EXCLUSIVA**
- Despesa destinada a um único órgão/unidade
- Exemplo: Energia elétrica da Princesa Isabel
- Lançar 100% para o órgão beneficiário

**AGUARDANDO REVISÃO**
- Fornecedor ambíguo (aparece em ambas categorias)
- Complemento insuficiente para decisão automática
- Requer intervenção humana

### Fluxo de Processamento

```
PDF Entrada
    ↓
Extração de Dados
    ↓
Classificação Automática (classifier.py)
    ↓
[Confiança alta?]
├─ SIM → Cálculo → Lançamento → Auditoria
└─ NÃO → Fila de Revisão → Análise Manual
```

---

## 🔧 API Endpoints (v2)

### Dashboard
```
GET /api/v2/dashboard
```
Retorna KPIs, gráficos e estatísticas gerais.

### Faturas
```
GET /api/v2/faturas?status=...&classificacao=...&pagina=1
GET /api/v2/faturas/<id>
POST /api/v2/faturas/<id>/classificar
```

### Revisão
```
GET /api/v2/faturas-revisao
```
Lista apenas faturas aguardando classificação manual.

### Rateios e Validação
```
GET /api/v2/rateios
GET /api/v2/validacao
```

### Health Check
```
GET /api/v2/health
```

---

## 📋 Tabelas do Schema v2

### `faturas_v2`
Armazena dados extraídos e classificação.

Campos principais:
- `classificacao` (compartilhado | exclusivo | revisao | erro | duplicado)
- `confianca_classificacao` (0.0 a 1.0)
- `status` (pendente | processado | lançado | revisao | rejeitado)

### `lancamentos`
Detalhe do que foi lançado para cada órgão.

```
Fatura 1: R$ 1000.00 (Compartilhado)
├─ SRA: R$ 154.50 (15.45%)
├─ DRF: R$ 100.00 (10%)
└─ CGU: R$ 745.50 (74.55%)
```

### `auditoria`
Registro de todas as ações.

```
Ação: leitura | classificacao | calculo | lancamento | validacao | alteracao
```

### `divergencias`
Problemas encontrados durante processamento.

Tipos:
- `soma_inconsistente` (valores não batem)
- `fornecedor_ambiguo` (não conseguiu identificar)
- `pdf_ilegivel` (texto não extraído)
- `complemento_insuficiente` (falta informação)

---

## 🎨 Interface: Abas Principais

### 📊 Dashboard
- KPIs com indicadores de desempenho
- Top serviços processados
- Distribuição por órgão
- Taxa de sucesso

### 📋 Faturas Processadas
- Tabela filtrada e paginada
- Busca por nome, fornecedor, competência
- Status visual (lançado, processado, etc)
- Acesso a detalhes completos

### ⚠️ Aguardando Revisão
- Fila de priorização (confiança baixa primeiro)
- Motivo da revisão claramente indicado
- Botões para classificar como compartilhado/exclusivo
- Campo obrigatório para justificativa

### 📊 Matriz de Rateios
- Visualização de distribuições realizadas
- Agrupado por serviço e fornecedor
- Total por órgão

### ✓ Validação
- Soma de valores (original vs lançado)
- Divergências abertas
- Status de consistência

---

## ✅ Casos de Teste Recomendados

### Teste 1: Rateio Compartilhado Simples
```
Fatura: CESAN - Água e Esgoto - Edifício-Sede
Valor: R$ 1000.00
Esperado: Distribuição entre órgãos conforme percentuais
```

### Teste 2: Despesa Exclusiva Clara
```
Fatura: EDP - Energia - Princesa Isabel
Valor: R$ 500.00
Esperado: 100% para órgão beneficiário identificado
```

### Teste 3: Fornecedor Ambíguo
```
Fatura: CESAN - Água e Esgoto - (sem complemento)
Valor: R$ 750.00
Esperado: Enviar para revisão (confiança baixa)
```

### Teste 4: Duplicação
```
Duas faturas: Mesmo fornecedor + número + competência + valor
Esperado: Detectar e marcar como duplicado
```

### Teste 5: PDF Ilegível
```
Fatura: Documento escaneado sem OCR
Esperado: Detectar erro de leitura, ir para revisão
```

---

## 🔐 Regras de Segurança

✅ Nunca apagar PDF original  
✅ Nunca sobrescrever lançamentos sem confirmação  
✅ Nunca duplicar fatura processada  
✅ Sempre registrar quem fez cada ação (auditoria)  
✅ Validar soma de valores após cálculo  
✅ Rejeitar se confiança < 60% (limiar configurável)  

---

## 📈 Próximas Melhorias (Roadmap)

| Prioridade | Funcionalidade | Status |
|-----------|-----------------|--------|
| P0 | Integração com OCR para PDFs escaneados | ⏳ |
| P0 | Exportação para Excel/CSV | ⏳ |
| P1 | Dashboard em tempo real | ⏳ |
| P1 | Integração com SIAFI | ⏳ |
| P2 | Machine Learning para classificação | ⏳ |
| P2 | Notificações por email | ⏳ |

---

## 🆘 Troubleshooting

### Erro: "no such table: faturas_v2"
**Solução**: Executar `schema_v2.sql` no banco SQLite

### Erro: "classifier module not found"
**Solução**: Certificar que `classifier.py` está em `Scripts/` e caminho está correto em `app_v2.py`

### Interface não carrega
**Solução**: Verificar se `index_v2.html` está em `/static/` e que API está respondendo

### API retorna 500
**Solução**: Verificar logs em terminal onde `app_v2.py` está rodando

---

## 📞 Suporte e Documentação

Para dúvidas sobre:
- **Lógica de classificação**: Ver `classifier.py` linhas 1-100
- **API**: Ver comentários em `app_v2.py`
- **Interface**: Ver CSS em `index_v2.html`
- **Schema**: Ver `schema_v2.sql`

---

**Sistema desenvolvido para**: Ministério da Gestão e da Inovação dos Serviços Públicos (MGI)  
**Compatibilidade**: Windows 7+, Python 3.7+, SQLite3, navegadores modernos  
**Licença**: Uso interno - MGI

