import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Interface_Web' / 'backend'))

import app as backend


def test_normalizar_classificacao_removes_acentos_corrompidos():
    assert backend.normalizar_classificacao('AGUARDANDO_REVIS?O') == 'AGUARDANDO_REVISÃO'
    assert backend.normalizar_classificacao('COMPARTILHADA') == 'COMPARTILHADA'
    assert backend.normalizar_classificacao('EXCLUSIVA') == 'EXCLUSIVA'
