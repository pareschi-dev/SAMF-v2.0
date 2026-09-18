import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE_NAME = "samf_config.json"
DEFAULT_CONFIG_PATH = ROOT_DIR / "Configuracoes" / CONFIG_FILE_NAME

CONFIG_FIELDS: Dict[str, str] = {
    "entrada_path": "Pasta de entrada",
    "processamento_path": "Pasta de processamento",
    "processadas_path": "Pasta de processadas",
    "compartilhadas_path": "Pasta de compartilhadas",
    "exclusivas_path": "Pasta de exclusivas",
    "revisao_path": "Pasta de revisão",
    "duplicadas_path": "Pasta de duplicadas",
    "erro_path": "Pasta de erro",
    "planilha_oficial_path": "Caminho da planilha oficial",
    "banco_path": "Caminho do banco de dados",
    "modo_execucao": "Modo de execução",
    "intervalo_monitoramento_segundos": "Intervalo de monitoramento (segundos)",
    "tempo_estabilidade_arquivo_segundos": "Tempo de estabilidade do arquivo (segundos)",
    "limite_diferenca_arredondamento": "Limite de diferença de arredondamento",
    "backup_path": "Caminho do backup",
    "formato_exportacao": "Formato de exportação",
    "ambiente": "Ambiente (desenvolvimento ou produção)",
}

REQUIRED_FIELDS: List[str] = list(CONFIG_FIELDS.keys())
ALLOWED_MODOS = {"manual", "automatico", "agendado", "hibrido"}
ALLOWED_AMBIENTES = {"desenvolvimento", "producao"}

COBRANCAS_FIELDS: Dict[str, str] = {
    "cobrancas_planilha_oficial_path": "Caminho da planilha oficial de cobranças",
    "cobrancas_planilha_aba": "Aba da planilha de cobranças",
    "cobrancas_entrada_path": "Pasta de entrada de cobranças",
    "cobrancas_fuso_horario": "Fuso horário de cobranças",
    "cobrancas_horario_leitura": "Horário de leitura de cobranças",
    "cobrancas_horario_execucao": "Horário de execução de cobranças",
    "cobrancas_dias_semana": "Dias da semana de cobranças",
    "cobrancas_janela_silencio": "Janela de silêncio de cobranças",
    "cobrancas_dias_antecedencia": "Dias de antecedência do vencimento",
    "cobrancas_dias_vencida": "Dias para considerar uma conta vencida",
    "cobrancas_valor_minimo_aviso": "Valor mínimo para aviso",
    "cobrancas_modo_operacao": "Modo de operação de cobranças",
    "cobrancas_limite_diario_mensagens": "Limite diário de mensagens",
    "cobrancas_intervalo_minimo_mensagens": "Intervalo mínimo entre mensagens",
    "cobrancas_horario_permitido_envio": "Horário permitido para envio",
    "cobrancas_backup_path": "Caminho de backup de cobranças",
    "cobrancas_provedor_whatsapp": "Provedor de WhatsApp",
    "cobrancas_status_integracao": "Status da integração de WhatsApp",
}

COBRANCAS_REQUIRED_FIELDS: List[str] = list(COBRANCAS_FIELDS)
COBRANCAS_OPTIONAL_FIELDS: Dict[str, str] = {
    "cobrancas_mapeamento_path": "Arquivo do mapeamento ativo de cobranças",
}
COBRANCAS_MODOS = {"somente_analise", "previa", "envio_autorizado"}
COBRANCAS_STATUS_INTEGRACAO = {"pendente de configuração", "configurado", "invalido"}

WHATSAPP_FIELDS: Dict[str, str] = {
    "cobrancas_whatsapp_business_account_id": "WhatsApp Business Account ID",
    "cobrancas_whatsapp_phone_number_id": "Phone Number ID",
    "cobrancas_whatsapp_api_url": "URL da API oficial do WhatsApp",
    "cobrancas_whatsapp_api_version": "Versão da API oficial do WhatsApp",
    "cobrancas_whatsapp_template_name": "Nome do template do WhatsApp",
    "cobrancas_whatsapp_template_language": "Idioma do template do WhatsApp",
    "cobrancas_whatsapp_webhook_url": "URL do webhook do WhatsApp",
    "cobrancas_whatsapp_access_token_env": "Variável de ambiente do token de acesso",
    "cobrancas_whatsapp_webhook_verify_token_env": "Variável de ambiente do token de verificação",
    "cobrancas_whatsapp_ambiente": "Ambiente do WhatsApp (teste ou producao)",
    "cobrancas_whatsapp_modo": "Modo do adaptador do WhatsApp (simulado ou oficial)",
    "cobrancas_whatsapp_envio_real_ativo": "Envio real do WhatsApp ativo",
}


def get_config_path() -> Path:
    return DEFAULT_CONFIG_PATH


def default_config() -> Dict[str, str]:
    return {key: "" for key in {**CONFIG_FIELDS, **COBRANCAS_FIELDS, **COBRANCAS_OPTIONAL_FIELDS, **WHATSAPP_FIELDS}}


def carregar_configuracao(raiz: str | os.PathLike[str] | None = None) -> Dict[str, str]:
    base_path = Path(raiz) if raiz is not None else ROOT_DIR
    config_path = Path(base_path) / "Configuracoes" / CONFIG_FILE_NAME
    if not config_path.exists():
        return default_config()

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return default_config()

    if not isinstance(payload, dict):
        return default_config()

    normalized = default_config()
    for key in {**CONFIG_FIELDS, **COBRANCAS_FIELDS, **COBRANCAS_OPTIONAL_FIELDS, **WHATSAPP_FIELDS}:
        if key in payload:
            value = payload.get(key)
            if value is None:
                normalized[key] = ""
            elif isinstance(value, str):
                normalized[key] = value.strip()
            else:
                normalized[key] = str(value).strip()
    return normalized


def salvar_configuracao(config: Dict[str, Any], raiz: str | os.PathLike[str] | None = None) -> Dict[str, str]:
    base_path = Path(raiz) if raiz is not None else ROOT_DIR
    config_path = Path(base_path) / "Configuracoes" / CONFIG_FILE_NAME
    config_path.parent.mkdir(parents=True, exist_ok=True)

    payload = default_config()
    for key in {**CONFIG_FIELDS, **COBRANCAS_FIELDS, **COBRANCAS_OPTIONAL_FIELDS, **WHATSAPP_FIELDS}:
        value = config.get(key)
        payload[key] = "" if value is None else str(value).strip()

    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    return payload


def _valor_obrigatorio(valor: Any) -> bool:
    if valor is None:
        return False
    return str(valor).strip() != ""


def validar_configuracao(config: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(config, dict):
        return False, "Configuração obrigatória pendente: estrutura inválida."

    faltantes = []
    for chave in REQUIRED_FIELDS:
        if not _valor_obrigatorio(config.get(chave)):
            faltantes.append(CONFIG_FIELDS[chave])

    if faltantes:
        return False, "Configuração obrigatória pendente: " + "; ".join(faltantes) + "."

    modo = str(config.get("modo_execucao", "")).strip().lower()
    if modo not in ALLOWED_MODOS:
        return False, "Modo de execução obrigatório inválido. Use manual, automatico, agendado ou hibrido."

    ambiente = str(config.get("ambiente", "")).strip().lower()
    if ambiente not in ALLOWED_AMBIENTES:
        return False, "Ambiente obrigatório inválido. Use desenvolvimento ou producao."

    numericos = [
        "intervalo_monitoramento_segundos",
        "tempo_estabilidade_arquivo_segundos",
        "limite_diferenca_arredondamento",
    ]
    for chave in numericos:
        try:
            float(config.get(chave, ""))
        except (TypeError, ValueError):
            return False, f"Campo obrigatório inválido: {CONFIG_FIELDS[chave]}."

    return True, "Configuração válida."


def validar_configuracao_cobrancas(config: Dict[str, Any]) -> Tuple[bool, str]:
    """Valida somente a configuração da área de cobranças, sem acessar arquivos."""
    if not isinstance(config, dict):
        return False, "Configuração de cobranças obrigatória pendente: estrutura inválida."

    faltantes = [
        COBRANCAS_FIELDS[chave]
        for chave in COBRANCAS_REQUIRED_FIELDS
        if not _valor_obrigatorio(config.get(chave))
    ]
    if faltantes:
        return False, "Configuração de cobranças obrigatória pendente: " + "; ".join(faltantes) + "."

    modo = str(config.get("cobrancas_modo_operacao", "")).strip().lower()
    if modo not in COBRANCAS_MODOS:
        return False, "Modo de operação de cobranças inválido. Use somente_analise, previa ou envio_autorizado."

    status_integracao = str(config.get("cobrancas_status_integracao", "")).strip().lower()
    if status_integracao not in COBRANCAS_STATUS_INTEGRACAO:
        return False, "Status da integração de WhatsApp inválido."
    if modo == "envio_autorizado" and status_integracao != "configurado":
        return False, "Envio autorizado bloqueado: integração oficial do WhatsApp não configurada."

    for chave, label in (
        ("cobrancas_dias_antecedencia", "Dias de antecedência do vencimento"),
        ("cobrancas_dias_vencida", "Dias para considerar uma conta vencida"),
        ("cobrancas_limite_diario_mensagens", "Limite diário de mensagens"),
        ("cobrancas_intervalo_minimo_mensagens", "Intervalo mínimo entre mensagens"),
    ):
        try:
            if float(config[chave]) < 0:
                raise ValueError
        except (TypeError, ValueError):
            return False, f"Campo de cobranças inválido: {label}."

    try:
        if float(config["cobrancas_valor_minimo_aviso"].replace(",", ".")) < 0:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        return False, "Campo de cobranças inválido: Valor mínimo para aviso."

    for chave, label in (
        ("cobrancas_horario_leitura", "Horário de leitura de cobranças"),
        ("cobrancas_horario_permitido_envio", "Horário permitido para envio"),
    ):
        horarios = str(config[chave]).split("-")
        if len(horarios) != 2 or any(
            len(parte.strip().split(":")) != 2
            or not all(item.isdigit() for item in parte.strip().split(":"))
            or int(parte.strip().split(":")[0]) > 23
            or int(parte.strip().split(":")[1]) > 59
            for parte in horarios
        ):
            return False, f"Campo de cobranças inválido: {label}. Use HH:MM-HH:MM."

    return True, "Configuração de cobranças válida."


def carregar_configuracao_do_ambiente() -> Dict[str, str]:
    return carregar_configuracao(ROOT_DIR)
