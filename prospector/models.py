"""Modelo de lead e normalizacoes (telefone BR, chave de deduplicacao)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import quote

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


# Numeros de servico: nao tem DDD e nao existem no WhatsApp.
PREFIXOS_SERVICO = ("0800", "0300", "0500", "0900", "4004", "3003", "4003", "4003")


def normalizar_telefone(bruto):
    """Devolve (e164, whatsapp_url). Strings vazias se o numero nao for utilizavel.

    Aceita tudo que o Maps devolve: "(41) 99999-8888", "+55 41 3333-2222",
    "0 41 3262-7373" (com o 0 de prefixo nacional), "0800 123 4567".
    """
    d = so_digitos(bruto)
    if not d:
        return "", ""

    if d.startswith(PREFIXOS_SERVICO):
        return d, ""

    # Prefixo nacional/operadora ("0 41 ...", "015 41 ..."): descartavel.
    d = d.lstrip("0")

    # Codigo do pais, com ou sem o 0 que ja tiramos acima.
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]

    if len(d) not in (10, 11):
        return "", ""
    if int(d[:2]) not in DDDS_VALIDOS:
        return "", ""

    e164 = f"+55{d}"
    # Celular (9 digitos apos o DDD, comecando em 9) e o unico que vai pro WhatsApp.
    whats = f"https://wa.me/55{d}" if len(d) == 11 and d[2] == "9" else ""
    return e164, whats


# 1o follow-up (48h depois da 1a mensagem). Reengajamento curto: nao repete a
# apresentacao, retoma o que ja foi enviado e abre espaco para duvida.
ABORDAGEM_FOLLOWUP1 = (
    "Fala{saudacao_nome}! Tudo bem?\n\n"
    "Passando só para saber se você conseguiu dar uma olhada no catálogo e na "
    "tabela de preços que te enviei outro dia.\n\n"
    "Se tiver ficado com alguma dúvida sobre como funcionam os projetos ou "
    "quiser bater um papo rápido sobre alguma demanda da {nome_empresa}, "
    "estou por aqui!"
)

# 2o e ultimo follow-up (72h depois do 1o). Curto, com saida facil: encerrar
# sem constranger deixa a porta aberta para o lead voltar depois.
ABORDAGEM_FOLLOWUP2 = (
    "Última mensagem por aqui, prometo 🙂\n\n"
    "Se não for o momento certo pro {negocio}, sem problema algum — fico à "
    "disposição quando fizer sentido — a tabela de preços continua valendo."
)


# Para quem ja demonstrou interesse em ter um sistema. Nao reapresenta nada:
# vai direto ao proximo passo, que e o escopo.
PITCH_INTERESSE = (
    "Que bom que fez sentido! 🙂\n\n"
    "Para eu montar um escopo do sistema do {negocio}, preciso de três coisas:\n"
    "1. Qual processo o sistema precisa resolver primeiro\n"
    "2. Quantas pessoas vão usar\n"
    "3. Se precisa conversar com algum sistema que vocês já usam\n\n"
    "Com isso eu te devolvo escopo, prazo e valor — sem compromisso."
)

# PDF da tabela de precos. O wa.me so leva texto, entao o anexo e sempre um
# clique manual — aqui a gente so garante que o arquivo existe e entrega ele.
TABELA_PDF = Path(__file__).resolve().parent.parent / "EG-Tabela-de-Precos-2026.2.pdf"

# Template geral: apresentacao ampla de solucoes, com a tabela em anexo. Nao
# depende de o lead ter site ou nao.
PITCH_GERAL = (
    "{saudacao} Tudo bem?\n\n"
    "Me chamo Eduardo Grunitzky, sou desenvolvedor de software e crio soluções "
    "digitais sob medida para empresas — desde sistemas internos de gestão, "
    "automações de processos e IA, até aplicativos e sites de alta conversão.\n\n"
    "🌐 Meu portfólio: https://portfolio-murex-alpha-23.vercel.app/\n"
    "(os projetos lá são modelos de demonstração que montei para exemplificar "
    "o padrão visual e de acabamento)\n\n"
    "O meu modelo de trabalho é direto: escopo e preço fechados, código 100% "
    "seu (sem ficar preso a mensalidades de plataformas) e entrega pronta "
    "rodando no servidor.\n\n"
    "📄 Estou te enviando em anexo a minha Tabela de Preços e Serviços 2026.2, "
    "com prazos e valores transparentes para cada tipo de projeto.\n\n"
    "Se fizer sentido para o momento da {nome_empresa} ou se tiver algum "
    "processo que queira automatizar, fico à disposição para batermos um papo!"
)



# Templates disponiveis na tela, na ordem em que aparecem.
TEMPLATES = {
    "Geral — apresentação + tabela de preços (PDF)": PITCH_GERAL,
    "Interesse demonstrado em sistema": PITCH_INTERESSE,
    "Follow-up 1 — reengajamento (48h)": ABORDAGEM_FOLLOWUP1,
    "Follow-up 2 — encerramento (72h)": ABORDAGEM_FOLLOWUP2,
}


def modelo_inicial(lead: dict) -> str:
    """Abertura unica: o pitch geral serve com ou sem site."""
    return PITCH_GERAL


class _Variaveis(dict):
    """Variavel que o template pede e o lead nao tem vira string vazia.

    Sem isto um `{link_site}` num lead sem site derrubaria o format com KeyError
    no meio da montagem da tabela.
    """

    def __missing__(self, chave: str) -> str:
        return ""


def preencher(modelo: str, lead: dict | None = None, **extras) -> str:
    """Troca as variaveis do template pelos dados do lead.

    Aceita {negocio}, {nome_lead}, {nome_empresa} (todos o nome do negocio: o
    Maps nao separa pessoa de empresa), {link_site}, {saudacao} e
    {saudacao_nome}.
    """
    lead = lead or {}
    nome = (lead.get("nome") or "").strip()
    negocio = nome or "seu negócio"
    variaveis = _Variaveis(
        # Sem nome a saudacao perde a virgula, em vez de virar "Olá, !".
        saudacao=f"Olá, {nome}!" if nome else "Olá!",
        # Vocativo para colar depois de uma palavra: "Fala{saudacao_nome}!"
        # vira "Fala, Padaria Sol!" ou so "Fala!" quando o lead nao tem nome.
        saudacao_nome=f", {nome}" if nome else "",
        negocio=negocio,
        nome_lead=negocio,
        # "da {nome_empresa}" precisa de um fallback feminino que caiba na frase.
        nome_empresa=nome or "sua empresa",
        link_site=lead.get("site") or "",
        **extras,
    )
    return modelo.format_map(variaveis)


def montar_link_whatsapp(lead: dict, modelo: str = PITCH_GERAL) -> str:
    """Link do wa.me com a mensagem ja preenchida com os dados do lead.

    `lead` e o dict do lead (precisa de `nome`, `whatsapp` e, para o pitch de
    sistemas, `site`). Sem WhatsApp valido, sai vazio.
    """
    whatsapp_url = lead.get("whatsapp") or ""
    if not whatsapp_url:
        return ""

    # safe="" para nao deixar passar "/" e "&" do nome do negocio, que quebrariam
    # o parametro. A quebra de linha vira %0A, que o WhatsApp entende.
    texto = quote(preencher(modelo, lead), safe="")
    return f"{whatsapp_url}?text={texto}"


def formatar_telefone(e164, bruto=""):
    """'+5541998941500' -> '(41) 99894-1500'. Cai no valor bruto se nao der."""
    # So formata numero geografico (o normalizador marca esses com "+").
    if not (e164 or "").startswith("+"):
        return bruto or e164 or ""
    d = so_digitos(e164)
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return bruto or e164 or ""


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
