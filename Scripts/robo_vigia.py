"""Monitor seguro da pasta de entrada.

Este módulo somente controla arquivos e estados do monitor. Ele não lê faturas,
classifica despesas, calcula rateios ou altera a planilha oficial.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional


DESTINOS = {
    'processando': 'processamento_path',
    'processadas': 'processadas_path',
    'revisao': 'revisao_path',
    'duplicadas': 'duplicadas_path',
    'erro': 'erro_path',
}

SUFIXOS_TEMPORARIOS = {'.tmp', '.part', '.crdownload', '.download', '.swp'}
PREFIXOS_TEMPORARIOS = ('~$', '~', '.')


class MonitorPasta:
    """Detecta, reserva, identifica e movimenta arquivos sem processar conteúdo."""

    _locks: Dict[str, threading.Lock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, config: Dict[str, str], connection_factory: Optional[Callable[[], sqlite3.Connection]] = None, sleep: Callable[[float], None] = time.sleep) -> None:
        self.config = config
        self.connection_factory = connection_factory
        self.sleep = sleep
        self._garantir_pastas()

    def verificar_pasta(self) -> Path:
        entrada = self._caminho('entrada_path')
        if not entrada.exists() or not entrada.is_dir():
            raise FileNotFoundError(f'Pasta de entrada não encontrada: {entrada}')
        return entrada

    def detectar_arquivos_novos(self) -> Iterable[Path]:
        entrada = self.verificar_pasta()
        return sorted(path for path in entrada.iterdir() if path.is_file() and not self.eh_temporario(path))

    @staticmethod
    def eh_temporario(path: Path) -> bool:
        nome = path.name.lower()
        return nome.endswith(tuple(SUFIXOS_TEMPORARIOS)) or any(path.name.startswith(prefixo) for prefixo in PREFIXOS_TEMPORARIOS)

    def arquivo_estavel(self, path: Path, verificacoes: int = 2) -> bool:
        """Exige tamanho e mtime iguais em leituras consecutivas."""
        intervalo = max(0.0, float(self.config.get('tempo_estabilidade_arquivo_segundos', 1) or 1))
        anterior = None
        for tentativa in range(max(2, verificacoes)):
            try:
                atual = (path.stat().st_size, path.stat().st_mtime_ns)
            except (FileNotFoundError, OSError):
                return False
            if atual == anterior:
                return True
            anterior = atual
            if tentativa < verificacoes - 1:
                self.sleep(intervalo)
        return False

    def calcular_hash(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open('rb') as arquivo:
            for bloco in iter(lambda: arquivo.read(1024 * 1024), b''):
                digest.update(bloco)
        return digest.hexdigest()

    def monitorar_arquivo(self, path: Path) -> Dict[str, str]:
        """Move um novo arquivo para processamento, sem executar processamento."""
        path = Path(path)
        if self.eh_temporario(path):
            self._registrar('ignorado_temporario', f'Arquivo temporário ignorado: {path.name}')
            return {'status': 'ignorado_temporario', 'arquivo': str(path)}
        if not path.exists() or not path.is_file():
            return self._erro(path, 'Arquivo inválido ou inexistente.')
        if path.suffix.lower() != '.pdf':
            return self._erro(path, 'Arquivo inválido: somente arquivos PDF são aceitos.')

        lock = self._obter_lock(path)
        if not lock.acquire(blocking=False):
            self._registrar('ignorado_em_execucao', f'Arquivo já está em execução: {path.name}')
            return {'status': 'em_execucao', 'arquivo': str(path)}

        try:
            self._registrar('inicio_monitoramento', f'Início do monitoramento: {path.name}')
            if not self.arquivo_estavel(path):
                return self._erro(path, 'Arquivo ainda não está estável.')

            hash_arquivo = self.calcular_hash(path)
            if self._hash_duplicado(hash_arquivo):
                destino = self.encaminhar_arquivo(path, 'duplicadas', hash_arquivo)
                self._registrar('fim_monitoramento', f'Arquivo duplicado encaminhado: {destino.name}', hash_arquivo)
                return {'status': 'duplicado', 'arquivo': str(destino), 'hash': hash_arquivo}

            destino = self.encaminhar_arquivo(path, 'processando', hash_arquivo)
            self._registrar('fim_monitoramento', f'Arquivo reservado para processamento: {destino.name}', hash_arquivo)
            return {'status': 'processando', 'arquivo': str(destino), 'hash': hash_arquivo}
        except (OSError, ValueError) as exc:
            return self._erro(path, str(exc))
        finally:
            lock.release()

    def encaminhar_arquivo(self, path: Path, destino: str, hash_arquivo: Optional[str] = None) -> Path:
        if destino not in DESTINOS:
            raise ValueError(f'Destino inválido: {destino}')
        origem = Path(path)
        if not origem.exists():
            raise FileNotFoundError(f'Arquivo não encontrado para encaminhamento: {origem}')
        pasta_destino = self._caminho(DESTINOS[destino])
        pasta_destino.mkdir(parents=True, exist_ok=True)
        alvo = self._nome_disponivel(pasta_destino / origem.name)
        shutil.move(str(origem), str(alvo))
        self._registrar(destino, f'Arquivo encaminhado para {destino}: {alvo.name}', hash_arquivo)
        return alvo

    def _hash_duplicado(self, hash_arquivo: str) -> bool:
        if not self.connection_factory:
            return False
        conn = self.connection_factory()
        try:
            tabela = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'faturas'").fetchone()
            if tabela and conn.execute('SELECT 1 FROM faturas WHERE hash_arquivo = ? LIMIT 1', (hash_arquivo,)).fetchone() is not None:
                return True
            logs = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'logs_processamento'").fetchone()
            return bool(logs and conn.execute(
                "SELECT 1 FROM logs_processamento WHERE hash_arquivo = ? AND status NOT IN ('erro_monitoramento', 'erro') LIMIT 1",
                (hash_arquivo,),
            ).fetchone())
        finally:
            conn.close()

    def _registrar(self, status: str, mensagem: str, hash_arquivo: Optional[str] = None) -> None:
        if not self.connection_factory:
            return
        conn = self.connection_factory()
        try:
            conn.execute('INSERT INTO logs_processamento (fatura_id, status, mensagem, hash_arquivo) VALUES (?, ?, ?, ?)', (None, status, mensagem, hash_arquivo))
            conn.commit()
        finally:
            conn.close()

    def _erro(self, path: Path, mensagem: str, hash_arquivo: Optional[str] = None) -> Dict[str, str]:
        try:
            destino = self.encaminhar_arquivo(path, 'erro', hash_arquivo) if path.exists() else path
        except (OSError, ValueError) as exc:
            mensagem = f'{mensagem} Falha ao encaminhar: {exc}'
            destino = path
        self._registrar('erro_monitoramento', mensagem, hash_arquivo)
        return {'status': 'erro', 'arquivo': str(destino), 'mensagem': mensagem}

    def _caminho(self, chave: str) -> Path:
        valor = str(self.config.get(chave, '')).strip()
        if not valor:
            raise ValueError(f'Caminho obrigatório não configurado: {chave}')
        return Path(valor)

    def _garantir_pastas(self) -> None:
        for chave in DESTINOS.values():
            self._caminho(chave).mkdir(parents=True, exist_ok=True)

    @classmethod
    def _obter_lock(cls, path: Path) -> threading.Lock:
        chave = str(path.resolve()).lower()
        with cls._locks_guard:
            return cls._locks.setdefault(chave, threading.Lock())

    @staticmethod
    def _nome_disponivel(path: Path) -> Path:
        if not path.exists():
            return path
        indice = 1
        while True:
            candidato = path.with_name(f'{path.stem}_{indice}{path.suffix}')
            if not candidato.exists():
                return candidato
            indice += 1


def monitorar_pasta(config: Dict[str, str], connection_factory=None) -> list[Dict[str, str]]:
    monitor = MonitorPasta(config, connection_factory=connection_factory)
    return [monitor.monitorar_arquivo(path) for path in monitor.detectar_arquivos_novos()]


if __name__ == '__main__':
    print('Use monitorar_pasta(config) para executar o monitor sem processar faturas.')