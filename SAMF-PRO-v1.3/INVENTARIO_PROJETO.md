# Inventário do Projeto SAMF-HUB v1.1

## 1. Visão geral

Este repositório é um sistema monolítico em Python com frontend estático e banco SQLite para processamento automatizado de faturas, rateio por órgãos e exportação em planilha. O projeto possui uma versão de execução principal, uma estrutura de suporte para v2 e documentação técnica complementar.

Local real do workspace: `c:\code\SAMF-HUB-v1.1`

Arquivos e pastas observados na raiz:
- `Scripts/`
- `Interface_Web/`
- `Configuracoes/`
- `Faturas_entrada/`
- `Processados/`
- `Duplicados/`
- `Erro/`
- `Relatorios/`
- `samf.db`
- `README.md`
- `docker-compose.yml`
- `SAMF_Dashboard_Final.html`
- `CONFIGURACAO_SAMF.md`
- `PARECER_PROFISSIONAL_v1.0.md`
- `SAMF_v2_EXEMPLOS_PRATICOS.md`
- `SAMF_v2_GUIA_COMPLETO.md`
- `SAMF_v2_PLANO_TESTES.md`

## 2. Estrutura de pastas e objetivo

### Raiz do projeto
- `Scripts/`: lógica principal em Python, banco e tratamento dos PDFs.
- `Interface_Web/`: backend Flask e frontend estático.
- `Configuracoes/`: arquivos de configurações e resultado do processamento.
- `Faturas_entrada/`: diretório de entrada para PDFs novos.
- `Processados/`: arquivos processados com sucesso.
- `Duplicados/`: arquivos repetidos por hash.
- `Erro/`: erros de execução.
- `Relatorios/`: relatórios Excel exportados.
- `samf.db`: banco SQLite real em uso.

### Observação importante
A estrutura atual está funcional como protótipo/ambiente de desenvolvimento e não representa uma instalação com produção definitiva. O projeto possui valores de configuração vazios e caminhos de operação que precisam ser confirmados antes de uso em ambiente real.

## 3. Frontend

### Arquivo principal
- `Interface_Web/backend/static/index.html`

### Funções observadas no frontend
- navegação por tabs de dashboard, faturas, rateios, exportação e logs;
- carregamento de estatísticas por API;
- listagem de faturas por status;
- modal de configuração com campos de entrada do sistema;
- integração com backend para salvar e consultar config;
- exportação via API e consulta de logs.

### Arquivos de frontend auxiliares
- `SAMF_Dashboard_Final.html`: dashboard final estático de referência;
- `Interface_Web/backend/static/index_v2.html`: versão v2 com estrutura mais avançada; não é a interface ativa principal observada no backend.

## 4. Backend

### Arquivo principal
- `Interface_Web/backend/app.py`

### Configurações do backend
- base path fixa: `c:\code\SAMF-HUB-v1.1`
- criação automática de `Faturas_entrada` ao iniciar
- carregamento e persistência de configuração em `Configuracoes/samf_config.json`

### Rotas principais do backend
- `/` e aliases de rotas do frontend
- `/api/config` (GET/POST)
- `/api/stats`
- `/api/rateios`
- `/api/faturas`
- `/api/faturas/<id>/detalhes`
- `/api/logs`
- `/api/export/<mes>`
- `/api/upload`

### Observação sobre a API
A API usa Flask com `flask-cors` e tenta invocar diretamente scripts do projeto. A rota de upload salva o PDF em `Faturas_entrada` e executa `Scripts/processar_fatura.py` em subprocesso.

## 5. Banco de dados

### Arquivo principal
- `Scripts/database.py`
- `Scripts/db.py`
- `samf.db`

### Caminho do banco
O banco utilizado pela aplicação é:
- `c:\code\SAMF-HUB-v1.1\samf.db`

### Schema principal em uso
- `Scripts/schema.sql`

### Tabelas principais
- `orgaos`
- `padroes_rateio`
- `servicos`
- `faturas`
- `rateios_calculados`
- `logs_processamento`

### Dados gerados/semiautomatizados
- `seed_db.py` preenche órgãos e serviços iniciais;
- `padroes_rateio` guarda os percentuais por órgão e padrão;
- `faturas` guarda hash, caminho, nome do arquivo, serviço, valor, status e timestamps;
- `rateios_calculados` guarda a distribuição por órgão;
- `logs_processamento` guarda os logs do processamento.

### Observação sobre v2
Existe também um esquema v2 conceitual em `Scripts/schema_v2.sql`, mas o runtime atual do projeto continua utilizando o schema legado em `schema.sql` e o banco `samf.db` real.

## 6. Scripts de processamento e automação

### `Scripts/processar_fatura.py`
Funções centrais:
- `carregar_configuracao(raiz)`
- `validar_configuracao(config)`
- `calcular_hash(filepath)`
- `extrair_texto(filepath)`
- `salvar_log(conn, fatura_id, status, mensagem, hash_arq=None)`
- `processar(raiz, caminho_pdf)`

Fluxo real:
1. leitura da configuração em `Configuracoes/samf_config.json`;
2. validação de campos obrigatórios e caminhos;
3. cálculo de hash SHA-256;
4. verificação de duplicidade no SQLite;
5. extração de texto do PDF com `pdfplumber`;
6. identificação do fornecedor/serviço a partir do texto bruto;
7. extração do valor total por regex;
8. gravar registro em `faturas`;
9. calcular rateios por órgão;
10. salvar log e gerar JSON de resultado em `Configuracoes/resultado.json`.

### `Scripts/robo_vigia.py`
Objetivo:
- monitora a pasta `Faturas_entrada` em loop;
- aguarda a estabilidade do arquivo antes de processar;
- executa `processar_fatura.py` em subprocesso;
- move o PDF para `Processados` após processamento.

### `Scripts/exportar_excel.py`
Objetivo:
- exporta os dados de `faturas` e `rateios_calculados` para planilha Excel;
- usa `openpyxl`;
- salva um arquivo `Relatorios/Despesas_YYYY_MM.xlsx`.

### `Scripts/seed_db.py`
Objetivo:
- inicializar dados de órgãos, padrões de rateio e serviços;
- usa uma base de percentuais em código e insere no banco.

## 7. Processamento de PDFs

### Bibliotecas observadas
- `pdfplumber` na rotina de extração textual;
- `pytesseract` e `Pillow` presentes em `Scripts/requirements.txt`, mas a rotina principal observada usa `pdfplumber` diretamente.

### Regras de negócio observadas no código
- existe validação de configuração antes do processamento;
- arquivos duplicados são bloqueados por hash;
- PDF sem texto extraível vai para revisão;
- fornecedor e serviço são identificados por substrings do texto;
- valor total é extraído por regex de valores no padrão brasileiro;
- rateio é calculado por padrão A/B e segue ajuste final para SIG.

## 8. Configuração e dados operacionais

### Arquivo de configuração atual
- `Configuracoes/samf_config.json`

Conteúdo atual observado:
- todos os campos de configuração estão vazios;
- isso impede o processamento sem confirmação do usuário/operador.

### Campos do config
- `entrada_path`
- `planilha_path`
- `valor_base`
- `modo_execucao`
- `backup_path`
- `percentuais_rateio`
- `usuarios_permissoes`
- `arredondamento`

### Observação
A configuração atual não contém valores de produção reais. O sistema exige preenchimento antes de processar. Isso está explícito em `Scripts/processar_fatura.py` via `validar_configuracao`.

## 9. Testes

### Testes encontrados
- `Scripts/test_classifier.py`
- `Scripts/test_configuracao.py`

### Finalidade
- classificação e validação de configuração;
- regressão de regras de classificação e bloqueio de processamento quando a configuração está incompleta.

### Observação
Os testes existem no projeto e foram usados para validar a proteção anti-configuração incompleta, mas não substituem dados de produção reais.

## 10. Documentação

### Documentos relevantes
- `README.md`: visão geral e uso do projeto;
- `CONFIGURACAO_SAMF.md`: configuração do ambiente local;
- `PARECER_PROFISSIONAL_v1.0.md`: parecer técnico e arquitetura;
- `SAMF_v2_GUIA_COMPLETO.md`: guia da versão v2;
- `SAMF_v2_PLANO_TESTES.md`: plano de testes do modelo v2;
- `SAMF_v2_EXEMPLOS_PRATICOS.md`: exemplos práticos e cenários de uso.

### Observação
Os documentos v2 são úteis para referência conceitual, mas o banco e a execução atual do projeto continuam no modelo legado/SQLite principal.

## 11. Dependências e requisitos

### Requisitos do projeto
- `Scripts/requirements.txt`
- `Interface_Web/backend/requirements.txt`

### Dependências observadas
- `pdfplumber`
- `pytesseract`
- `Pillow`
- `openpyxl`
- `python-dotenv`
- `flask`
- `flask-cors`

## 12. Estado real do projeto

### O que existe de fato
- estrutura funcional de processamento de PDF;
- backend Flask com dashboard e rotas;
- banco SQLite com dados e schema real;
- scripts de automação e exportação;
- testes de configuração e classificação;
- documentação técnica do projeto.

### O que ainda está ausente para uso operacional real
- caminhos reais de produção para entrada/backup/relatório;
- percentuais oficiais e definitivos de rateio;
- planilha oficial de referência ou caminho configurado para a planilha;
- valores de produção e permissões reais;
- dados operacionais concretos para ambiente corporativo.

## 13. Conclusão da análise

O projeto é um protótipo funcional com arquitetura real e integração entre backend, banco e processamento de PDFs, mas não possui o conjunto completo de dados de produção necessários para operar como sistema definitivo sem confirmação de configuração e dados reais.

## 14. Verificação de ausência de dados reais

Existem ausências relevantes de:
- caminhos de produção reais;
- percentuais oficiais de rateio;
- planilha oficial de referência;
- dados de usuários/permissões concretos;
- configuração operacional completa e validada.

No arquivo `Configuracoes/samf_config.json`, os campos importantes aparecem em branco. A estrutura do projeto confirma que a aplicação foi concebida para operar com esses dados, mas eles não estão materializados no repositório atual.
