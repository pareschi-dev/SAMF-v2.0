"""Adaptador seguro e sem rede para a WhatsApp Business Platform oficial."""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict


STATUS_NAO_CONFIGURADO = 'nao_configurado'
STATUS_INCOMPLETO = 'incompleto'
STATUS_INVALIDO = 'invalido'
STATUS_TESTE_APROVADO = 'teste_aprovado'
STATUS_PRODUCAO_BLOQUEADA = 'producao_bloqueada'


class ErroWhatsAppBusiness(ValueError):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def _texto(config: Dict[str, Any], chave: str) -> str:
    return str(config.get(chave) or '').strip()


def _segredo(config: Dict[str, Any], chave: str, loader: Callable[[str], str | None]) -> str:
    nome_variavel = _texto(config, chave)
    return str(loader(nome_variavel) or '').strip() if nome_variavel else ''


def _config_publica(config: Dict[str, Any]) -> Dict[str, Any]:
    campos = (
        'cobrancas_whatsapp_business_account_id', 'cobrancas_whatsapp_phone_number_id',
        'cobrancas_whatsapp_api_url', 'cobrancas_whatsapp_api_version',
        'cobrancas_whatsapp_template_name', 'cobrancas_whatsapp_template_language',
        'cobrancas_whatsapp_webhook_url', 'cobrancas_whatsapp_access_token_env',
        'cobrancas_whatsapp_webhook_verify_token_env', 'cobrancas_whatsapp_ambiente',
        'cobrancas_whatsapp_modo', 'cobrancas_whatsapp_envio_real_ativo',
    )
    return {campo: config.get(campo, '') for campo in campos}


def configuracao_auditoria(config: Dict[str, Any]) -> Dict[str, Any]:
    """Retorna somente campos não relacionados a segredos para auditoria."""
    return {
        chave: valor for chave, valor in _config_publica(config).items()
        if chave not in {
            'cobrancas_whatsapp_access_token_env',
            'cobrancas_whatsapp_webhook_verify_token_env',
        }
    }


def validar_configuracao_whatsapp(
    config: Dict[str, Any],
    *,
    secret_loader: Callable[[str], str | None] | None = None,
) -> Dict[str, Any]:
    """Valida configuração sem rede e nunca retorna valores secretos."""
    publica = _config_publica(config)
    preenchidos = any(str(valor or '').strip() for valor in publica.values())
    if not preenchidos:
        return {'status': STATUS_NAO_CONFIGURADO, 'configuracao': publica}

    obrigatorios = (
        'cobrancas_whatsapp_business_account_id', 'cobrancas_whatsapp_phone_number_id',
        'cobrancas_whatsapp_api_url', 'cobrancas_whatsapp_api_version',
        'cobrancas_whatsapp_template_name', 'cobrancas_whatsapp_template_language',
        'cobrancas_whatsapp_webhook_url', 'cobrancas_whatsapp_access_token_env',
        'cobrancas_whatsapp_webhook_verify_token_env', 'cobrancas_whatsapp_ambiente',
        'cobrancas_whatsapp_modo',
    )
    faltantes = [campo for campo in obrigatorios if not _texto(config, campo)]
    if faltantes:
        return {'status': STATUS_INCOMPLETO, 'faltantes': faltantes, 'configuracao': publica}

    if not _texto(config, 'cobrancas_whatsapp_business_account_id').isdigit() or not _texto(config, 'cobrancas_whatsapp_phone_number_id').isdigit():
        return {'status': STATUS_INVALIDO, 'erro': 'IDs da conta e do telefone devem conter somente dígitos.', 'configuracao': publica}
    if not re.fullmatch(r'https://[^\s]+', _texto(config, 'cobrancas_whatsapp_api_url')):
        return {'status': STATUS_INVALIDO, 'erro': 'A URL da API oficial deve usar HTTPS.', 'configuracao': publica}
    if _texto(config, 'cobrancas_whatsapp_ambiente') not in {'teste', 'producao'}:
        return {'status': STATUS_INVALIDO, 'erro': 'Ambiente deve ser teste ou producao.', 'configuracao': publica}
    if _texto(config, 'cobrancas_whatsapp_modo') not in {'simulado', 'oficial'}:
        return {'status': STATUS_INVALIDO, 'erro': 'Modo deve ser simulado ou oficial.', 'configuracao': publica}
    if _texto(config, 'cobrancas_whatsapp_envio_real_ativo').lower() in {'1', 'true', 'sim', 'yes'}:
        return {'status': STATUS_PRODUCAO_BLOQUEADA, 'erro': 'Envio real permanece bloqueado nesta etapa.', 'configuracao': publica}
    if secret_loader is None:
        secret_loader = os.environ.get
    if not _segredo(config, 'cobrancas_whatsapp_access_token_env', secret_loader):
        return {'status': STATUS_INCOMPLETO, 'faltantes': ['token_de_acesso'], 'configuracao': publica}
    if not _segredo(config, 'cobrancas_whatsapp_webhook_verify_token_env', secret_loader):
        return {'status': STATUS_INCOMPLETO, 'faltantes': ['token_verificacao_webhook'], 'configuracao': publica}
    return {'status': STATUS_TESTE_APROVADO, 'configuracao': publica}


class WhatsAppBusinessAdapter:
    """Adaptador de configuração/teste; não possui transporte HTTP."""

    def __init__(self, config: Dict[str, Any], *, secret_loader=None, simulated_credential=True):
        self.config = config
        self.secret_loader = secret_loader or os.environ.get
        self.simulated_credential = simulated_credential

    def testar_conexao(self) -> Dict[str, Any]:
        resultado = validar_configuracao_whatsapp(self.config, secret_loader=self.secret_loader)
        if resultado['status'] != STATUS_TESTE_APROVADO:
            return resultado
        if _texto(self.config, 'cobrancas_whatsapp_modo') != 'simulado':
            return {'status': STATUS_PRODUCAO_BLOQUEADA, 'erro': 'Teste oficial externo não é executado nesta etapa.'}
        if not self.simulated_credential:
            return {'status': STATUS_INVALIDO, 'erro': 'Credencial simulada inválida.'}
        return {'status': STATUS_TESTE_APROVADO, 'modo': 'simulado', 'externo_chamado': False}

    def montar_mensagem(self, template_variables: Dict[str, Any]) -> Dict[str, Any]:
        validacao = validar_configuracao_whatsapp(self.config, secret_loader=self.secret_loader)
        if validacao['status'] not in {STATUS_TESTE_APROVADO, STATUS_PRODUCAO_BLOQUEADA}:
            raise ErroWhatsAppBusiness('configuracao_invalida', 'Configuração não permite montar a mensagem.')
        return {
            'template': _texto(self.config, 'cobrancas_whatsapp_template_name'),
            'idioma': _texto(self.config, 'cobrancas_whatsapp_template_language'),
            'variaveis': dict(template_variables),
        }

    def enviar(self, telefone: str, mensagem: Dict[str, Any]) -> Dict[str, Any]:
        raise ErroWhatsAppBusiness('envio_bloqueado', 'Envio real bloqueado; nenhum provedor externo foi chamado.')