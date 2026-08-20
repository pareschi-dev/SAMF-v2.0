"""Backup versionado e restauração segura do SAMF."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / 'samf.db'
BACKUP_DIR = ROOT_DIR / 'Backups'
VERSAO_PADRAO = 'v1.0.0'


def _configuracao_segura(config: dict[str, Any]) -> dict[str, Any]:
    sensiveis = ('senha', 'password', 'token', 'secret', 'credential', 'chave', 'api_key')
    return {chave: valor for chave, valor in config.items() if not any(item in chave.lower() for item in sensiveis)}


def _hash(arquivo: Path) -> str:
    digest = hashlib.sha256()
    with arquivo.open('rb') as handle:
        for bloco in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(bloco)
    return digest.hexdigest()


def _copiar_arquivo(origem: Path, staging: Path, destino: str, arquivos: list[dict[str, str]]) -> None:
    if not origem.is_file():
        return
    alvo = staging / destino
    alvo.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, alvo)
    arquivos.append({'caminho': destino, 'sha256': _hash(alvo), 'tamanho': str(alvo.stat().st_size)})


def _copiar_pdfs(origem: Path, staging: Path, arquivos: list[dict[str, str]]) -> None:
    if not origem.is_dir():
        return
    for arquivo in origem.rglob('*'):
        if arquivo.is_file() and arquivo.suffix.lower() == '.pdf':
            relativo = arquivo.relative_to(origem).as_posix()
            _copiar_arquivo(arquivo, staging, f'pdfs/{origem.name}/{relativo}', arquivos)


def _snapshot_tabelas(db_path: Path, staging: Path, arquivos: list[dict[str, str]]) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        regras = {}
        for tabela in ('regras_administrativas', 'padroes_rateio', 'regras_classificacao'):
            existe = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)).fetchone()
            if existe:
                regras[tabela] = [dict(row) for row in conn.execute(f'SELECT * FROM {tabela}').fetchall()]
        logs = {}
        for tabela in ('logs_processamento', 'auditoria', 'auditoria_eventos'):
            existe = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)).fetchone()
            if existe:
                logs[tabela] = [dict(row) for row in conn.execute(f'SELECT * FROM {tabela}').fetchall()]
    finally:
        conn.close()
    for nome, conteudo in (('regras/regras.json', regras), ('logs/logs.json', logs)):
        alvo = staging / nome
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        arquivos.append({'caminho': nome, 'sha256': _hash(alvo), 'tamanho': str(alvo.stat().st_size)})


def criar_backup(config: dict[str, Any] | None = None, *, motivo: str, versao: str = VERSAO_PADRAO,
                 raiz: Path = ROOT_DIR, db_path: Path = DB_PATH, destino: Path | None = None) -> Path:
    config = config or {}
    backup_dir = Path(destino) if destino else Path(config.get('backup_path') or raiz / 'Backups')
    backup_dir.mkdir(parents=True, exist_ok=True)
    instante = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = f'backup_{instante}_{versao}'
    numero = 1
    arquivo_zip = backup_dir / f'{base}_{numero:03d}.zip'
    while arquivo_zip.exists():
        numero += 1
        arquivo_zip = backup_dir / f'{base}_{numero:03d}.zip'
    staging = Path(tempfile.mkdtemp(prefix=f'{base}_', dir=backup_dir))
    arquivos: list[dict[str, str]] = []
    try:
        if not db_path.is_file():
            raise FileNotFoundError(f'Banco não encontrado: {db_path}')
        copia_db = staging / 'banco/samf.db'
        copia_db.parent.mkdir(parents=True, exist_ok=True)
        origem = sqlite3.connect(db_path)
        destino_db = sqlite3.connect(copia_db)
        try:
            origem.backup(destino_db)
        finally:
            destino_db.close(); origem.close()
        arquivos.append({'caminho': 'banco/samf.db', 'sha256': _hash(copia_db), 'tamanho': str(copia_db.stat().st_size)})

        config_path = raiz / 'Configuracoes' / 'samf_config.json'
        if config_path.is_file():
            seguro = staging / 'config/samf_config.json'
            seguro.parent.mkdir(parents=True, exist_ok=True)
            seguro.write_text(json.dumps(_configuracao_segura(json.loads(config_path.read_text(encoding='utf-8'))), ensure_ascii=False, indent=2), encoding='utf-8')
            arquivos.append({'caminho': 'config/samf_config.json', 'sha256': _hash(seguro), 'tamanho': str(seguro.stat().st_size)})

        planilha = Path(config.get('planilha_oficial_path') or config.get('planilha_path') or '')
        if planilha.is_file():
            _copiar_arquivo(planilha, staging, f'planilha/{planilha.name}', arquivos)
        pdf_dirs = {raiz / 'Processados'}
        for chave in ('processadas_path', 'compartilhadas_path', 'exclusivas_path', 'revisao_path', 'duplicadas_path', 'erro_path'):
            if config.get(chave):
                pdf_dirs.add(Path(config[chave]))
        for pasta in pdf_dirs:
            _copiar_pdfs(pasta, staging, arquivos)
        _snapshot_tabelas(db_path, staging, arquivos)

        manifest = {
            'produto': 'SAMF', 'versao_backup': versao, 'criado_em': datetime.now().isoformat(timespec='seconds'),
            'motivo': motivo, 'banco_origem': str(db_path), 'arquivos': arquivos,
            'politica': 'append-only: nunca sobrescrever backups anteriores; retenção por política operacional.',
        }
        manifesto = staging / 'manifest.json'
        manifesto.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        with zipfile.ZipFile(arquivo_zip, 'w', zipfile.ZIP_DEFLATED) as pacote:
            for caminho in staging.rglob('*'):
                if caminho.is_file():
                    pacote.write(caminho, caminho.relative_to(staging).as_posix())
        return arquivo_zip
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def restaurar_backup(arquivo: Path, destino: Path, *, permitir_destino_existente: bool = False) -> Path:
    arquivo = Path(arquivo); destino = Path(destino)
    if not arquivo.is_file():
        raise FileNotFoundError(f'Backup não encontrado: {arquivo}')
    if destino.exists() and any(destino.iterdir()) and not permitir_destino_existente:
        raise FileExistsError('O destino de restauração não está vazio.')
    destino.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporario:
        extraido = Path(temporario)
        with zipfile.ZipFile(arquivo) as pacote:
            pacote.extractall(extraido)
        manifest = json.loads((extraido / 'manifest.json').read_text(encoding='utf-8'))
        for item in manifest['arquivos']:
            copia = extraido / item['caminho']
            if not copia.is_file() or _hash(copia) != item['sha256']:
                raise ValueError(f'Integridade inválida no arquivo {item["caminho"]}.')
        for item in manifest['arquivos']:
            origem = extraido / item['caminho']
            alvo = destino / item['caminho']
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, alvo)
        shutil.copy2(extraido / 'manifest.json', destino / 'manifest.json')
    banco = destino / 'banco/samf.db'
    conn = sqlite3.connect(banco)
    try:
        conn.execute('PRAGMA integrity_check')
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Banco restaurado reprovado no integrity_check.')
    finally:
        conn.close()
    return destino


def testar_restauracao(arquivo: Path) -> Path:
    destino = Path(tempfile.mkdtemp(prefix='samf_restore_test_'))
    try:
        restaurar_backup(Path(arquivo), destino)
        return destino
    except Exception:
        shutil.rmtree(destino, ignore_errors=True)
        raise


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Backup e restauração SAMF')
    subparsers = parser.add_subparsers(dest='comando', required=True)
    criar = subparsers.add_parser('criar'); criar.add_argument('--motivo', required=True); criar.add_argument('--versao', default=VERSAO_PADRAO)
    restaurar = subparsers.add_parser('restaurar'); restaurar.add_argument('arquivo'); restaurar.add_argument('destino')
    teste = subparsers.add_parser('testar'); teste.add_argument('arquivo')
    args = parser.parse_args()
    if args.comando == 'criar': print(criar_backup(motivo=args.motivo, versao=args.versao))
    elif args.comando == 'restaurar': print(restaurar_backup(Path(args.arquivo), Path(args.destino)))
    else: print(testar_restauracao(Path(args.arquivo)))
