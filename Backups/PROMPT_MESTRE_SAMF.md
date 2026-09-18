# Prompt mestre para trabalhar no SAMF PRO

Use este contexto antes de analisar, corrigir ou ampliar o projeto.

## Objetivo

Entender o SAMF PRO como um sistema local de gestão de faturas, rateio, auditoria, cobranças e vencimentos. Preserve dados existentes, faça mudanças pequenas e valide cada fluxo pelo código e por um teste executável.

## Projeto

- Raiz: `C:\CodeForge\SAMF-PRO-v1.3`
- Sistema operacional: Windows
- Ambiente Python: `.venv`
- Backend principal compatível com a interface: `Interface_Web\backend\app.py`
- Backend legado/protótipo: `Interface_Web\backend\app_v2.py`; não iniciar este para a interface atual.
- Frontend: `Interface_Web\backend\static\index.html`
- Banco local: `samf.db` usando SQLite.
- Provedor atual: `DB_PROVIDER=sqlite` no `.env`.
- Porta padrão: `5000`
- Inicializador completo: `RODAR_SAMF_COMPLETO.ps1`
- Atalho Windows: `INICIAR_SAMF.bat`

## Como iniciar

```powershell
Set-Location "C:\CodeForge\SAMF-PRO-v1.3"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\RODAR_SAMF_COMPLETO.ps1
```

Ou execute `INICIAR_SAMF.bat`.

API: `http://127.0.0.1:5000`

Validação:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/auth/status
```

## Banco e domínios

Há dois domínios de dados diferentes:

1. `faturas`: faturas de entrada, extração de PDF, classificação, rateio e dashboard em `/api/stats`.
2. `contas`: contas de cobrança, planilha oficial, vencimentos, destinatários e mensagens em `/api/cobrancas/...`.

Não presumir que uma conta em `contas` apareça automaticamente no dashboard geral. O dashboard geral consulta `faturas`; as telas de cobranças consultam `contas`.

## Planilha de cobranças

- Arquivo: `Relatorios\cobrancas_teste.xlsx`
- Aba: `Cobrancas`
- Mapeamento: `Configuracoes\mapeamento_cobrancas_teste.json`
- Configuração: `Configuracoes\samf_config.json`
- O leitor exige datas no formato brasileiro `DD/MM/AAAA` quando a célula contém texto.
- Campos obrigatórios: órgão, fornecedor, serviço, competência, vencimento, valor original, valor pago e valor pendente.
- A integração oficial é `Scripts\integracao_operacional_cobrancas.py`.
- Antes de concluir, executar o leitor oficial e confirmar `status=sucesso` e `linhas_invalidas=0`.

## Login

- O usuário atual é `samfpro`, perfil administrador e ativo.
- A senha nunca deve ser lida, impressa ou incluída neste documento; o banco armazena somente hash scrypt.
- Para redefinir a senha, digite o segredo diretamente no prompt:

```powershell
Set-Location "C:\CodeForge\SAMF-PRO-v1.3"
$env:PYTHONPATH = "$PWD\Scripts"
& ".\.venv\Scripts\python.exe" ".\Scripts\alterar_senha_usuario.py" samfpro
```

- Não misturar comandos PowerShell com respostas dos prompts do programa.
- O nome do usuário informado ao comando precisa ser separado por espaço do caminho do script.
- Em caso de sessão antiga no navegador, limpar no Console do navegador:

```javascript
localStorage.removeItem('samf_token');
localStorage.removeItem('samf_usuario');
location.reload();
```

## Regras de diagnóstico

- `401` em `/api/auth/login`: usuário ou senha inválidos; o backend e o banco podem estar funcionando.
- `401` em `/api/stats` ou `/api/config`: token ausente, expirado ou inválido.
- `404` em `/api/auth/status`, `/api/config` ou `/api/stats`: foi iniciado `app_v2.py` em vez de `app.py`.
- Página branca: a rota `/` deve servir `static/index.html`; não usar o shell antigo que referencia `static/app.js`.
- Planilha não carrega: conferir caminho configurado, aba, mapeamento ativo, formato `DD/MM/AAAA` e `linhas_invalidas`.
- Dashboard vazio: consultar primeiro `SELECT COUNT(*) FROM faturas`; não confundir com a tabela `contas`.
- Não executar `-InicializarBanco` sem confirmar, pois `seed_db.py` recria dados de referência.

## Procedimento para qualquer mudança

1. Identificar a rota, tabela, função e arquivo que controlam o comportamento.
2. Ler testes próximos antes de editar.
3. Preservar dados e configurações existentes.
4. Fazer a menor alteração possível.
5. Rodar validação focada imediatamente após editar.
6. Confirmar API, banco e interface separadamente quando o fluxo envolver os três.
7. Não expor senhas, tokens, hashes completos ou credenciais.
8. Não usar `app_v2.py` como solução para a interface atual.

## Estado conhecido

- O backend principal foi corrigido para servir o frontend real e apontar para a raiz atual do projeto.
- A planilha de teste contém registros fictícios de cobrança, incluindo vencimentos próximos.
- A leitura oficial da planilha deve ser a fonte de verdade para novas contas.
- O dashboard geral e o módulo de cobranças têm fontes de dados distintas e podem exigir sincronização explícita se o requisito for mostrar cobranças no dashboard.

## Solicitação padrão para o agente

> Analise o SAMF PRO respeitando todo o contexto acima. Explique primeiro qual tabela, rota e função controlam o problema. Faça uma hipótese verificável, aplique a menor correção necessária, preserve dados existentes e execute uma validação focada. Ao final, informe arquivos alterados, comandos executados e o resultado objetivo dos testes. Não invente credenciais nem exponha segredos.
