import sqlite3
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from robo_vigia import MonitorPasta


def _config(tmp_path):
    return {
        'entrada_path': str(tmp_path / 'entrada'),
        'processamento_path': str(tmp_path / 'processando'),
        'processadas_path': str(tmp_path / 'processadas'),
        'compartilhadas_path': str(tmp_path / 'compartilhadas'),
        'exclusivas_path': str(tmp_path / 'exclusivas'),
        'revisao_path': str(tmp_path / 'revisao'),
        'duplicadas_path': str(tmp_path / 'duplicadas'),
        'erro_path': str(tmp_path / 'erro'),
        'tempo_estabilidade_arquivo_segundos': '0',
    }


def _banco(tmp_path):
    banco = tmp_path / 'monitor.db'
    conn = sqlite3.connect(banco)
    conn.execute('CREATE TABLE faturas (hash_arquivo TEXT UNIQUE NOT NULL)')
    conn.execute('CREATE TABLE logs_processamento (fatura_id INTEGER, status TEXT, mensagem TEXT, hash_arquivo TEXT)')
    conn.commit()
    conn.close()
    return lambda: sqlite3.connect(banco)


def test_arquivo_em_copia_aguarda_estabilidade_e_vai_para_processando(tmp_path):
    config = _config(tmp_path)
    entrada = Path(config['entrada_path'])
    entrada.mkdir(parents=True)
    arquivo = entrada / 'fatura.pdf'
    arquivo.write_bytes(b'%PDF-copia-estavel')
    monitor = MonitorPasta(config, sleep=lambda _: None)

    resultado = monitor.monitorar_arquivo(arquivo)

    assert resultado['status'] == 'processando'
    assert Path(resultado['arquivo']).parent == Path(config['processamento_path'])
    assert not arquivo.exists()


def test_arquivo_duplicado_vai_para_duplicadas_antes_do_processamento(tmp_path):
    config = _config(tmp_path)
    entrada = Path(config['entrada_path'])
    entrada.mkdir(parents=True)
    arquivo = entrada / 'duplicada.pdf'
    arquivo.write_bytes(b'%PDF-duplicado')
    monitor = MonitorPasta(config, connection_factory=_banco(tmp_path), sleep=lambda _: None)
    hash_arquivo = monitor.calcular_hash(arquivo)
    conn = monitor.connection_factory()
    conn.execute('INSERT INTO faturas (hash_arquivo) VALUES (?)', (hash_arquivo,))
    conn.commit()
    conn.close()

    resultado = monitor.monitorar_arquivo(arquivo)

    assert resultado['status'] == 'duplicado'
    assert Path(resultado['arquivo']).parent == Path(config['duplicadas_path'])


def test_arquivo_temporario_e_ignorado(tmp_path):
    config = _config(tmp_path)
    entrada = Path(config['entrada_path'])
    entrada.mkdir(parents=True)
    arquivo = entrada / 'fatura.pdf.part'
    arquivo.write_bytes(b'copia')
    monitor = MonitorPasta(config, sleep=lambda _: None)

    resultado = monitor.monitorar_arquivo(arquivo)

    assert resultado['status'] == 'ignorado_temporario'
    assert arquivo.exists()
    assert not list(Path(config['processamento_path']).iterdir())


def test_arquivo_invalido_vai_para_erro(tmp_path):
    config = _config(tmp_path)
    entrada = Path(config['entrada_path'])
    entrada.mkdir(parents=True)
    arquivo = entrada / 'fatura.txt'
    arquivo.write_text('não é PDF', encoding='utf-8')
    monitor = MonitorPasta(config, sleep=lambda _: None)

    resultado = monitor.monitorar_arquivo(arquivo)

    assert resultado['status'] == 'erro'
    assert Path(resultado['arquivo']).parent == Path(config['erro_path'])


def test_dois_arquivos_simultaneos_sao_reservados_individualmente(tmp_path):
    config = _config(tmp_path)
    entrada = Path(config['entrada_path'])
    entrada.mkdir(parents=True)
    arquivos = [entrada / 'um.pdf', entrada / 'dois.pdf']
    for arquivo in arquivos:
        arquivo.write_bytes(arquivo.name.encode('ascii'))
    monitor = MonitorPasta(config, sleep=lambda _: None)
    resultados = []

    threads = [threading.Thread(target=lambda item=item: resultados.append(monitor.monitorar_arquivo(item))) for item in arquivos]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(resultado['status'] for resultado in resultados) == ['processando', 'processando']
    assert len(list(Path(config['processamento_path']).glob('*.pdf'))) == 2


def test_monitor_registra_inicio_fim_e_erro(tmp_path):
    config = _config(tmp_path)
    entrada = Path(config['entrada_path'])
    entrada.mkdir(parents=True)
    arquivo_ok = entrada / 'ok.pdf'
    arquivo_ok.write_bytes(b'ok')
    arquivo_erro = entrada / 'erro.txt'
    arquivo_erro.write_text('erro', encoding='utf-8')
    monitor = MonitorPasta(config, connection_factory=_banco(tmp_path), sleep=lambda _: None)

    monitor.monitorar_arquivo(arquivo_ok)
    monitor.monitorar_arquivo(arquivo_erro)
    conn = monitor.connection_factory()
    statuses = [row[0] for row in conn.execute('SELECT status FROM logs_processamento').fetchall()]
    conn.close()

    assert 'inicio_monitoramento' in statuses
    assert 'fim_monitoramento' in statuses
    assert 'erro_monitoramento' in statuses