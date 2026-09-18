"""Geração de prévias de cobrança sem persistência ou envio."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict


VARIAVEIS = (
    'nome_destinatario', 'orgao', 'unidade', 'servico', 'fornecedor',
    'competencia', 'valor_pendente', 'data_vencimento', 'dias_restantes',
    'dias_em_atraso',
)
PLACEHOLDER = re.compile(r'{{\s*([a-z_]+)\s*}}')


class ErroPreviaCobranca(ValueError):
    def __init__(self, codigo: str, mensagem: str, campos_faltantes: list[str] | None = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.campos_faltantes = campos_faltantes or []

    def as_dict(self) -> Dict[str, Any]:
        return {'codigo': self.codigo, 'mensagem': self.mensagem, 'campos_faltantes': self.campos_faltantes}


def gerar_previa_cobranca(
    conta: Dict[str, Any],
    destinatario: Dict[str, Any],
    regra: Dict[str, Any],
    *,
    data_atual: date | datetime,
) -> Dict[str, Any]:
    status = _normalizar_status(conta.get('status'))
    if status == 'PAGA':
        raise ErroPreviaCobranca('conta_paga', 'Conta paga não pode gerar prévia de cobrança.')
    if status not in {'PROXIMA_DO_VENCIMENTO', 'VENCIDA'}:
        raise ErroPreviaCobranca('conta_nao_elegivel', f'Conta não elegível para cobrança: {status or "sem status"}.')
    if status == 'PROXIMA_DO_VENCIMENTO' and not _verdadeiro(regra.get('cobrar_proximas')):
        raise ErroPreviaCobranca('regra_nao_aplicavel', 'A regra não está habilitada para contas próximas do vencimento.')
    if status == 'VENCIDA' and not _verdadeiro(regra.get('cobrar_vencidas')):
        raise ErroPreviaCobranca('regra_nao_aplicavel', 'A regra não está habilitada para contas vencidas.')

    telefone = str(destinatario.get('telefone') or '').strip()
    if not telefone:
        raise ErroPreviaCobranca('telefone_ausente', 'Telefone do destinatário ausente.', ['telefone'])
    if not _verdadeiro(destinatario.get('autorizacao_registrada')):
        raise ErroPreviaCobranca('destinatario_nao_autorizado', 'Destinatário sem autorização registrada.', ['autorizacao_registrada'])
    modelo = str(regra.get('modelo_mensagem') or '')
    if not modelo.strip():
        raise ErroPreviaCobranca('modelo_ausente', 'Modelo de mensagem ausente.', ['modelo_mensagem'])

    vencimento = _data(conta.get('data_vencimento'))
    valor = _valor(conta.get('valor_pendente'))
    obrigatorios = {
        'nome_destinatario': destinatario.get('nome'),
        'orgao': conta.get('orgao'),
        'unidade': conta.get('unidade'),
        'servico': conta.get('servico'),
        'fornecedor': conta.get('fornecedor'),
        'competencia': conta.get('competencia'),
        'valor_pendente': valor,
        'data_vencimento': vencimento,
    }
    faltantes = [campo for campo, valor_campo in obrigatorios.items() if valor_campo in (None, '')]
    placeholders = set(PLACEHOLDER.findall(modelo))
    desconhecidas = sorted(placeholders - set(VARIAVEIS))
    if desconhecidas:
        raise ErroPreviaCobranca('variavel_desconhecida', 'Modelo contém variáveis não permitidas: ' + ', '.join(desconhecidas), desconhecidas)
    variaveis_ausentes_modelo = sorted(set(VARIAVEIS) - placeholders)
    if variaveis_ausentes_modelo:
        raise ErroPreviaCobranca(
            'variavel_ausente_modelo',
            'Modelo não contém as variáveis obrigatórias: ' + ', '.join(variaveis_ausentes_modelo) + '.',
            variaveis_ausentes_modelo,
        )
    faltantes.extend(sorted(placeholders & set(VARIAVEIS) - set(obrigatorios) - {'dias_restantes', 'dias_em_atraso'}))
    if faltantes:
        raise ErroPreviaCobranca('variavel_ausente', 'Prévia bloqueada; campos obrigatórios ausentes: ' + ', '.join(sorted(set(faltantes))) + '.', sorted(set(faltantes)))

    hoje = data_atual.date() if isinstance(data_atual, datetime) else data_atual
    dias = (vencimento - hoje).days
    valores = {
        'nome_destinatario': destinatario['nome'], 'orgao': conta['orgao'], 'unidade': conta['unidade'],
        'servico': conta['servico'], 'fornecedor': conta['fornecedor'], 'competencia': conta['competencia'],
        'valor_pendente': _formatar_valor(valor), 'data_vencimento': _formatar_data(vencimento),
        'dias_restantes': str(max(0, dias)), 'dias_em_atraso': str(max(0, -dias)),
    }
    texto = PLACEHOLDER.sub(lambda match: valores[match.group(1)], modelo)
    return {
        'status': 'previa', 'destinatario': destinatario['nome'], 'telefone_mascarado': _mascarar_telefone(telefone),
        'orgao': conta['orgao'], 'unidade': conta['unidade'], 'servico': conta['servico'],
        'fornecedor': conta['fornecedor'], 'competencia': conta['competencia'], 'valor_pendente': valor,
        'vencimento': _formatar_data(vencimento), 'dias_restantes': max(0, dias), 'dias_em_atraso': max(0, -dias),
        'regra_utilizada': regra.get('nome'), 'texto': texto,
    }


def _normalizar_status(valor: Any) -> str:
    return str(valor or '').upper().replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')


def _verdadeiro(valor: Any) -> bool:
    return valor in (True, 1, '1', 'true', 'True')


def _data(valor: Any) -> date | None:
    if isinstance(valor, datetime): return valor.date()
    if isinstance(valor, date): return valor
    for formato in ('%Y-%m-%d', '%d/%m/%Y'):
        try: return datetime.strptime(str(valor or '').strip(), formato).date()
        except ValueError: pass
    return None


def _valor(valor: Any) -> Decimal | None:
    try:
        texto = str(valor or '').replace('R$', '').replace(' ', '')
        if ',' in texto: texto = texto.replace('.', '').replace(',', '.')
        resultado = Decimal(texto)
        return resultado if resultado.is_finite() else None
    except (InvalidOperation, ValueError): return None


def _formatar_valor(valor: Decimal) -> str:
    return f'R$ {valor:.2f}'.replace('.', ',')


def _formatar_data(valor: date) -> str:
    return valor.strftime('%d/%m/%Y')


def _mascarar_telefone(telefone: str) -> str:
    digitos = ''.join(char for char in telefone if char.isdigit())
    if len(digitos) <= 4: return '*' * len(digitos)
    return '*' * (len(digitos) - 4) + digitos[-4:]
