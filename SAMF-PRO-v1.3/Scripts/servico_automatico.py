"""Serviço contínuo de monitoramento e processamento automático de PDFs."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from configuracao_operacional import carregar_configuracao
from robo_vigia import MonitorPasta

ROOT_DIR = Path(__file__).resolve().parents[1]


def _destino(config, status):
    if status == 'compartilhada':
        return Path(config['compartilhadas_path'])
    if status == 'exclusiva':
        return Path(config['exclusivas_path'])
    if status == 'sucesso':
        return Path(config['processadas_path'])
    if status == 'duplicado':
        return Path(config['duplicadas_path'])
    if status == 'revisao':
        return Path(config['revisao_path'])
    return Path(config['erro_path'])


def processar_arquivo(config, caminho):
    resultado = ROOT_DIR / 'Configuracoes' / 'resultado.json'
    comando = [sys.executable, str(ROOT_DIR / 'Scripts' / 'processar_fatura.py'), str(ROOT_DIR), str(caminho)]
    processo = subprocess.run(comando, capture_output=True, text=True)
    status = 'erro'
    classificacao = None
    if resultado.exists():
        try:
            payload = json.loads(resultado.read_text(encoding='utf-8'))
            status = payload.get('status', 'erro')
            classificacao = payload.get('classificacao')
        except (OSError, json.JSONDecodeError):
            status = 'erro'
    if processo.returncode != 0:
        status = 'erro'
    if status == 'sucesso' and classificacao in {'compartilhada', 'exclusiva'}:
        status = classificacao
    destino = _destino(config, status)
    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / caminho.name
    contador = 1
    while alvo.exists():
        alvo = destino / f'{caminho.stem}_{contador}{caminho.suffix}'
        contador += 1
    if caminho.exists():
        shutil.move(str(caminho), str(alvo))
    return status, alvo


def _arquivos_em_processamento(config):
    pasta = Path(config['processamento_path'])
    pasta.mkdir(parents=True, exist_ok=True)
    return sorted(path for path in pasta.iterdir() if path.is_file() and path.suffix.lower() == '.pdf')


def executar():
    config = carregar_configuracao(ROOT_DIR)
    intervalo = max(1, int(float(config.get('intervalo_monitoramento_segundos', 30) or 30)))
    monitor = MonitorPasta(config)
    print('SAMF automático ativo. Aguardando PDFs...', flush=True)
    while True:
        arquivos = _arquivos_em_processamento(config)
        arquivos.extend(monitor.detectar_arquivos_novos())
        for arquivo in arquivos:
            try:
                caminho = Path(arquivo)
                if caminho.parent.resolve() == Path(config['processamento_path']).resolve():
                    status, destino = processar_arquivo(config, caminho)
                    print(f'{caminho.name}: {status} -> {destino}', flush=True)
                    continue
                resultado = monitor.monitorar_arquivo(caminho)
                if resultado.get('status') == 'processando':
                    status, destino = processar_arquivo(config, Path(resultado['arquivo']))
                    print(f'{caminho.name}: {status} -> {destino}', flush=True)
            except Exception as exc:
                print(f'{Path(arquivo).name}: erro no ciclo automático: {exc}', flush=True)
        time.sleep(intervalo)


if __name__ == '__main__':
    executar()
