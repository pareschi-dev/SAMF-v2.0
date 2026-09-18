import io
import os
import tempfile
from pathlib import Path

import fitz
import pytest

from extrator_pdf import extrair_pdf

ROOT = Path(__file__).resolve().parents[1]


def _make_scanned_pdf(text: str, path: Path):
    doc = fitz.open()
    page = doc.new_page()
    img = fitz.Pixmap(fitz.Colorspace(fitz.CS_GRAY), 1, 1)
    img = None
    del img
    page.insert_image(page.rect, filename=None)
    doc.save(path)
    doc.close()


def test_extrator_pdf_digital_real():
    pdf_path = ROOT / 'Duplicados' / 'CESAN - 05 - MAIO - ED. SEDE.pdf'
    resultado = extrair_pdf(str(pdf_path))

    assert resultado['status'] == 'ok'
    assert len(resultado['faturas']) >= 1
    assert resultado['faturas'][0]['fornecedor'] == 'CESAN'
    assert resultado['faturas'][0]['cnpj']
    assert resultado['faturas'][0]['valor']
    assert 'competencia' in resultado['faturas'][0]
    assert 'campos_nao_encontrados' in resultado


def test_extrator_pdf_escaneado_usa_ocr(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / 'escaneado.pdf'
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), 'Texto escaneado de teste', fontsize=14)
        doc.save(pdf_path)
        doc.close()

        def fake_ocr(*args, **kwargs):
            return 'EMPRESA TESTE\nCNPJ: 12.345.678/0001-99\nR$ 1.234,56\nMÊS/ANO 05/2026'

        monkeypatch.setattr('extrator_pdf.pytesseract.image_to_string', fake_ocr)
        monkeypatch.setattr('extrator_pdf.fitz.open', lambda *a, **k: fitz.open(pdf_path))
        resultado = extrair_pdf(str(pdf_path))

        assert resultado['status'] in {'ok', 'escaneado'}
        assert any(f['fornecedor'] for f in resultado['faturas']) or resultado['campos_nao_encontrados']


def test_extrator_pdf_ilegivel():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / 'ilegivel.pdf'
        pdf_path.write_bytes(b'%PDF-1.4\n%%EOF\n')
        resultado = extrair_pdf(str(pdf_path))

        assert resultado['status'] in {'corrompido', 'ilegivel', 'protegido'}
        assert 'faturas' in resultado


def test_extrator_pdf_com_mais_de_uma_fatura():
    pdf_path = ROOT / 'Processados' / 'SUDESTE - 06 - JUNHO - TODAS.pdf'
    resultado = extrair_pdf(str(pdf_path))

    assert resultado['status'] in {'ok', 'multi_fatura'}
    assert len(resultado['faturas']) >= 2


def test_extrator_pdf_sem_valor():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / 'sem_valor.pdf'
        pdf_path.write_text('NO VALUE HERE\nCNPJ: 12.345.678/0001-99\n', encoding='utf-8')
        resultado = extrair_pdf(str(pdf_path))

        assert resultado['status'] in {'ok', 'ilegivel'}
        assert 'campos_nao_encontrados' in resultado
