# SAMF – Sistema de Automação de Mensuração de Faturas (Versão SQLite)

O SAMF é uma solução integrada para automação do rateio de despesas condominiais entre 15 órgãos federais. Esta versão utiliza **SQLite**, sendo ideal para ambientes corporativos com restrições de instalação e firewall.

---

## 1. Estrutura de Pastas (OneDrive)
Certifique-se de que a pasta raiz `SAMF` contenha a seguinte estrutura:

```text
SAMF/
├── Faturas_entrada/   <-- Onde você coloca os PDFs novos
├── Processados/       <-- Sucesso no processamento
├── Revisao_Manual/    <-- PDFs com baixa confiança ou erro de leitura
├── Duplicados/        <-- Arquivos repetidos (Hash SHA-256)
├── Erro/              <-- Erros técnicos de execução
├── Relatorios/        <-- Onde os arquivos Excel (.xlsx) são salvos
├── Configuracoes/     <-- Pasta técnica para o arquivo resultado.json
├── Scripts/           <-- Scripts Python (.py) e banco de dados (samf.db)
└── Interface_Web/     <-- Sistema visual (Backend e Frontend)
```

---

## 2. Instalação e Configuração Inicial

### Passo 1: Preparar o Banco de Dados
Abra o Prompt de Comando (CMD) na pasta `Scripts` e execute:
```cmd
python seed_db.py
```
*Isso criará o arquivo `samf.db` e carregará os 15 órgãos e os 17 serviços padrão.*

### Passo 2: Configurar o Power Automate Desktop (PAD)
No seu fluxo do PAD, garanta que:
1.  A variável `%BasePath%` aponte para a raiz da pasta `SAMF\`.
2.  A ação **Executar aplicativo** chame o script:
    `python.exe "%BasePath%Scripts\processar_fatura.py" "%BasePath%" "%CurrentItem.FullName%"`
3.  O tempo de **Aguardar** após a execução seja de **10 segundos**.

---

## 3. Como Operar o Sistema

1.  **Processamento Automático**: Basta jogar os PDFs na pasta `Faturas_entrada`. O robô (PAD) processará e moverá os arquivos para as pastas de destino.
2.  **Visualização de Dados**: Use o **DBeaver** para abrir o arquivo `samf.db` e consultar as tabelas `faturas` e `rateios_calculados`.
3.  **Geração de Relatórios**:
    - Rode o script `exportar_excel.py` via CMD:
      `python Scripts/exportar_excel.py "C:\Caminho\SAMF" "2026-07"`
    - O arquivo Excel será gerado na pasta `Relatorios`.

---

## 4. Regras de Negócio (Rateio)
- **Padrão A**: Rateio baseado em ocupação de área (usado para Água, Energia, Limpeza, etc.).
- **Padrão B**: Rateio baseado em pontos de telefonia (usado para Telecomunicações).
- **Ajuste SIG**: O 15º órgão (SIG) recebe automaticamente a diferença de centavos para garantir que a soma dos rateios seja sempre exatamente igual ao valor total da fatura.

---

## 5. Troubleshooting (Resolução de Problemas)
- **Erro "ModuleNotFoundError"**: Certifique-se de ter instalado as dependências: `pip install pdfplumber openpyxl flask flask-cors`.
- **Arquivo não move da pasta**: Verifique no CMD se o script `processar_fatura.py` está dando algum erro de sintaxe.
- **Banco não encontrado**: Verifique se o arquivo `database.py` está com o nome correto e se o `samf.db` está na raiz da pasta.

---
**Desenvolvido para:** Ministério da Gestão e da Inovação dos Serviços Públicos (MGI).



"""cd "c:\Users\nerivaldo.junior\OneDrive - Ministério da Gestão e da Inovação dos Serv. Pub\samf"
& ".\.venv\Scripts\Activate.ps1"
python .\Interface_Web\backend\app.py"""



"""cd "c:\Users\nerivaldo.junior\OneDrive - Ministério da Gestão e da Inovação dos Serv. Pub\samf"
& ".\.venv\Scripts\Activate.ps1"
python .\Scripts\robo_vigia.py"""
