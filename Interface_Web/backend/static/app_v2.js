/**
 * SAMF v2.0 - Frontend Professional
 * Interface para processamento profissional de faturas e rateios
 */

const API = '/api/v2';
let app = new Vue({
    el: '#app',
    data: {
        tab_ativo: 'dashboard',
        dashboard: null,
        faturas: [],
        faturas_em_revisao: [],
        fatura_selecionada: null,
        filtros: {
            status: '',
            classificacao: '',
            fornecedor: '',
            competencia: '',
            busca: ''
        },
        loading: false,
        mensagem_sucesso: '',
        mensagem_erro: '',
        pagina: 1,
        por_pagina: 50,
        total_faturas: 0
    },
    computed: {
        titulo_tab() {
            const titulos = {
                'dashboard': '📊 Dashboard',
                'faturas': '📋 Faturas Processadas',
                'revisao': '⚠️ Aguardando Revisão',
                'rateios': '📊 Matriz de Rateios',
                'validacao': '✓ Validação'
            };
            return titulos[this.tab_ativo] || 'SAMF v2.0';
        },
        cor_classificacao() {
            return {
                'compartilhado': '#3b82f6',
                'exclusivo': '#8b5cf6',
                'revisao': '#f59e0b',
                'erro': '#ef4444'
            };
        }
    },
    methods: {
        mudar_tab(tab) {
            this.tab_ativo = tab;
            this.mensagem_sucesso = '';
            this.mensagem_erro = '';
            
            if (tab === 'dashboard') this.carregar_dashboard();
            if (tab === 'faturas') this.carregar_faturas();
            if (tab === 'revisao') this.carregar_revisao();
            if (tab === 'rateios') this.carregar_rateios();
            if (tab === 'validacao') this.carregar_validacao();
        },
        
        async carregar_dashboard() {
            this.loading = true;
            try {
                const resp = await fetch(`${API}/dashboard`);
                this.dashboard = await resp.json();
            } catch (e) {
                this.mensagem_erro = `Erro ao carregar dashboard: ${e.message}`;
            } finally {
                this.loading = false;
            }
        },
        
        async carregar_faturas() {
            this.loading = true;
            try {
                const params = new URLSearchParams({
                    pagina: this.pagina,
                    por_pagina: this.por_pagina,
                    ...Object.fromEntries(Object.entries(this.filtros).filter(([,v]) => v))
                });
                
                const resp = await fetch(`${API}/faturas?${params}`);
                const data = await resp.json();
                this.faturas = data.faturas;
                this.total_faturas = data.total;
            } catch (e) {
                this.mensagem_erro = `Erro ao carregar faturas: ${e.message}`;
            } finally {
                this.loading = false;
            }
        },
        
        async carregar_revisao() {
            this.loading = true;
            try {
                const resp = await fetch(`${API}/faturas-revisao`);
                const data = await resp.json();
                this.faturas_em_revisao = data.faturas_em_revisao;
            } catch (e) {
                this.mensagem_erro = `Erro ao carregar revisão: ${e.message}`;
            } finally {
                this.loading = false;
            }
        },
        
        async carregar_rateios() {
            this.loading = true;
            try {
                const resp = await fetch(`${API}/rateios`);
                this.rateios = (await resp.json()).rateios;
            } catch (e) {
                this.mensagem_erro = `Erro ao carregar rateios: ${e.message}`;
            } finally {
                this.loading = false;
            }
        },
        
        async carregar_validacao() {
            this.loading = true;
            try {
                const resp = await fetch(`${API}/validacao`);
                this.validacao = await resp.json();
            } catch (e) {
                this.mensagem_erro = `Erro ao carregar validação: ${e.message}`;
            } finally {
                this.loading = false;
            }
        },
        
        async ver_detalhes(fatura_id) {
            this.loading = true;
            try {
                const resp = await fetch(`${API}/faturas/${fatura_id}`);
                this.fatura_selecionada = await resp.json();
            } catch (e) {
                this.mensagem_erro = `Erro ao carregar detalhes: ${e.message}`;
            } finally {
                this.loading = false;
            }
        },
        
        async classificar_fatura(fatura_id, classificacao, justificativa) {
            if (!justificativa) {
                this.mensagem_erro = 'Justificativa é obrigatória';
                return;
            }
            
            this.loading = true;
            try {
                const resp = await fetch(`${API}/faturas/${fatura_id}/classificar`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ classificacao, justificativa, usuario: 'admin' })
                });
                
                if (resp.ok) {
                    this.mensagem_sucesso = 'Fatura classificada com sucesso!';
                    this.fatura_selecionada = null;
                    setTimeout(() => this.carregar_revisao(), 500);
                } else {
                    this.mensagem_erro = 'Erro ao classificar fatura';
                }
            } catch (e) {
                this.mensagem_erro = `Erro: ${e.message}`;
            } finally {
                this.loading = false;
            }
        },
        
        formatar_valor(valor) {
            return new Intl.NumberFormat('pt-BR', {
                style: 'currency',
                currency: 'BRL'
            }).format(valor || 0);
        },
        
        formatar_data(data) {
            if (!data) return '-';
            return new Date(data).toLocaleDateString('pt-BR');
        }
    },
    
    mounted() {
        this.carregar_dashboard();
    }
});
