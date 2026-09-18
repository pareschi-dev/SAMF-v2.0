import json
import sqlite3
import zipfile

from backup_recuperacao import criar_backup, restaurar_backup, testar_restauracao as validar_restauracao


def _criar_banco(caminho):
    conn = sqlite3.connect(caminho)
    conn.execute('CREATE TABLE dados (id INTEGER PRIMARY KEY, valor TEXT)')
    conn.execute('INSERT INTO dados (valor) VALUES (?)', ('original',))
    conn.commit()
    conn.close()


def test_backup_e_restauracao_em_ambiente_separado(tmp_path):
    raiz = tmp_path / 'origem'
    raiz.mkdir()
    (raiz / 'Configuracoes').mkdir()
    (raiz / 'Configuracoes' / 'samf_config.json').write_text(
        json.dumps({'ambiente': 'desenvolvimento', 'api_token': 'nao salvar'}), encoding='utf-8'
    )
    banco = raiz / 'samf.db'
    _criar_banco(banco)
    pacote = criar_backup(
        {'backup_path': str(raiz / 'Backups')}, motivo='atualizacao_importante',
        raiz=raiz, db_path=banco, destino=raiz / 'Backups'
    )

    restaurado = tmp_path / 'ambiente_separado'
    restaurar_backup(pacote, restaurado)
    conn = sqlite3.connect(restaurado / 'banco' / 'samf.db')
    assert conn.execute('SELECT valor FROM dados').fetchone()[0] == 'original'
    conn.close()
    config = json.loads((restaurado / 'config' / 'samf_config.json').read_text(encoding='utf-8'))
    assert 'api_token' not in config
    assert validar_restauracao(pacote).is_dir()


def test_restauracao_rejeita_membro_com_path_traversal(tmp_path):
    pacote = tmp_path / 'malicioso.zip'
    with zipfile.ZipFile(pacote, 'w') as arquivo:
        arquivo.writestr('../fora.txt', 'conteudo')
    try:
        restaurar_backup(pacote, tmp_path / 'destino')
    except ValueError as erro:
        assert 'caminho' in str(erro)
    else:
        raise AssertionError('path traversal aceito')