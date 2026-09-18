"""Orquestracao agendada de cobrancas sem dados incompletos."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, Callable, Dict, Iterable
from zoneinfo import ZoneInfo


class ErroAgendamentoCobrancas(ValueError):
    pass


class ProcessadorAgendadoCobrancas:
    def __init__(
        self,
        config: Dict[str, Any],
        *,
        ler_planilha: Callable[[], Dict[str, Any]] | None = None,
        atualizar_contas: Callable[[Iterable[Dict[str, Any]], Dict[str, Any]], Dict[str, Any]],
        recalcular_status: Callable[[Iterable[Dict[str, Any]], Dict[str, Any]], Iterable[Dict[str, Any]]],
        aplicar_regras: Callable[[Iterable[Dict[str, Any]], Dict[str, Any]], Iterable[Dict[str, Any]]],
        gerar_previa: Callable[[Dict[str, Any]], Any],
        enviar: Callable[[Dict[str, Any]], Any],
        verificar_duplicidade: Callable[[Dict[str, Any]], bool],
        registrar: Callable[[Dict[str, Any]], None] | None = None,
        agora: Callable[[], datetime] | None = None,
        raiz: str | None = None,
        conn=None,
    ) -> None:
        self.config = config
        self.conn = conn
        self.raiz = raiz
        if ler_planilha is None:
            from integracao_operacional_cobrancas import ler_planilha_operacional
            self.ler_planilha = lambda: ler_planilha_operacional(config, raiz=raiz)
        else:
            self.ler_planilha = ler_planilha
        self.atualizar_contas = atualizar_contas
        self.recalcular_status = recalcular_status
        self.aplicar_regras = aplicar_regras
        self.gerar_previa = gerar_previa
        self.enviar = enviar
        self.verificar_duplicidade = verificar_duplicidade
        self.registrar = registrar
        self.agora = agora or (lambda: datetime.now(timezone.utc))

    def deve_executar(self, momento: datetime | None = None) -> bool:
        local = self._localizar(momento or self.agora())
        dias = self._dias_configurados()
        if dias and local.weekday() not in dias:
            return False
        horario = str(self.config.get('cobrancas_horario_execucao') or '').strip()
        return _hora_na_faixa(local.time(), horario) if horario else True

    def executar(self, momento: datetime | None = None) -> Dict[str, Any]:
        inicio = self.agora().astimezone(timezone.utc)
        resultado: Dict[str, Any] = {
            'status': 'iniciado', 'inicio': inicio.isoformat(), 'fim': None,
            'quantidade_analisada': 0, 'quantidade_elegivel': 0,
            'quantidade_enviada': 0, 'quantidade_previas': 0, 'erros': [],
        }
        if not self.deve_executar(momento):
            resultado.update(status='fora_da_janela', fim=self.agora().astimezone(timezone.utc).isoformat())
            return self._finalizar(resultado)
        try:
            if self.conn is not None:
                from integracao_operacional_cobrancas import executar_integracao_planilha
                integracao = executar_integracao_planilha(
                    self.conn, self.config, raiz=self.raiz,
                    data_atual=(momento or self.agora()).date(),
                )
                resultado.update(
                    status='concluido' if integracao['status'] == 'sucesso' else integracao['status'],
                    quantidade_analisada=integracao.get('criadas', 0) + integracao.get('atualizadas', 0),
                    erros=[] if integracao['status'] == 'sucesso' else [integracao.get('erro', 'Leitura não concluída.')],
                )
                return self._finalizar(resultado)
            leitura = self.ler_planilha()
            if str(leitura.get('status', '')).lower() != 'sucesso':
                raise ErroAgendamentoCobrancas(leitura.get('erro') or 'Leitura da planilha não concluída.')
            linhas = list(leitura.get('linhas', []))
            resultado['quantidade_analisada'] = len(linhas)
            contas = self.atualizar_contas(linhas, leitura)
            contas_atualizadas = list(contas.get('contas', contas if isinstance(contas, list) else []))
            contas_status = list(self.recalcular_status(contas_atualizadas, self.config))
            elegiveis = list(self.aplicar_regras(contas_status, self.config))
            resultado['quantidade_elegivel'] = len(elegiveis)
            modo = str(self.config.get('cobrancas_modo_operacao') or 'somente_analise').strip().lower()
            for item in elegiveis:
                if self.verificar_duplicidade(item):
                    continue
                if modo == 'somente_analise':
                    continue
                if modo == 'previa' or not self._envio_permitido():
                    self.gerar_previa(item)
                    resultado['quantidade_previas'] += 1
                elif modo == 'envio_autorizado':
                    self.enviar(item)
                    resultado['quantidade_enviada'] += 1
                else:
                    raise ErroAgendamentoCobrancas(f'Modo de operação inválido: {modo}.')
            resultado['status'] = 'concluido'
        except Exception as exc:
            resultado['status'] = 'erro'
            resultado['erros'].append(str(exc))
        resultado['fim'] = self.agora().astimezone(timezone.utc).isoformat()
        return self._finalizar(resultado)

    def _envio_permitido(self) -> bool:
        if str(self.config.get('cobrancas_modo_operacao') or '').strip().lower() != 'envio_autorizado':
            return False
        local = self._localizar(self.agora())
        silencio = str(self.config.get('cobrancas_janela_silencio') or '').strip()
        return not _hora_na_faixa(local.time(), silencio) if silencio else True

    def _dias_configurados(self) -> set[int]:
        valor = str(self.config.get('cobrancas_dias_semana') or '').strip()
        if not valor:
            return set()
        try:
            dias = {int(item.strip()) for item in valor.split(',')}
        except ValueError as exc:
            raise ErroAgendamentoCobrancas('Dias da semana inválidos.') from exc
        if not dias <= set(range(7)):
            raise ErroAgendamentoCobrancas('Dias da semana devem usar valores de 0 a 6.')
        return dias

    def _localizar(self, momento: datetime) -> datetime:
        fuso = str(self.config.get('cobrancas_fuso_horario') or 'UTC').strip()
        try:
            return momento.astimezone(ZoneInfo(fuso))
        except Exception as exc:
            raise ErroAgendamentoCobrancas(f'Fuso horário inválido: {fuso}.') from exc

    def _finalizar(self, resultado):
        if self.registrar:
            self.registrar(resultado)
        return resultado


def _hora_na_faixa(valor: time, faixa: str) -> bool:
    try:
        inicio_texto, fim_texto = faixa.split('-', 1)
        inicio = time.fromisoformat(inicio_texto.strip())
        fim = time.fromisoformat(fim_texto.strip())
    except ValueError as exc:
        raise ErroAgendamentoCobrancas(f'Faixa de horário inválida: {faixa}.') from exc
    return inicio <= valor <= fim if inicio <= fim else valor >= inicio or valor <= fim
