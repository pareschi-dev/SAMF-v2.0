"""
SAMF v2.0 - Motor de Classificação Profissional
Lógica para classificar despesas como compartilhado, exclusivo ou aguardando revisão
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class FaturaExtraida:
    """Dados extraídos de uma fatura PDF"""
    nome_arquivo: str
    fornecedor: str
    servico: str
    numero: Optional[str] = None
    descricao: Optional[str] = None
    competencia: Optional[str] = None
    valor: Optional[float] = None
    endereco: Optional[str] = None
    unidade: Optional[str] = None
    orgao_original: Optional[str] = None
    complemento: Optional[str] = None
    secao: Optional[str] = None


@dataclass
class ResultadoClassificacao:
    """Resultado da classificação de uma fatura"""
    classificacao: str  # 'COMPARTILHADA', 'EXCLUSIVA', 'AGUARDANDO_REVISÃO'
    confianca: float  # 0.0 a 1.0
    motivo: str
    orgao_beneficiario: Optional[str] = None
    evidencias: Optional[List[str]] = None
    regra_aplicada: Optional[str] = None
    requer_intervencao: bool = False
    possiveis_alternativas: Optional[List[str]] = None
    motivo_revisao: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            'classificacao': self.classificacao,
            'confianca': self.confianca,
            'evidencias': self.evidencias or [],
            'regra_utilizada': self.regra_aplicada,
            'possiveis_alternativas': self.possiveis_alternativas or [],
            'motivo': self.motivo,
            'motivo_revisao': self.motivo_revisao,
            'orgao_beneficiario': self.orgao_beneficiario,
            'requer_intervencao': self.requer_intervencao,
        }


class ClassificadorFaturas:
    """
    Classifica faturas como compartilhado, exclusivo ou revisão
    baseado nas regras oficiais de rateio
    """

    REGRAS = (
        ('CESAN edifício-sede', 'COMPARTILHADA', 'CESAN', ('água e esgoto',), ('edifício-sede', 'ed sede', 'ed. sede'), 'SERVIÇOS DESPESAS COMPARTILHADAS'),
        ('CESAN estacionamento', 'EXCLUSIVA', 'CESAN', ('água e esgoto',), ('estacionamento',), 'SERVIÇOS EXCLUSIVOS'),
        ('AJP edifício-sede', 'COMPARTILHADA', 'AJP', ('dedetização',), ('edifício-sede', 'ed sede', 'ed. sede'), 'SERVIÇOS DESPESAS COMPARTILHADAS'),
        ('AJP Princesa Isabel', 'EXCLUSIVA', 'AJP', ('dedetização',), ('princesa isabel',), 'SERVIÇOS EXCLUSIVOS'),
        ('EDP edifício-sede', 'COMPARTILHADA', 'EDP', ('energia elétrica',), ('edifício-sede', 'ed sede', 'ed. sede'), 'SERVIÇOS DESPESAS COMPARTILHADAS'),
        ('EDP Princesa Isabel', 'EXCLUSIVA', 'EDP', ('energia elétrica',), ('princesa isabel',), 'SERVIÇOS EXCLUSIVOS'),
        ('SUDESTE serviço de limpeza', 'COMPARTILHADA', 'SUDESTE', ('serviço de limpeza',), (), 'SERVIÇOS DESPESAS COMPARTILHADAS'),
        ('SUDESTE limpeza e higienização', 'EXCLUSIVA', 'SUDESTE', ('limpeza e higienização',), (), 'SERVIÇOS EXCLUSIVOS'),
        ('MÁXIMA telefonista', 'COMPARTILHADA', 'MÁXIMA', ('telefonista',), (), 'SERVIÇOS DESPESAS COMPARTILHADAS'),
        ('MÁXIMA auxiliar administrativo por cidade', 'EXCLUSIVA', 'MÁXIMA', ('auxiliar administrativo',), ('vitória', 'cachoeiro', 'colatina', 'vila velha'), 'SERVIÇOS EXCLUSIVOS'),
        ('VIVO FIXO compartilhado', 'COMPARTILHADA', 'VIVO', ('telefonia fixa', 'vivo fixo'), ('fixo',), 'SERVIÇOS DESPESAS COMPARTILHADAS'),
        ('VIVO FIXO - PABX', 'EXCLUSIVA', 'VIVO', ('telefonia', 'vivo fixo'), ('pabx',), 'SERVIÇOS EXCLUSIVOS'),
    )

    def classificar(self, fatura: FaturaExtraida) -> ResultadoClassificacao:
        """Classifica somente quando uma regra oficial possui evidência suficiente."""
        fornecedor = self._normalizar_texto(fatura.fornecedor)
        servico = self._normalizar_texto(fatura.servico)
        complemento = self._normalizar_texto(fatura.complemento)
        unidade = self._normalizar_texto(fatura.unidade)
        endereco = self._normalizar_texto(fatura.endereco)
        descricao = self._normalizar_texto(fatura.descricao)
        orgao = self._normalizar_texto(fatura.orgao_original)
        secao = self._normalizar_texto(fatura.secao)
        contexto = ' '.join(filter(None, (complemento, unidade, endereco, descricao, orgao, fornecedor, servico)))
        evidencias_base = [f'Fornecedor: {fornecedor or "NAO_ENCONTRADO"}', f'Serviço: {servico or "NAO_ENCONTRADO"}', f'Complemento/unidade/endereço: {contexto or "NAO_ENCONTRADO"}', f'Seção: {secao or "NAO_ENCONTRADA"}']

        if not fornecedor or not servico or not secao:
            return self._revisao('Ausência de fornecedor, serviço ou seção da planilha.', evidencias_base, ['COMPARTILHADA', 'EXCLUSIVA'], 0.10)

        candidatos = [regra for regra in self.REGRAS if self._regra_compativel(regra, fornecedor, servico, contexto, secao)]
        if len(candidatos) != 1:
            alternativas = sorted({regra[1] for regra in self.REGRAS if self._fornecedor_compativel(regra[2], fornecedor) and self._servico_compativel(regra[3], servico)})
            motivo = 'Ausência de evidência suficiente para decidir.' if not candidatos else 'Mais de uma regra oficial é compatível com os dados informados.'
            return self._revisao(motivo, evidencias_base, alternativas or ['COMPARTILHADA', 'EXCLUSIVA'], 0.40 if candidatos else 0.20)

        nome, classificacao, _, _, indicadores, _ = candidatos[0]
        evidencias = evidencias_base + [f'Indicador encontrado: {indicadores or "combinação de serviço e seção"}']
        return ResultadoClassificacao(classificacao, 0.95, f'Regra oficial confirmada: {nome}.', fatura.orgao_original if classificacao == 'EXCLUSIVA' else None, evidencias, nome, False, [], None)

    def _revisao(self, motivo: str, evidencias: List[str], alternativas: List[str], confianca: float) -> ResultadoClassificacao:
        return ResultadoClassificacao('AGUARDANDO_REVISÃO', confianca, motivo, evidencias=evidencias, regra_aplicada=None, requer_intervencao=True, possiveis_alternativas=alternativas, motivo_revisao=motivo)

    @classmethod
    def _regra_compativel(cls, regra, fornecedor: str, servico: str, contexto: str, secao: str) -> bool:
        _, _, fornecedor_regra, servicos, indicadores, secao_regra = regra
        if regra[0] == 'VIVO FIXO compartilhado' and 'PABX' in contexto:
            return False
        contexto_normalizado = cls._normalizar_texto(contexto)
        return (cls._fornecedor_compativel(fornecedor_regra, fornecedor)
                and cls._servico_compativel(servicos, servico)
                and cls._normalizar_texto(secao_regra) == secao
                and (not indicadores or any(cls._normalizar_texto(indicador) in contexto_normalizado for indicador in indicadores)))

    @classmethod
    def _fornecedor_compativel(cls, regra: str, valor: str) -> bool:
        regra_normalizada = cls._normalizar_texto(regra)
        valor_normalizado = cls._normalizar_texto(valor)
        return regra_normalizada in valor_normalizado or (regra_normalizada == 'VIVO' and 'VIVO' in valor_normalizado)

    @classmethod
    def _servico_compativel(cls, regras, valor: str) -> bool:
        valor_normalizado = cls._normalizar_texto(valor)
        return any(cls._normalizar_texto(regra) == valor_normalizado or cls._normalizar_texto(regra) in valor_normalizado for regra in regras)

    @staticmethod
    def _normalizar_texto(texto: str) -> str:
        if not texto:
            return ""
        texto = unicodedata.normalize('NFKD', texto)
        texto = texto.encode('ascii', 'ignore').decode('ascii')
        texto = texto.strip().upper()
        texto = re.sub(r'\s+', ' ', texto)
        return texto


