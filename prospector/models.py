"""Modelo de lead e normalizacoes (telefone BR, chave de deduplicacao)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional

# DDDs validos no Brasil (evita tratar numero truncado como telefone bom).
DDDS_VALIDOS = {
    11, 12, 13, 14, 15, 16, 17, 18, 19,
    21, 22, 24, 27, 28,
    31, 32, 33, 34, 35, 37, 38,
    41, 42, 43, 44, 45, 46, 47, 48, 49,
    51, 53, 54, 55,
    61, 62, 63, 64, 65, 66, 67, 68, 69,
    71, 73, 74, 75, 77, 79,
    81, 82, 83, 84, 85, 86, 87, 88, 89,
    91, 92, 93, 94, 95, 96, 97, 98, 99,
}


def so_digitos(texto: Optional[str]) -> str:
    return re.sub(r"\D", "", texto or "")


def normalizar_telefone(bruto: Optional[str]) -> tuple[str, str]:
    """Devolve (e164, whatsapp_url). Strings vazias se o numero nao for utilizavel.

    Aceita os formatos que o Maps devolve: "(41) 99999-8888", "+55 41 3333-2222",
    "0800 123 4567".
    """
    d = so_digitos(bruto)
    if not d:
        return "", ""

    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]

    # 0800/0300 e afins: nao tem DDD e nao vai pro WhatsApp.
    if d.startswith("0"):
        return d, ""

    if len(d) not in (10, 11):
        return "", ""
    if int(d[:2]) not in DDDS_VALIDOS:
        return "", ""

    e164 = f"+55{d}"
    # Celular (9 digitos apos o DDD) e o unico que faz sentido no WhatsApp.
    whats = f"https://wa.me/55{d}" if len(d) == 11 and d[2] == "9" else ""
    return e164, whats


def extrair_place_key(maps_url: str, nome: str, endereco: str) -> str:
    """Chave estavel para deduplicar entre buscas.

    A URL do Maps carrega o identificador do local em `!1s0x...:0x...` — e o dado
    mais estavel disponivel sem a API. Sem ele, cai num hash de nome+endereco.
    """
    m = re.search(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", maps_url or "")
    if m:
        return m.group(1)
    base = f"{nome.strip().lower()}|{endereco.strip().lower()}"
    return "h:" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]


@dataclass
class Lead:
    place_key: str
    nome: str
    categoria: str = ""
    endereco: str = ""
    telefone: str = ""
    telefone_e164: str = ""
    whatsapp: str = ""
    site: str = ""
    tem_site: bool = False
    nota: Optional[float] = None
    avaliacoes: Optional[int] = None
    maps_url: str = ""
    termo: str = ""
    regiao: str = ""
    status: str = "novo"
    observacoes: str = ""
    primeira_vez: str = field(default_factory=lambda: date.today().isoformat())
    ultima_vez: str = field(default_factory=lambda: date.today().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


def parse_nota(texto: Optional[str]) -> Optional[float]:
    """'4,7' (pt-BR) ou '4.7' -> 4.7"""
    if not texto:
        return None
    m = re.search(r"(\d+[.,]\d+|\d+)", texto)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_avaliacoes(texto: Optional[str]) -> Optional[int]:
    """'(1.234)' ou '1,234 reviews' -> 1234"""
    if not texto:
        return None
    d = re.sub(r"[.,\s]", "", texto)
    m = re.search(r"(\d+)", d)
    return int(m.group(1)) if m else None
