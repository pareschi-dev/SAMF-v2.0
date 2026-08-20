# SAMF v2.0 - Plano de Testes Completo

## ✅ Checklist de Implementação

### Fase 1: Preparação
- [ ] Criar backup do banco samf.db existente
- [ ] Executar schema_v2.sql
- [ ] Copiar classifier.py para Scripts/
- [ ] Copiar app_v2.py para Interface_Web/backend/
- [ ] Copiar index_v2.html e app_v2.js para static/
- [ ] Atualizar requirements.txt se necessário

### Fase 2: Testes Unitários

#### Test 2.1: Import do Módulo Classifier
```python
# Scripts/test_classifier.py
from classifier import ClassificadorFaturas, FaturaExtraida

clf = ClassificadorFaturas()
print("✓ Classifier importado com sucesso")
```

**Resultado Esperado**: Sem erros de import

---

#### Test 2.2: Classificação Compartilhado Simples
```python
fatura = FaturaExtraida(
    nome_arquivo="CESAN - FEV - ED.SEDE.pdf",
    fornecedor="CESAN",
    servico="Água e Esgoto",
    complemento="Edifício-Sede",
    valor=1000.00
)

resultado = clf.classificar(fatura)
print(f"Classificação: {resultado.classificacao}")
print(f"Confiança: {resultado.confianca}")

assert resultado.classificacao == 'compartilhado'
assert resultado.confianca > 0.90
print("✓ Teste 2.2: PASSOU")
```

**Resultado Esperado**: 
```
Classificação: compartilhado
Confiança: 0.95
✓ Teste 2.2: PASSOU
```

---

#### Test 2.3: Classificação Exclusivo
```python
fatura = FaturaExtraida(
    nome_arquivo="EDP - PRINCESA ISABEL.pdf",
    fornecedor="EDP",
    servico="Energia Elétrica",
    complemento="Princesa Isabel",
    valor=500.00
)

resultado = clf.classificar(fatura)
assert resultado.classificacao == 'exclusivo'
assert resultado.confianca > 0.90
print("✓ Teste 2.3: PASSOU")
```

**Resultado Esperado**: Classificação exclusivo com confiança >0.90

---

#### Test 2.4: Classificação Ambígua (Revisão)
```python
fatura = FaturaExtraida(
    nome_arquivo="AJP - FATURA.pdf",
    fornecedor="AJP",
    servico="Dedetização",
    complemento="",  # VAZIO - ambíguo
    valor=2500.00
)

resultado = clf.classificar(fatura)
assert resultado.classificacao == 'revisao'
assert resultado.confianca < 0.60
assert resultado.requer_intervencao == True
print("✓ Teste 2.4: PASSOU")
```

**Resultado Esperado**: Marcado como revisão, requer intervenção humana

---

### Fase 3: Testes de API

#### Test 3.1: Health Check
```bash
curl http://localhost:5000/api/v2/health

# Resposta esperada:
# {"status": "OK", "timestamp": "2026-08-18T14:30:00"}
```

---

#### Test 3.2: Dashboard (Vazio)
```bash
curl http://localhost:5000/api/v2/dashboard

# Resposta esperada:
# {
#   "resumo": {
#     "total_faturas": 0,
#     "valor_total_processado": 0,
#     "taxa_sucesso": 0,
#     "divergencias_abertas": 0,
#     "em_revisao": 0
#   },
#   "por_classificacao": {},
#   "por_status": {},
#   "top_servicos": [],
#   "distribuicao_orgaos": []
# }
```

---

### Fase 4: Testes de Interface

#### Test 4.1: Carregar HTML
```bash
Abrir em navegador: http://localhost:5000/static/index_v2.html
Esperado: Página carrega com abas visíveis
```

#### Test 4.2: Navegação entre Abas
```
✓ Dashboard carrega (vazio inicialmente)
✓ Faturas carrega (tabela vazia)
✓ Revisão carrega (mensagem: nenhuma fatura)
✓ Rateios carrega (sem dados)
✓ Validação carrega (sem divergências)
```

#### Test 4.3: Responsividade
```
✓ Em 1920x1080: Layout completo
✓ Em 1366x768: Layout ajustado
✓ Em 768x1024 (tablet): Layout mobile funcional
✓ Em 375x667 (mobile): Usável (testes limitados)
```

---

### Fase 5: Testes de Cenários Reais

#### Test 5.1: Processar Fatura Compartilhada

**Setup:**
1. Colocar arquivo PDF real `CESAN-02-FEVEREIRO-ED.SEDE.pdf` em Faturas_entrada
2. Rodar robo_vigia.py

**Verificação no Dashboard:**
```
✓ Total de faturas: 1
✓ Valor total processado: R$ XXX.XX
✓ Taxa de sucesso: 100%
✓ Classificação: Compartilhado (1)
```

**Verificação no Banco:**
```sql
SELECT * FROM faturas_v2 WHERE nome_arquivo LIKE 'CESAN%';
-- Deve retornar: classificacao='compartilhado', status='lançado'

SELECT COUNT(*) FROM lancamentos WHERE fatura_id=1;
-- Deve retornar: 14 (ou número de órgãos compartilhados)
```

---

#### Test 5.2: Processar Fatura Exclusiva

**Setup:**
1. Colocar `EDP-PRINCESA-ISABEL.pdf` em Faturas_entrada
2. Rodar robo_vigia.py

**Verificação:**
```sql
SELECT * FROM lancamentos WHERE fatura_id=2;
-- Deve retornar: 1 linha com valor=100% para 1 órgão
-- Demais órgãos: 0
```

---

#### Test 5.3: Processar Fatura Ambígua

**Setup:**
1. Colocar `AJP-DEDETIZACAO.pdf` (sem complemento claro) em Faturas_entrada

**Verificação:**
```sql
SELECT * FROM faturas_v2 WHERE nome_arquivo LIKE 'AJP%';
-- Deve retornar: classificacao='revisao', confianca<0.6

SELECT * FROM divergencias WHERE fatura_id=X;
-- Pode ter: tipo_divergencia='complemento_insuficiente'
```

**Interface:**
```
✓ Abrir aba "Aguardando Revisão"
✓ Ver fatura em amarelo com motivo
✓ Clicar "Compartilhado" ou "Exclusivo"
✓ Escrever justificativa
✓ Enviar
✓ Fatura sai da fila
```

---

#### Test 5.4: Detectar Duplicação

**Setup:**
1. Colocar `CESAN-02-FEV-ED.SEDE.pdf` em Faturas_entrada
2. Copiar mesmo arquivo, renomear para `CESAN - FEVEREIRO - CENTRAL.pdf`
3. Colocar ambos em Faturas_entrada
4. Rodar robo_vigia.py

**Verificação:**
```sql
SELECT COUNT(*) FROM faturas_v2 WHERE classificacao='duplicado';
-- Deve retornar: 1 (segunda cópia marcada como duplicado)

SELECT * FROM divergencias WHERE tipo_divergencia LIKE 'duplicada';
-- Deve ter registro da detecção
```

---

#### Test 5.5: Detectar PDF Ilegível

**Setup:**
1. Criar arquivo PDF com apenas imagem (sem OCR)
2. Colocar em Faturas_entrada

**Verificação:**
```sql
SELECT * FROM faturas_v2 WHERE nome_arquivo LIKE 'imagem%';
-- Deve retornar: classificacao='revisao', motivo='sem_texto'

SELECT * FROM logs_processamento WHERE nivel='warning';
-- Deve ter: "PDF sem texto extraível"
```

---

### Fase 6: Testes de Validação e Auditoria

#### Test 6.1: Validação de Soma

**Inserir fatura artificial (SQL):**
```sql
INSERT INTO faturas_v2 (nome_arquivo, valor_total, classificacao, status)
VALUES ('TEST.pdf', 1000.00, 'compartilhado', 'processado');

-- Inserir lançamentos que NÃO somam 1000:
INSERT INTO lancamentos (fatura_id, orgao_id, valor_lançado)
VALUES (1, 1, 500.00), (1, 2, 400.00);  -- Total: 900.00 (falta 100)
```

**Verificação:**
```bash
curl http://localhost:5000/api/v2/validacao

# Deve retornar divergência:
# {
#   "divergencias": {
#     "soma_inconsistente": 1
#   },
#   "validacao_valores": {
#     "consistente": false,
#     "diferenca": 100.00
#   }
# }
```

**Interface:**
```
✓ Dashboard: Divergências abertas: 1
✓ Aba Validação: Mostrar diferença
✓ Usuário deve corrigir manualmente
```

---

#### Test 6.2: Auditoria Completa

**Simular classificação manual:**
```bash
curl -X POST http://localhost:5000/api/v2/faturas/3/classificar \
  -H "Content-Type: application/json" \
  -d '{"classificacao":"compartilhado","justificativa":"Aprovado por análise manual","usuario":"admin"}'
```

**Verificar auditoria:**
```sql
SELECT * FROM auditoria WHERE fatura_id=3 ORDER BY criado_em DESC;

-- Deve conter:
-- - Ação: revisao
-- - Usuario: admin
-- - Justificativa: "Aprovado por análise manual"
-- - Resultado: "Aprovado em revisão manual"
```

**Interface:**
```
✓ Abrir detalhes da fatura
✓ Ver seção "Histórico de Auditoria"
✓ Listar: "Revisão por admin - Compartilhado - Aprovado"
```

---

### Fase 7: Testes de Performance

#### Test 7.1: 100 Faturas
```bash
# Inserir 100 faturas no banco (via script)
python -c "
import sqlite3
conn = sqlite3.connect('samf.db')
cur = conn.cursor()
for i in range(100):
    cur.execute('''INSERT INTO faturas_v2 
    (nome_arquivo, valor_total, classificacao, status)
    VALUES (?, ?, ?, ?)''', (f'fatura_{i}.pdf', 1000+i, 'compartilhado', 'lançado'))
conn.commit()
"

# Dashboard deve carregar em <2s
time curl http://localhost:5000/api/v2/dashboard
# Esperado: <2000ms
```

#### Test 7.2: Paginação
```bash
curl "http://localhost:5000/api/v2/faturas?pagina=1&por_pagina=50"
# Deve retornar: 50 faturas + info de paginação

curl "http://localhost:5000/api/v2/faturas?pagina=2&por_pagina=50"
# Deve retornar: próximas 50 faturas
```

---

### Fase 8: Testes de Segurança

#### Test 8.1: Não Apagar Dados
```bash
# Listar arquivo original:
ls -la c:\code\SAMF-HUB-v1.1\Processados\CESAN-02-FEVEREIRO.pdf

# Depois de processar:
# ✓ Arquivo deve continuar em Processados
# ✓ Arquivo NUNCA é deletado
# ✓ Apenas movido de Faturas_entrada
```

#### Test 8.2: Não Duplicar Lançamentos
```sql
-- Processar mesma fatura 2x
-- Verificar se só tem 1 set de lançamentos

SELECT COUNT(DISTINCT fatura_id) FROM lancamentos WHERE valor_lançado > 0;
-- Se processou 2x fatura 1, deve ter só 1 fatura_id, não 2
```

#### Test 8.3: Rejeitar sem Justificativa
```bash
curl -X POST http://localhost:5000/api/v2/faturas/1/classificar \
  -H "Content-Type: application/json" \
  -d '{"classificacao":"compartilhado","justificativa":""}'

# Esperado: Erro 400
# "Justificativa obrigatória"
```

---

## 📊 Relatório de Testes

Após executar todos os testes, preencher:

| Fase | Teste | Status | Observações |
|------|-------|--------|-------------|
| 2 | 2.1 Import | ☐ PASSOU | |
| 2 | 2.2 Compartilhado | ☐ PASSOU | |
| 2 | 2.3 Exclusivo | ☐ PASSOU | |
| 2 | 2.4 Ambíguo | ☐ PASSOU | |
| 3 | 3.1 Health | ☐ PASSOU | |
| 3 | 3.2 Dashboard | ☐ PASSOU | |
| 4 | 4.1 HTML | ☐ PASSOU | |
| 4 | 4.2 Abas | ☐ PASSOU | |
| 4 | 4.3 Responsivo | ☐ PASSOU | |
| 5 | 5.1 Compartilhada | ☐ PASSOU | |
| 5 | 5.2 Exclusiva | ☐ PASSOU | |
| 5 | 5.3 Ambígua | ☐ PASSOU | |
| 5 | 5.4 Duplicação | ☐ PASSOU | |
| 5 | 5.5 PDF Ilegível | ☐ PASSOU | |
| 6 | 6.1 Validação | ☐ PASSOU | |
| 6 | 6.2 Auditoria | ☐ PASSOU | |
| 7 | 7.1 Performance | ☐ PASSOU | |
| 7 | 7.2 Paginação | ☐ PASSOU | |
| 8 | 8.1 Segurança Arquivos | ☐ PASSOU | |
| 8 | 8.2 Sem Duplicação | ☐ PASSOU | |
| 8 | 8.3 Validação Form | ☐ PASSOU | |

---

## ✅ Checklist de Entrega

- [ ] Todos os testes passaram
- [ ] Documentação atualizada
- [ ] Schema v2 criado no banco
- [ ] Classifier funcionando
- [ ] API respondendo
- [ ] Interface carregando
- [ ] PDFs sendo processados
- [ ] Auditoria registrando
- [ ] Relatórios gerando
- [ ] Usuários treinados

