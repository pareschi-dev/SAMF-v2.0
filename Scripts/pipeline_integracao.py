"""Orquestração sequencial do fluxo completo de uma fatura."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from calculador_exclusivo import CalculadorDespesaExclusiva
from calculador_rateio import CalculadorRateioCompartilhado
from classifier import ClassificadorFaturas, FaturaExtraida
from extrator_pdf import extrair_pdf
from integrador_planilha import IntegradorPlanilha
from robo_vigia import MonitorPasta


STATUS_SUCESSO = 'PROCESSADA_COM_SUCESSO'
STATUS_REVISAO = 'AGUARDANDO_REVISÃO'
STATUS_DUPLICADA = 'DUPLICADA_OU_JÁ_PROCESSADA'
STATUS_NAO_PROCESSADA = 'NÃO_PROCESSADA'
STATUS_ERRO_LEITURA = 'ERRO_DE_LEITURA'
STATUS_ERRO_GRAVACAO = 'ERRO_DE_GRAVAÇÃO'


class PipelineIntegracao:
    """Executa o fluxo sem paralelismo e sem pular etapas validadas."""

    def __init__(
        self,
        config: Dict[str, Any],
        monitor: Optional[MonitorPasta] = None,
        extrator: Callable[[str], Dict[str, Any]] = extrair_pdf,
        classificador: Optional[ClassificadorFaturas] = None,
        regra_compartilhada: Optional[Callable[[Dict[str, Any]], Any]] = None,
        regra_exclusiva: Optional[Callable[[Dict[str, Any]], Any]] = None,
        orgaos: Optional[Callable[[], list[Any]]] = None,
        calculador_compartilhado: Optional[CalculadorRateioCompartilhado] = None,
        calculador_exclusivo: Optional[CalculadorDespesaExclusiva] = None,
        integrador: Optional[IntegradorPlanilha] = None,
        enriquecer: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        self.config = config
        self.monitor = monitor or MonitorPasta(config)
        self.extrator = extrator
        self.classificador = classificador or ClassificadorFaturas()
        self.regra_compartilhada = regra_compartilhada
        self.regra_exclusiva = regra_exclusiva
        self.orgaos = orgaos or (lambda: [])
        self.calculador_compartilhado = calculador_compartilhado or CalculadorRateioCompartilhado()
        self.calculador_exclusivo = calculador_exclusivo or CalculadorDespesaExclusiva()
        self.integrador = integrador or IntegradorPlanilha(config)
        self.enriquecer = enriquecer

    def processar_arquivo(self, caminho: Path) -> Dict[str, Any]:
        inicio = datetime.now(timezone.utc).isoformat()
        relatorio = {'arquivo_original': str(caminho), 'inicio': inicio, 'etapas': []}
        monitor_resultado = self.monitor.monitorar_arquivo(Path(caminho))
        self._etapa(relatorio, 'monitoramento', monitor_resultado)
        if monitor_resultado['status'] == 'duplicado':
            return self._finalizar(relatorio, STATUS_DUPLICADA, monitor_resultado.get('arquivo'))
        if monitor_resultado['status'] != 'processando':
            status = STATUS_NAO_PROCESSADA if monitor_resultado['status'] in {'ignorado_temporario', 'em_execucao'} else STATUS_ERRO_LEITURA
            return self._finalizar(relatorio, status, monitor_resultado.get('arquivo'))

        caminho_processando = Path(monitor_resultado['arquivo'])
        hash_arquivo = monitor_resultado.get('hash')
        try:
            extraido = self.extrator(str(caminho_processando))
        except Exception as exc:
            return self._encaminhar_erro(relatorio, caminho_processando, STATUS_ERRO_LEITURA, f'Falha de leitura: {exc}', hash_arquivo)
        self._etapa(relatorio, 'extracao', extraido)
        if extraido.get('status') in {'ilegivel', 'corrompido', 'protegido', 'erro'} or len(extraido.get('faturas', [])) != 1:
            motivo = extraido.get('erro') or 'Arquivo sem exatamente uma fatura legível.'
            return self._encaminhar_erro(relatorio, caminho_processando, STATUS_ERRO_LEITURA, motivo, hash_arquivo)

        dados = dict(extraido['faturas'][0])
        dados['nome_arquivo'] = caminho_processando.name
        dados['valor_base'] = dados.get('valor')
        if self.enriquecer:
            dados.update(self.enriquecer(dados) or {})
        self._etapa(relatorio, 'dados_para_classificacao', dados)
        try:
            fatura = FaturaExtraida(
                nome_arquivo=dados.get('nome_arquivo', caminho_processando.name),
                fornecedor=dados.get('fornecedor', ''),
                servico=dados.get('servico', ''),
                numero=dados.get('numero'), descricao=dados.get('descricao'), competencia=dados.get('competencia'),
                valor=dados.get('valor'), endereco=dados.get('endereco'), unidade=dados.get('unidade'),
                orgao_original=dados.get('orgao') or dados.get('orgao_original'), complemento=dados.get('complemento'), secao=dados.get('secao'),
            )
            classificacao = self.classificador.classificar(fatura)
        except Exception as exc:
            return self._encaminhar_erro(relatorio, caminho_processando, STATUS_ERRO_LEITURA, f'Falha de classificação: {exc}', hash_arquivo)
        classificacao_dict = classificacao.as_dict()
        self._etapa(relatorio, 'classificacao', classificacao_dict)
        if classificacao.classificacao == STATUS_REVISAO:
            return self._encaminhar_revisao(relatorio, caminho_processando, classificacao.motivo, hash_arquivo)

        try:
            if classificacao.classificacao == 'COMPARTILHADA':
                regra = self.regra_compartilhada(dados) if self.regra_compartilhada else None
                calculo = self.calculador_compartilhado.calcular({'classificacao': classificacao.classificacao, 'valor_base': dados.get('valor_base')}, regra)
            else:
                regra = self.regra_exclusiva(dados) if self.regra_exclusiva else None
                calculo = self.calculador_exclusivo.calcular({'classificacao': classificacao.classificacao, 'valor_base': dados.get('valor_base'), **dados}, regra, self.orgaos())
        except Exception as exc:
            return self._encaminhar_revisao(relatorio, caminho_processando, f'Falha de cálculo: {exc}', hash_arquivo)
        self._etapa(relatorio, 'calculo', calculo)
        if calculo.get('status') != 'CALCULADO_VALIDADO' or not calculo.get('valido'):
            return self._encaminhar_revisao(relatorio, caminho_processando, '; '.join(calculo.get('motivos_revisao', ['Cálculo não validado.'])), hash_arquivo)

        if not self._validar_total(calculo):
            return self._encaminhar_revisao(relatorio, caminho_processando, 'Validação final da soma das parcelas falhou.', hash_arquivo)
        self._etapa(relatorio, 'validacao', {'status': 'VALIDADO', 'soma': calculo.get('soma_parcelas'), 'valor_base': calculo.get('valor_base')})
        try:
            gravacao = self.integrador.gravar(dados, calculo)
        except Exception as exc:
            return self._encaminhar_erro(relatorio, caminho_processando, STATUS_ERRO_GRAVACAO, f'Falha de gravação: {exc}', hash_arquivo)
        self._etapa(relatorio, 'planilha_auditoria', gravacao)
        if gravacao.get('status') != 'GRAVADO_VALIDADO':
            if gravacao.get('status') not in {STATUS_REVISAO, 'AGUARDANDO_REVISÃO'}:
                return self._encaminhar_erro(relatorio, caminho_processando, STATUS_ERRO_GRAVACAO, '; '.join(gravacao.get('motivos_revisao', ['Erro de gravação.'])), hash_arquivo)
            return self._encaminhar_revisao(relatorio, caminho_processando, '; '.join(gravacao.get('motivos_revisao', ['Gravação não validada.'])), hash_arquivo)
        try:
            final = self.monitor.encaminhar_arquivo(caminho_processando, 'processadas', hash_arquivo)
        except Exception as exc:
            return self._finalizar(relatorio, STATUS_ERRO_GRAVACAO, str(caminho_processando), f'Falha no encaminhamento final: {exc}')
        self._etapa(relatorio, 'pasta_final', {'status': 'processadas', 'arquivo': str(final)})
        return self._finalizar(relatorio, STATUS_SUCESSO, str(final))

    def executar_pasta(self) -> Dict[str, Any]:
        resultados = [self.processar_arquivo(caminho) for caminho in self.monitor.detectar_arquivos_novos()]
        sucesso_geral = bool(resultados) and all(item['status'] == STATUS_SUCESSO for item in resultados)
        return {'status_geral': 'SUCESSO' if sucesso_geral else 'PENDENTE', 'faturas': resultados}

    def _encaminhar_revisao(self, relatorio, caminho, motivo, hash_arquivo):
        try:
            destino = self.monitor.encaminhar_arquivo(caminho, 'revisao', hash_arquivo)
            self._etapa(relatorio, 'pasta_final', {'status': 'revisao', 'arquivo': str(destino), 'motivo': motivo})
            return self._finalizar(relatorio, STATUS_REVISAO, str(destino), motivo)
        except Exception as exc:
            return self._finalizar(relatorio, STATUS_ERRO_GRAVACAO, str(caminho), f'{motivo}; falha ao mover para revisão: {exc}')

    def _encaminhar_erro(self, relatorio, caminho, status, motivo, hash_arquivo):
        try:
            destino = self.monitor.encaminhar_arquivo(caminho, 'erro', hash_arquivo)
            self._etapa(relatorio, 'pasta_final', {'status': 'erro', 'arquivo': str(destino), 'motivo': motivo})
            return self._finalizar(relatorio, status, str(destino), motivo)
        except Exception as exc:
            return self._finalizar(relatorio, STATUS_ERRO_GRAVACAO, str(caminho), f'{motivo}; falha ao mover para erro: {exc}')

    @staticmethod
    def _validar_total(calculo):
        try:
            return Decimal(str(calculo['soma_parcelas'])) == Decimal(str(calculo['valor_base']))
        except (KeyError, ArithmeticError, ValueError):
            return False

    @staticmethod
    def _etapa(relatorio, nome, resultado):
        relatorio['etapas'].append({'etapa': nome, 'status': resultado.get('status', 'CONCLUIDA') if isinstance(resultado, dict) else 'CONCLUIDA', 'resultado': resultado})

    @staticmethod
    def _finalizar(relatorio, status, arquivo, motivo=None):
        relatorio['status'] = status
        relatorio['arquivo_final'] = arquivo
        if motivo:
            relatorio['motivo'] = motivo
        relatorio['fim'] = datetime.now(timezone.utc).isoformat()
        return relatorio