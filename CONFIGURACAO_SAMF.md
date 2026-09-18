SAMF PRO — Configuração e Estado Atual

Base de trabalho verificada no ambiente atual:
- Pasta raiz: c:\code\SAMF-HUB-v1.1
- Pasta de entrada: c:\code\SAMF-HUB-v1.1\Faturas_entrada
- Pasta processada: c:\code\SAMF-HUB-v1.1\Processados
- Pasta de erro: c:\code\SAMF-HUB-v1.1\Erro
- Pasta duplicadas: c:\code\SAMF-HUB-v1.1\Duplicados
- Pasta de relatórios: c:\code\SAMF-HUB-v1.1\Relatorios
- Banco atual: c:\code\SAMF-HUB-v1.1\samf.db
- Backend web: c:\code\SAMF-HUB-v1.1\Interface_Web\backend\app.py

Implementações aplicadas na revisão atual:
- Lógica de classificação prioriza serviço + fornecedor + complemento + unidade/endereço.
- Fornecedores ambíguos exigem complemento para sair de revisão.
- Monitor de entrada garante espera de estabilidade antes do processamento de PDFs.
- Rotas do frontend foram ampliadas para manter navegação compatível com os menus esperados.

Itens que ainda dependem de confirmação do usuário/ambiente:
- Caminho exato da planilha oficial de rateio.
- Percentuais e regras definitivas por órgão e competência.
- Beneficiário exclusivo para cada caso não identificado pela fatura.
- Modo de execução: manual, automática, agendada ou híbrida.
- Usuários e perfis de acesso finais.
- Base de cálculo usada na planilha: bruto, líquido ou final.
- Política de arredondamento residual e backup.

Observação importante:
O sistema não deve inventar valores, percentuais, competências, fornecedores, órgãos ou regras sem evidência real no banco, nos PDFs ou na planilha oficial. Quando a informação não puder ser comprovada, o documento deve permanecer em revisão.
