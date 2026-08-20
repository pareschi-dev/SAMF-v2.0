"""Máquina de estados para aprovação manual de mensagens de cobrança."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable


PREVIA = 'PRÉVIA'
AGUARDANDO = 'AGUARDANDO_APROVAÇÃO'
APROVADA = 'APROVADA'
REJEITADA = 'REJEITADA'
CANCELADA = 'CANCELADA'

_STATUS_NORMALIZADOS = {
    'previa': PREVIA,
    'prévia': PREVIA,
    'aguardando_aprovacao': AGUARDANDO,
    'aguardando_aprovação': AGUARDANDO,
    'aprovado': APROVADA,
    'aprovada': APROVADA,
    'rejeitado': REJEITADA,
    'rejeitada': REJEITADA,
    'cancelado': CANCELADA,
    'cancelada': CANCELADA,
}
_STATUS_ARMAZENAMENTO = {
    PREVIA: 'previa',
    AGUARDANDO: 'aguardando_aprovacao',
    APROVADA: 'aprovado',
    REJEITADA: 'falhou',
    CANCELADA: 'cancelado',
}


class ErroAprovacaoMensagem(ValueError):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem

    def as_dict(self) -> Dict[str, str]:
        return {'codigo': self.codigo, 'erro': self.mensagem}


def estado_publico(status: Any) -> str:
    return _STATUS_NORMALIZADOS.get(str(status or '').strip().lower(), str(status or '').upper())


def transicionar_mensagem(
    mensagem: Dict[str, Any],
    acao: str,
    *,
    usuario: str,
    justificativa: str = '',
    data: datetime | None = None,
    conta_pendente: bool = True,
    destinatario_ativo: bool = True,
) -> Dict[str, Any]:
    if not usuario.strip():
        raise ErroAprovacaoMensagem('usuario_obrigatorio', 'Usuário é obrigatório.')
    estado = estado_publico(mensagem.get('status'))
    acao = acao.strip().lower()
    if acao in {'rejeitar', 'alterar'} and not justificativa.strip():
        raise ErroAprovacaoMensagem('justificativa_obrigatoria', 'Justificativa é obrigatória para rejeitar ou alterar.')
    if acao == 'aprovar':
        if estado not in {PREVIA, AGUARDANDO}:
            raise ErroAprovacaoMensagem('transicao_invalida', f'Mensagem não pode ser aprovada a partir de {estado}.')
        if not conta_pendente:
            raise ErroAprovacaoMensagem('conta_nao_pendente', 'A conta não continua pendente; aprovação bloqueada.')
        if not destinatario_ativo:
            raise ErroAprovacaoMensagem('destinatario_inativo', 'O destinatário não está ativo; aprovação bloqueada.')
        novo = APROVADA
    elif acao == 'rejeitar':
        if estado not in {PREVIA, AGUARDANDO}:
            raise ErroAprovacaoMensagem('transicao_invalida', f'Mensagem não pode ser rejeitada a partir de {estado}.')
        novo = REJEITADA
    elif acao == 'alterar':
        if estado not in {PREVIA, AGUARDANDO}:
            raise ErroAprovacaoMensagem('transicao_invalida', f'Mensagem não pode ser alterada a partir de {estado}.')
        novo = PREVIA
    else:
        raise ErroAprovacaoMensagem('acao_invalida', 'Ação deve ser aprovar, rejeitar ou alterar.')
    instante = (data or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    return {
        'status': novo,
        'status_armazenamento': _STATUS_ARMAZENAMENTO[novo],
        'usuario': usuario,
        'data': instante,
        'justificativa': justificativa.strip(),
    }


def validar_lote(ids: Iterable[Any]) -> list[int]:
    resultado = []
    for valor in ids:
        try:
            resultado.append(int(valor))
        except (TypeError, ValueError) as exc:
            raise ErroAprovacaoMensagem('ids_invalidos', 'Todos os IDs das mensagens devem ser inteiros.') from exc
    if not resultado:
        raise ErroAprovacaoMensagem('lote_vazio', 'Nenhuma mensagem foi selecionada.')
    return list(dict.fromkeys(resultado))
