# SAMF v2.0 - Exemplos Práticos de Classificação

## 📌 Caso 1: Água e Esgoto - Compartilhado

**Arquivo da Fatura:**
```
CESAN - 02 - FEVEREIRO - ED.SEDE.pdf
```

**Dados Extraídos:**
```
Fornecedor: CESAN
Serviço: Água e Esgoto
Complemento: "Edifício-Sede"
Valor Total: R$ 5.617,62
Competência: 2026-02
Endereço: Avenida Getúlio Vargas, Vitória - ES
```

**Processo de Classificação:**

1. **Verificar em COMPARTILHADOS**
   - CESAN + Água e Esgoto? ✅ Encontrado na lista
   - Indicadores especiais: ['edifício-sede', 'ed. sede', 'central']
   - Complemento contém: "ed. sede"? ✅ SIM

2. **Resultado**
   ```
   Classificação: COMPARTILHADO
   Confiança: 0.95 (95%)
   Regra: COMPARTILHADO: CESAN + Água e Esgoto + ed. sede
   ```

3. **Cálculo de Rateio**
   ```
   Valor Total: R$ 5.617,62
   
   Aplicar matriz COMPARTILHADO (percentuais da planilha):
   - SRA: 15.45% = R$ 867,42
   - DRF: 10.00% = R$ 561,76
   - ... (todos os órgãos compartilhados)
   
   Validação: Soma = R$ 5.617,62 ✅
   ```

4. **Auditoria**
   ```
   Tipo: leitura
   Resultado: Sucesso na extração
   
   Tipo: classificacao
   Resultado: Compartilhado com 95% confiança
   
   Tipo: calculo
   Resultado: 14 órgãos receberam parcelas
   
   Tipo: lancamento
   Resultado: 14 lançamentos realizados
   ```

---

## 📌 Caso 2: Dedetização - Ambígua (Requer Revisão)

**Arquivo da Fatura:**
```
AJP - 04 - ABRIL - ED SEDE - RATEIO.pdf
```

**Dados Extraídos:**
```
Fornecedor: AJP
Serviço: Dedetização
Complemento: "" (vazio/insuficiente)
Valor Total: R$ 2.535,00
Competência: 2026-04
Endereço: Avenida Getúlio Vargas, Vitória - ES
```

**Processo de Classificação:**

1. **Verificar em COMPARTILHADOS**
   - AJP + Dedetização? ✅ Encontrado
   - Indicadores: ['edifício-sede', 'ed. sede', 'central']
   - Complemento: "" → NÃO CONTÉM indicadores
   - Resultado: Pode ser compartilhado, mas sem certeza

2. **Verificar em EXCLUSIVOS**
   - AJP + Dedetização? ✅ Também encontrado
   - Indicadores: ['princesa isabel', 'unidade']
   - Complemento: "" → NÃO CONTÉM indicadores
   - Resultado: Pode ser exclusivo, mas sem certeza

3. **AJP é Fornecedor Ambíguo?**
   - Sim, aparece em compartilhado E exclusivo
   - Complemento insuficiente: "" (vazio)
   - Nome do arquivo diz "RATEIO" → Dica de compartilhado

4. **Resultado**
   ```
   Classificação: REVISAO
   Confiança: 0.50 (50%)
   Motivo: Fornecedor AJP ambíguo (aparece em compartilhado e exclusivo)
   Requer Intervenção: SIM
   ```

5. **Fila de Revisão**
   ```
   Apresentar para usuário com:
   - Evidências: "Nome do arquivo contém 'RATEIO' - indicador de compartilhado"
   - Opções:
     a) Aprovar como COMPARTILHADO (baseado no nome)
     b) Aprovar como EXCLUSIVO (se souber de unidade específica)
   - Campo obrigatório: Justificativa da decisão
   ```

6. **Se Aprovado como Compartilhado**
   ```
   Auditoria:
   Tipo: revisao
   Usuário: admin
   Decisão Anterior: revisao (50% confiança)
   Decisão Nova: compartilhado
   Justificativa: "Nome do arquivo contém 'RATEIO' indicando serviço compartilhado"
   Resultado: Aprovado em revisão manual
   
   Depois: Prosseguir com cálculo e lançamento como compartilhado
   ```

---

## 📌 Caso 3: Energia Elétrica - Exclusivo (Unidade Específica)

**Arquivo da Fatura:**
```
EDP - PRINCESA ISABEL - 05 - MAIO.pdf
```

**Dados Extraídos:**
```
Fornecedor: EDP
Serviço: Energia Elétrica
Complemento: "Princesa Isabel"
Valor Total: R$ 52.995,92
Competência: 2026-05
Órgão Beneficiário: (a extrair do PDF)
```

**Processo de Classificação:**

1. **Verificar em COMPARTILHADOS**
   - EDP + Energia Elétrica? ✅ Encontrado
   - Indicadores: ['edifício-sede', 'ed. sede', 'central']
   - Complemento contém: "Princesa Isabel"? ❌ NÃO
   - Descarta como compartilhado

2. **Verificar em EXCLUSIVOS**
   - EDP + Energia Elétrica? ✅ Encontrado
   - Indicadores: ['princesa isabel', 'unidade']
   - Complemento contém: "Princesa Isabel"? ✅ SIM

3. **Resultado**
   ```
   Classificação: EXCLUSIVO
   Confiança: 0.95 (95%)
   Regra: EXCLUSIVO: EDP + Energia Elétrica + Princesa Isabel
   Órgão Beneficiário: (identificar do PDF)
   ```

4. **Cálculo de Rateio (100% para um órgão)**
   ```
   Valor Total: R$ 52.995,92
   
   Órgão Beneficiário: [identificado do documento]
   ├─ SRA: R$ 52.995,92 (100%)
   ├─ Demais: R$ 0,00
   
   Validação: Soma = R$ 52.995,92 ✅
   ```

5. **Auditoria**
   ```
   Tipo: classificacao
   Resultado: Exclusivo com 95% confiança
   Evidência: Complemento contém "Princesa Isabel"
   
   Tipo: lancamento
   Resultado: 100% lançado para SRA; demais órgãos = R$ 0,00
   ```

---

## 📌 Caso 4: Auxiliar Administrativo - Exclusivo por Cidade

**Arquivo da Fatura:**
```
MAXIMA - AUXILIAR ADMINISTRATIVO - VITORIA - 2026-05.pdf
```

**Dados Extraídos:**
```
Fornecedor: MÁXIMA
Serviço: Auxiliar Administrativo
Complemento: "Vitória"
Valor Total: R$ 2.500,00
Competência: 2026-05
Órgão Beneficiário: (extrair do PDF)
```

**Processo de Classificação:**

1. **Verificar em EXCLUSIVOS**
   - MÁXIMA + Auxiliar Administrativo? ✅ Encontrado
   - Indicadores: ['vitória', 'cachoeiro', 'colatina', 'vila velha', 'cidade']
   - Complemento contém: "Vitória"? ✅ SIM

2. **Resultado**
   ```
   Classificação: EXCLUSIVO
   Confiança: 0.92 (92%)
   Regra: EXCLUSIVO: MÁXIMA + Auxiliar Administrativo + Vitória
   ```

3. **Lançamento**
   ```
   Órgão Beneficiário: [CGU | SERPRO | ...] (baseado no contexto)
   Valor: R$ 2.500,00 (100%)
   ```

---

## 📌 Caso 5: Telefonia VIVO - Pode Ser Ambígua

**Arquivo 1 - Compartilhada:**
```
VIVO FIXO - CENTRAL - 2026-05.pdf
Fornecedor: VIVO
Serviço: Telefonia Fixa
Complemento: "Central" / "Geral"
Valor: R$ 1.200,00

→ Classificação: COMPARTILHADO (percentuais para todos órgãos)
```

**Arquivo 2 - Exclusiva:**
```
VIVO FIXO PABX - 2026-05.pdf
Fornecedor: VIVO
Serviço: Telefonia Fixa
Complemento: "PABX"
Valor: R$ 800,00

→ Classificação: EXCLUSIVO (100% para órgão com PABX)
```

**Arquivo 3 - Ambígua:**
```
VIVO FIXO - 2026-05.pdf
Fornecedor: VIVO
Serviço: Telefonia Fixa
Complemento: "" (vazio)
Valor: R$ 950,00

→ Classificação: REVISAO (Confiança baixa - precisa determinar se central ou PABX)
```

---

## 📌 Caso 6: Duplicação Detectada

**Primeira Fatura:**
```
CESAN - FEVEREIRO - ED.SEDE - 2026-02.pdf
Hash: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
Fornecedor: CESAN
Número: 123456
Competência: 2026-02
Valor: R$ 5.617,62
Status: Processado
```

**Segunda Fatura (Duplicada):**
```
CESAN - FEV - SEDE.pdf
Hash: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6 (MESMO)
Ou: Mesmo fornecedor + número + competência + valor

→ Sistema detecta:
   Tipo: DUPLICADO
   Motivo: Hash idêntico / combinação fornecedor+número+competência+valor já existe
   Ação: Marcar como "duplicado", NÃO processar
   Auditoria: Registrar detecção e rejeição
```

---

## 📌 Caso 7: PDF Ilegível

**Arquivo da Fatura:**
```
fatura_escaneada_baixa_qualidade.pdf
```

**Processo:**
```
Tentativa de Extração de Texto:
- Sem OCR: 0 caracteres extraídos
- PDF é imagem: verdadeiro
- Resultado: Falha na leitura

Classificação: REVISAO
Confiança: 0.10 (10%)
Motivo: "PDF sem texto extraível (pode ser imagem/digitalização)"

Ação:
1. Registrar erro
2. Enviar para revisão
3. Usuário deve fazer OCR manual ou inserir dados manualmente
4. Aprovar após preenchimento manual
```

---

## 📌 Caso 8: Validação de Soma (Divergência)

**Fatura Processada:**
```
Valor Original: R$ 1.000,00

Lançamentos Realizados:
- SRA: R$ 154.50
- DRF: R$ 100.00
- CGU: R$ 745.49 (nota: deveria ser 745.50)
─────────────
Soma: R$ 999,99 (FALTA R$ 0,01)
```

**Detecção de Divergência:**
```
Tipo: soma_inconsistente
Valor Esperado: R$ 1.000,00
Valor Obtido: R$ 999,99
Diferença: R$ 0,01
Resolvido: NÃO

Sistema marca:
- divergencia_detectada = 1
- Registra na tabela divergencias
- Dashboard mostra: "1 divergência aberta"

Ação Recomendada:
1. Revisar cálculo de arredondamento
2. Ajustar um órgão em R$ 0,01 (geralmente o último)
3. Registrar ajuste na auditoria
4. Marcar como resolvido
```

---

## 🔄 Fluxograma Completo de Uma Fatura

```
┌─────────────────────┐
│  PDF na pasta       │
│  Faturas_entrada    │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│  Extrair dados:     │
│  - Fornecedor       │
│  - Serviço          │
│  - Valor            │
│  - Complemento      │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│  Verificar se já    │
│  foi processada     │
│  (hash/número)      │
└──────────┬──────────┘
       SIM │ NÃO
           ↓
    DUPLICADO ────→ Marcar como duplicado
                   Auditoria: Rejeição
           ↓
┌─────────────────────┐
│  Tentar classificar │
│  automaticamente    │
│  (classifier.py)    │
└──────────┬──────────┘
           ↓
    ┌─────┴─────────────┬──────────────┐
    ↓                   ↓              ↓
COMPARTILHADO       EXCLUSIVO       REVISAO
Confiança >80%      Confiança >80%  Confiança <80%
    ↓                   ↓              ↓
  Calcular Rateio    Lançar 100%   Fila de Revisão
    ↓                   ↓              ↓
  Validar Soma     Validar Soma   Aguardar Humano
    ↓                   ↓              ↓
 ✓/✗ Divergência   ✓/✗ Divergência   (humano escolhe)
    ↓                   ↓              ↓
  Lançar            Lançar         Lançar
  ↓                 ↓              ↓
AUDITORIA COMPLETA
  - Ação
  - Usuário
  - Dados
  - Resultado
  ↓
STATUS: LANÇADO ✅
```

---

## 💡 Regras de Ouro

1. **Nunca presumir**: Se duvidoso, enviar para revisão
2. **Sempre registrar**: Cada decisão fica na auditoria
3. **Sempre validar**: Soma de valores é obrigatória
4. **Nunca duplicar**: Hash e verificação de combinação única
5. **Nunca descartar**: PDF original sempre preservado
6. **Sempre confirmar**: Alterações manuais precisam de justificativa

