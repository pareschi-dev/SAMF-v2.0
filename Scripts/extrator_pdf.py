import hashlib
import os
import re
from copy import copy
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz
import pdfplumber
import pytesseract
from PIL import Image


MESES = {
    'JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ',
    'JANEIRO', 'FEVEREIRO', 'MARCO', 'ABRIL', 'MAIO', 'JUNHO', 'JULHO', 'AGOSTO', 'SETEMBRO', 'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO'
}


@dataclass
class CampoExtraido:
    nome: str
    valor: Optional[str]
    confianca: float
    origem: str
    encontrado: bool = True


class ExtratorPDF:
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        self.texto_total = ''
        self.texto_paginas: List[str] = []
        self.tabelas: List[List[List[str]]] = []
        self.status = 'ok'
        self.erro = None

    def extrair(self) -> Dict[str, Any]:
        if not self.pdf_path.exists():
            return self._resultado_erro('arquivo_nao_encontrado', 'Arquivo PDF não encontrado.')

        try:
            self.texto_total, self.texto_paginas, self.tabelas = self._ler_pdf()
        except Exception as exc:  # pragma: no cover - fallback
            self.status = 'ilegivel'
            self.erro = str(exc)
            return self._resultado_erro('ilegivel', str(exc))

        if not self.texto_total.strip():
            return self._resultado_erro('ilegivel', 'PDF sem texto legível.')

        return self._montar_resultado()

    def _ler_pdf(self) -> tuple[str, List[str], List[List[List[str]]]]:
        texto_paginas: List[str] = []
        tabelas: List[List[List[str]]] = []
        try:
            with pdfplumber.open(str(self.pdf_path)) as pdf:
                pages = list(pdf.pages)
                if not pages:
                    return '', [], []
                for page in pages:
                    text = page.extract_text() or ''
                    texto_paginas.append(text)
                    tables = page.extract_tables() or []
                    if tables:
                        tabelas.extend(tables)
                return '\n\n'.join(texto_paginas), texto_paginas, tabelas
        except Exception:
            return self._ler_ocr_fallback()

    def _ler_ocr_fallback(self) -> tuple[str, List[str], List[List[List[str]]]]:
        try:
            with fitz.open(str(self.pdf_path)) as doc:
                if doc.is_encrypted:
                    raise PermissionError('PDF protegido por senha')
                paginas: List[str] = []
                tabelas: List[List[List[str]]] = []
                for page_index in range(doc.page_count):
                    page = doc[page_index]
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    image = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
                    text = pytesseract.image_to_string(image, config='--psm 6')
                    paginas.append(text)
                return '\n\n'.join(paginas), paginas, tabelas
        except Exception as exc:
            raise RuntimeError(f'Erro ao extrair PDF: {exc}')

    def _resultado_erro(self, status: str, mensagem: str) -> Dict[str, Any]:
        return {
            'status': status,
            'arquivo': str(self.pdf_path),
            'hash': self._hash_arquivo(),
            'faturas': [],
            'campos_nao_encontrados': [],
            'erro': mensagem,
        }

    def _hash_arquivo(self) -> str:
        digest = hashlib.sha256()
        try:
            with open(self.pdf_path, 'rb') as file:
                for chunk in iter(lambda: file.read(8192), b''):
                    digest.update(chunk)
        except OSError:
            return ''
        return digest.hexdigest()

    def _montar_resultado(self) -> Dict[str, Any]:
        texto = self.texto_total
        if not texto.strip():
            return self._resultado_erro('ilegivel', 'Textos vazios após leitura.')

        empresas = self._quebrar_faturas(texto)
        if not empresas:
            empresas = [texto]

        faturas: List[Dict[str, Any]] = []
        campos_nao_encontrados: List[str] = []

        for bloco in empresas:
            campos = self._extrair_campos(bloco)
            campos_nao_encontrados.extend(campos.get('campos_nao_encontrados', []))
            faturas.append(campos)

        resultado = {
            'status': 'ok' if len(faturas) <= 1 else 'multi_fatura',
            'arquivo': str(self.pdf_path),
            'hash': self._hash_arquivo(),
            'faturas': faturas,
            'tabelas': self.tabelas,
            'campos_nao_encontrados': sorted(set(campos_nao_encontrados)),
        }
        return resultado

    def _quebrar_faturas(self, texto: str) -> List[str]:
        padrao = r'DANFSev1\.0|DOCUMENTO\s+AUXILIAR\s+DA\s+NOTA\s+FISCAL|DOCUMENTO\s+AUXILIAR\s+DA\s+NFS-?E'
        ocorrencias_documento = list(re.finditer(padrao, texto, flags=re.I))
        if len(ocorrencias_documento) <= 1:
            return []

        blocos: List[str] = []
        posicoes = [match.start() for match in ocorrencias_documento]
        for indice, posicao in enumerate(posicoes):
            inicio = posicao
            fim = posicoes[indice + 1] if indice + 1 < len(posicoes) else len(texto)
            bloco = texto[inicio:fim].strip()
            if bloco:
                blocos.append(bloco)
        return blocos

    def _extrair_campos(self, bloco: str) -> Dict[str, Any]:
        bloco_norm = bloco.replace('\r', '\n')
        texto_upper = bloco_norm.upper()

        fornecedor = self._localizar_fornecedor(bloco_norm)
        cnpj = self._extrair_cnpj(bloco_norm)
        numero = self._extrair_numero(bloco_norm)
        datas = self._extrair_datas(bloco_norm)
        competencia = self._extrair_competencia(bloco_norm)
        servico = self._extrair_servico(bloco_norm)
        descricao = self._extrair_descricao(bloco_norm)
        valor = self._extrair_valor(bloco_norm)
        endereco = self._extrair_endereco(bloco_norm)
        unidade = self._extrair_unidade(bloco_norm)
        orgao = self._extrair_orgao(bloco_norm)

        campos = {
            'fornecedor': fornecedor or 'NAO_ENCONTRADO',
            'cnpj': cnpj or 'NAO_ENCONTRADO',
            'numero': numero or 'NAO_ENCONTRADO',
            'data_emissao': datas.get('emissao') or 'NAO_ENCONTRADO',
            'data_vencimento': datas.get('vencimento') or 'NAO_ENCONTRADO',
            'competencia': competencia or 'NAO_ENCONTRADO',
            'servico': servico or 'NAO_ENCONTRADO',
            'descricao': descricao or 'NAO_ENCONTRADO',
            'valor': valor,
            'endereco': endereco or 'NAO_ENCONTRADO',
            'unidade': unidade or 'NAO_ENCONTRADO',
            'orgao': orgao or 'NAO_ENCONTRADO',
            'confianca': self._calcular_confianca({
                'fornecedor': fornecedor,
                'cnpj': cnpj,
                'numero': numero,
                'competencia': competencia,
                'servico': servico,
                'valor': valor,
                'endereco': endereco,
                'unidade': unidade,
                'orgao': orgao,
            }),
            'campos_nao_encontrados': [
                campo for campo, valor_campo in {
                    'fornecedor': fornecedor,
                    'cnpj': cnpj,
                    'numero': numero,
                    'data_emissao': datas.get('emissao'),
                    'data_vencimento': datas.get('vencimento'),
                    'competencia': competencia,
                    'servico': servico,
                    'descricao': descricao,
                    'valor': valor,
                    'endereco': endereco,
                    'unidade': unidade,
                    'orgao': orgao,
                }.items() if not valor_campo or valor_campo == 'NAO_ENCONTRADO'
            ],
        }
        return campos

    def _localizar_fornecedor(self, texto: str) -> Optional[str]:
        padroes = [
            r'COMPANHIA\s+ESPIRITO\s+SANTENSE\s+DE\s+SANEAMENTO.*?[-–]?\s*(CESAN)',
            r'\b(CESAN)\b',
            r'\b(ELEVADORES\s+MILÊNIO)\b',
            r'\b(P\.M\.V\.|P.M.V\.)\b',
            r'\b(EDP)\b',
            r'\b(SUDESTE)\b',
            r'\b(AJP)\b',
            r'\b(VIVO)\b',
            r'\b(JCA)\b',
            r'\b(MÁXIMA)\b',
            r'\b(SEI)\b',
        ]
        for padrao in padroes:
            match = re.search(padrao, texto, flags=re.I)
            if match:
                return match.group(1).upper()
        return None

    def _extrair_cnpj(self, texto: str) -> Optional[str]:
        match = re.search(r'CNPJ\s*[:\-]?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', texto)
        if match:
            return match.group(1)
        return None

    def _extrair_numero(self, texto: str) -> Optional[str]:
        for padrao in [
            r'NF\.?\s*[:\-]?\s*(\d+)',
            r'NOTA\s+FISCAL\s*[:\-]?\s*(\d+)',
            r'FATURA\s*[:\-]?\s*([A-Z0-9/-]+)',
            r'MATRICULA\s*[:\-]?\s*([A-Z0-9-]+)',
        ]:
            match = re.search(padrao, texto, flags=re.I)
            if match:
                return match.group(1)
        return None

    def _extrair_datas(self, texto: str) -> Dict[str, Optional[str]]:
        datas = {}
        for padrao, nome in [
            (r'VENCIMENTO\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})', 'vencimento'),
            (r'DATA\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})', 'emissao'),
            (r'EMISS[ÃA]O\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})', 'emissao'),
            (r'VENC\.?\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})', 'vencimento'),
        ]:
            match = re.search(padrao, texto, flags=re.I)
            if match:
                datas[nome] = match.group(1)
        return datas

    def _extrair_competencia(self, texto: str) -> Optional[str]:
        padroes = [
            r'MÊS/ANO\s*[:\-]?\s*(\d{2}/\d{4})',
            r'PERIODO\s+DE\s+REFERENCIA\s*[:\-]?\s*(\d{2}/\d{4})',
            r'M[ÊE]S\s*[:\-]?\s*(\d{2}/\d{4})',
            r'(\d{2}/\d{4})',
        ]
        for padrao in padroes:
            match = re.search(padrao, texto, flags=re.I)
            if match:
                return match.group(1)
        return None

    def _extrair_servico(self, texto: str) -> Optional[str]:
        for termo in ['ÁGUA E ESGOTO', 'ENERGIA ELÉTRICA', 'ALUGUÉIS + TAXAS', 'DEDIZAÇÃO', 'SERVIÇO DE LIMPEZA', 'MANUTENÇÃO DE JARDINS']:
            if termo in texto.upper():
                return termo.title()
        if 'ÁGUA' in texto.upper() or 'ESGOTO' in texto.upper():
            return 'Água e esgoto'
        if 'ENERGIA' in texto.upper():
            return 'Energia elétrica'
        return None

    def _extrair_descricao(self, texto: str) -> Optional[str]:
        for padrao in [
            r'DESCRICAO\s*[:\-]?\s*(.*)',
            r'DESCRIÇÃO\s*[:\-]?\s*(.*)',
            r'CATALOGO\s*[:\-]?\s*(.*)',
            r'TIPO DE LIGAÇÃO\s*[:\-]?\s*(.*)',
        ]:
            match = re.search(padrao, texto, flags=re.I | re.S)
            if match:
                descricao = re.sub(r'\s+', ' ', match.group(1)).strip()
                return descricao[:200] if descricao else None
        return None

    def _extrair_valor(self, texto: str) -> Optional[float]:
        valores = re.findall(r'R\$\s*([0-9\.]+,[0-9]{2})', texto)
        if not valores:
            valores = re.findall(r'([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})', texto)
        if not valores:
            return None
        valor = valores[0]
        valor = valor.replace('.', '').replace(',', '.')
        try:
            return float(valor)
        except ValueError:
            return None

    def _extrair_endereco(self, texto: str) -> Optional[str]:
        match = re.search(r'([A-ZÀ-Ÿ0-9\.\-\s,]+)\s*CEP\s*:\s*\d{5}-?\d{3}', texto, flags=re.I)
        if match:
            return re.sub(r'\s+', ' ', match.group(1)).strip()
        return None

    def _extrair_unidade(self, texto: str) -> Optional[str]:
        for padrao in [
            r'UNIDADE\s*[:\-]?\s*([A-Z0-9À-Ÿ/\-\s]+)',
            r'LOCAL\s*[:\-]?\s*([A-Z0-9À-Ÿ/\-\s]+)',
            r'ENDERECO\s*[:\-]?\s*([A-Z0-9À-Ÿ/\-\s]+)',
        ]:
            match = re.search(padrao, texto, flags=re.I)
            if match:
                return re.sub(r'\s+', ' ', match.group(1)).strip()
        return None

    def _extrair_orgao(self, texto: str) -> Optional[str]:
        for termo in ['SRA', 'DRF', 'PFN', 'PSFN', 'SPU', 'CGU', 'BB', 'SERPRO', 'ABIN', 'ALFÂNDEGA', 'SRT', 'AGU', 'FUNDACENTRO', 'ASSEFAZ', 'IBGE']:
            if termo in texto.upper():
                return termo
        return None

    def _calcular_confianca(self, campos: Dict[str, Any]) -> float:
        score = 0
        total = 0
        for nome, valor_campo in campos.items():
            if nome in {'campos_nao_encontrados'}:
                continue
            total += 1
            if valor_campo not in (None, 'NAO_ENCONTRADO', ''):
                score += 1
        if total == 0:
            return 0.0
        return round(score / total, 2)


def extrair_pdf(pdf_path: str) -> Dict[str, Any]:
    return ExtratorPDF(pdf_path).extrair()


if __name__ == '__main__':
    import json
    import sys
    if len(sys.argv) < 2:
        print(json.dumps({'status': 'erro', 'mensagem': 'Uso: extrator_pdf.py <arquivo.pdf>'}, ensure_ascii=False))
    else:
        print(json.dumps(extrair_pdf(sys.argv[1]), ensure_ascii=False, indent=2))
