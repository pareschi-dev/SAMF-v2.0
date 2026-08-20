"""Envio controlado de mensagens aprovadas, com modo de teste sem rede."""

from __future__ import annotations

import os
import re
from datetime import datetime, time, timezone
from typing import Any, Dict, Protocol


class ProvedorWhatsApp(Protocol):
    def testar_credencial(self) -> Dict[str, Any]: ...
    def enviar(self, telefone: str, texto: str) -> Dict[str, Any]: ...
    def consultar(self, identificador_externo: str) -> Dict[str, Any]: ...
    def cancelar(self, identificador_externo: str) -> Dict[str, Any]: ...


class ErroEnvioCobranca(ValueError):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem

    def as_dict(self) -> Dict[str, str]:
        return {'codigo': self.codigo, 'erro': self.mensagem}


class ProvedorNaoConfigurado:
    def testar_credencial(self): return {'configurado': False, 'erro': 'Provedor WhatsApp não configurado.'}
    def enviar(self, telefone, texto): raise ErroEnvioCobranca('provedor_nao_configurado', 'Envio real bloqueado: provedor não configurado.')
    def consultar(self, identificador_externo): raise ErroEnvioCobranca('provedor_nao_configurado', 'Provedor não configurado.')
    def cancelar(self, identificador_externo): raise ErroEnvioCobranca('provedor_nao_configurado', 'Provedor não configurado.')


class ServicoEnvioCobranca:
    def __init__(self, config: Dict[str, Any], provedor: ProvedorWhatsApp | None = None, agora=None):
        self.config = config
        self.provedor = provedor or ProvedorNaoConfigurado()
        self.agora = agora or (lambda: datetime.now(timezone.utc))

    def verificar_configuracao(self) -> Dict[str, Any]:
        provedor = str(self.config.get('cobrancas_provedor_whatsapp') or '').strip()
        status = str(self.config.get('cobrancas_status_integracao') or '').strip().lower()
        modo = str(self.config.get('cobrancas_modo_operacao') or '').strip().lower()
        configurado = bool(provedor and status == 'configurado')
        return {'configurado': configurado, 'provedor': provedor or None, 'status': status or 'pendente de configuração', 'modo': modo or 'somente_analise'}

    def testar_credencial(self) -> Dict[str, Any]:
        if not self.verificar_configuracao()['configurado']:
            return {'configurado': False, 'erro': 'Provedor WhatsApp não configurado.'}
        return self.provedor.testar_credencial()

    def enviar_aprovada(self, mensagem: Dict[str, Any], conta: Dict[str, Any], destinatario: Dict[str, Any], regra: Dict[str, Any], *, contagem_diaria: int = 0, ultima_mensagem_em: datetime | None = None, duplicada: bool = False) -> Dict[str, Any]:
        self._validar_pre_envio(mensagem, conta, destinatario, regra, contagem_diaria, ultima_mensagem_em, duplicada)
        instante = self.agora().astimezone(timezone.utc).isoformat()
        if str(self.config.get('cobrancas_modo_operacao') or '').strip().lower() == 'somente_analise' or str(self.config.get('cobrancas_modo_operacao') or '').strip().lower() == 'previa':
            return {'status': 'simulacao', 'tentativa': 0, 'data': instante, 'identificador_externo': None, 'resposta_provedor': None, 'erro': None}
        if not self.verificar_configuracao()['configurado']:
            return {'status': 'bloqueado', 'tentativa': 0, 'data': instante, 'identificador_externo': None, 'resposta_provedor': None, 'erro': 'Provedor WhatsApp não configurado.'}
        try:
            resposta = self.provedor.enviar(str(destinatario['telefone']), str(mensagem['texto']))
            return {'status': 'enviado', 'tentativa': 1, 'data': instante, 'identificador_externo': resposta.get('id') or resposta.get('message_id'), 'resposta_provedor': resposta, 'erro': None}
        except Exception as exc:
            return {'status': 'falhou', 'tentativa': 1, 'data': instante, 'identificador_externo': None, 'resposta_provedor': None, 'erro': str(exc)}

    def consultar_resposta(self, identificador_externo: str) -> Dict[str, Any]:
        if not identificador_externo:
            raise ErroEnvioCobranca('identificador_ausente', 'Identificador externo obrigatório.')
        return self.provedor.consultar(identificador_externo)

    def cancelar_pendente(self, identificador_externo: str) -> Dict[str, Any]:
        if not identificador_externo:
            raise ErroEnvioCobranca('identificador_ausente', 'Identificador externo obrigatório.')
        return self.provedor.cancelar(identificador_externo)

    def _validar_pre_envio(self, mensagem, conta, destinatario, regra, contagem_diaria, ultima_mensagem_em, duplicada):
        if str(mensagem.get('status') or '').upper() not in {'APROVADA', 'APROVADO'}:
            raise ErroEnvioCobranca('mensagem_nao_aprovada', 'Somente mensagens aprovadas podem ser enviadas.')
        if not _pendente(conta): raise ErroEnvioCobranca('conta_nao_pendente', 'Conta não está pendente.')
        if str(conta.get('status') or '').upper() == 'PAGA': raise ErroEnvioCobranca('conta_paga', 'Conta paga não pode ser enviada.')
        if not destinatario.get('ativo'): raise ErroEnvioCobranca('destinatario_inativo', 'Destinatário inativo.')
        telefone = str(destinatario.get('telefone') or '')
        if len(re.sub(r'\D', '', telefone)) < 10: raise ErroEnvioCobranca('telefone_invalido', 'Telefone inválido.')
        if not destinatario.get('autorizacao_registrada'): raise ErroEnvioCobranca('sem_autorizacao', 'Destinatário sem autorização.')
        if not regra.get('ativa'): raise ErroEnvioCobranca('regra_inativa', 'Regra de cobrança inativa.')
        if int(contagem_diaria) >= int(regra.get('limite_diario') or 0): raise ErroEnvioCobranca('limite_diario', 'Limite diário de mensagens atingido.')
        if not _horario_permitido(self.agora(), regra.get('horario_permitido')): raise ErroEnvioCobranca('fora_do_horario', 'Horário permitido para envio não está vigente.')
        if ultima_mensagem_em and (self.agora() - ultima_mensagem_em).total_seconds() < int(regra.get('intervalo_minimo_segundos') or 0): raise ErroEnvioCobranca('intervalo_minimo', 'Intervalo mínimo entre mensagens não foi atingido.')
        if duplicada: raise ErroEnvioCobranca('mensagem_duplicada', 'Mensagem igual já foi enviada no intervalo definido.')


def _pendente(conta):
    try: return float(conta.get('valor_pendente')) > 0
    except (TypeError, ValueError): return False


def _horario_permitido(agora, faixa):
    if not faixa: return False
    try:
        inicio, fim = [time.fromisoformat(item.strip()) for item in str(faixa).split('-', 1)]
        atual = agora.astimezone(timezone.utc).time().replace(tzinfo=None)
        return inicio <= atual <= fim if inicio <= fim else atual >= inicio or atual <= fim
    except ValueError: return False
