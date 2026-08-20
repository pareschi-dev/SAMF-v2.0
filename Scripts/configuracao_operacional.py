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


def get_config_path() -> Path:
    return DEFAULT_CONFIG_PATH


def default_config() -> Dict[str, str]:
    return {key: "" for key in CONFIG_FIELDS}


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
    for key in CONFIG_FIELDS:
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
    for key in CONFIG_FIELDS:
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


def carregar_configuracao_do_ambiente() -> Dict[str, str]:
    return carregar_configuracao(ROOT_DIR)
