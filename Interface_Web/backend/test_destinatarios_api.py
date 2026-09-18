import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import app as app_module


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    banco = tmp_path / 'destinatarios.db'
    backup = []

    def conectar():
        conn = sqlite3.connect(banco)
        conn.row_factory = sqlite3.Row
        return conn

    def criar_backup(motivo):
        backup.append(motivo)
        return tmp_path / f'backup_{len(backup)}.zip'

    monkeypatch.setattr(app_module, 'get_db', conectar)
    monkeypatch.setattr(app_module, '_backup_antes', criar_backup)
    cliente = app_module.app.test_client()
    assert cliente.post('/api/auth/bootstrap', json={
        'usuario': 'admin', 'nome': 'Administrador', 'senha': 'senha-segura',
    }).status_code == 201
    token = cliente.post('/api/auth/login', json={
        'usuario': 'admin', 'senha': 'senha-segura',
    }).get_json()['token']
    return cliente, {'Authorization': f'Bearer {token}'}, conectar, backup


def destinatario(**alteracoes):
    dados = {
        'nome': 'Ana', 'orgao': 'SRA', 'unidade': 'Sede',
        'telefone': '+55 (11) 99999-1234', 'tipo': 'orgao',
        'ativo': True, 'autorizacao_registrada': True,
    }
    dados.update(alteracoes)
    return dados


def test_rejeita_telefone_invalido_na_criacao(ambiente):
    cliente, headers, *_ = ambiente
    resposta = cliente.post('/api/destinatarios', headers=headers, json=destinatario(telefone='123'))
    assert resposta.status_code == 400
    assert 'telefone' in resposta.get_json()['erro'].lower()


def test_aceita_e_normaliza_telefone_valido(ambiente):
    cliente, headers, conectar, _ = ambiente
    resposta = cliente.post('/api/destinatarios', headers=headers, json=destinatario())
    assert resposta.status_code == 201
    conn = conectar()
    assert conn.execute('SELECT telefone FROM destinatarios').fetchone()[0] == '+5511999991234'
    conn.close()


def test_rejeita_telefone_invalido_na_alteracao(ambiente):
    cliente, headers, *_ = ambiente
    id_destinatario = cliente.post('/api/destinatarios', headers=headers, json=destinatario()).get_json()['id']
    resposta = cliente.put(f'/api/destinatarios/{id_destinatario}', headers=headers, json={'telefone': 'abc123'})
    assert resposta.status_code == 400


def test_audita_criacao_alteracao_e_desativacao_sem_telefone_completo(ambiente):
    cliente, headers, conectar, _ = ambiente
    id_destinatario = cliente.post('/api/destinatarios', headers=headers, json=destinatario()).get_json()['id']
    assert cliente.put(f'/api/destinatarios/{id_destinatario}', headers=headers, json={'nome': 'Ana Atualizada'}).status_code == 200
    assert cliente.put(f'/api/destinatarios/{id_destinatario}', headers=headers, json={'ativo': False}).status_code == 200
    conn = conectar()
    eventos = conn.execute('SELECT acao, dados_anterior, dados_novo, usuario, status FROM auditoria_cobranca WHERE tabela_origem=? ORDER BY id', ('destinatario',)).fetchall()
    assert [evento['acao'] for evento in eventos] == ['criação', 'alteração', 'desativação']
    assert all(evento['usuario'] == 'admin' and evento['status'] == 'sucesso' for evento in eventos)
    texto = json.dumps([dict(evento) for evento in eventos], ensure_ascii=False)
    assert '99999-1234' not in texto
    assert '+5511999991234' not in texto
    assert 'senha' not in texto.lower()
    assert 'token' not in texto.lower()
    conn.close()


def test_falha_de_backup_impede_alteracao_e_nao_audita(monkeypatch, ambiente):
    cliente, headers, conectar, backup = ambiente
    id_destinatario = cliente.post('/api/destinatarios', headers=headers, json=destinatario()).get_json()['id']
    antes = len(backup)

    def falhar(_motivo):
        raise OSError('backup indisponível')

    monkeypatch.setattr(app_module, '_backup_antes', falhar)
    resposta = cliente.put(f'/api/destinatarios/{id_destinatario}', headers=headers, json={'nome': 'Não salvar'})
    assert resposta.status_code == 409
    conn = conectar()
    assert conn.execute('SELECT nome FROM destinatarios WHERE id=?', (id_destinatario,)).fetchone()[0] == 'Ana'
    assert conn.execute('SELECT COUNT(*) FROM auditoria_cobranca WHERE tabela_origem=?', ('destinatario',)).fetchone()[0] == 1
    assert len(backup) == antes
    conn.close()