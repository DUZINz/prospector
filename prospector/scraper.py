"""
Coleta estabelecimentos no Google Maps e identifica quais nao tem site proprio.

Roda como CLI e emite NDJSON no stdout (uma linha JSON por evento), para que o
app Streamlit consiga acompanhar o progresso sem misturar o event loop do
Playwright com o do Streamlit:

    python -m prospector.scraper --termo dentista --regiao "Curitiba PR" --max 40

Eventos emitidos:
    {"tipo": "status",  "msg": "..."}
    {"tipo": "progresso", "atual": 3, "total": 40}
    {"tipo": "lead",    "dados": {...}}
    {"tipo": "erro",    "msg": "..."}
    {"tipo": "fim",     "total": 40, "sem_site": 17}
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.parse
from typing import Iterator, Optional

from playwright.sync_api import Error as PWError
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from . import selectors as S
from .models import (
    Lead,
    extrair_place_key,
    normalizar_telefone,
    parse_avaliacoes,
    parse_nota,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Dominios que aparecem no campo "site" mas nao sao site proprio do negocio.
# Um dentista cujo unico link e o Instagram continua sendo lead.
AGREGADORES = {
    "instagram.com", "facebook.com", "fb.com", "m.facebook.com",
    "wa.me", "api.whatsapp.com", "linktr.ee", "linktree.com",
    "bio.link", "beacons.ai", "linkbio.co",
    "doctoralia.com.br", "ifood.com.br", "booksy.com",
    "business.site", "negocio.site",  # sites gerados pelo proprio Google
    "youtube.com", "tiktok.com", "twitter.com", "x.com",
    "google.com", "goo.gl", "maps.app.goo.gl",
}


def emitir(tipo: str, **kwargs) -> None:
    print(json.dumps({"tipo": tipo, **kwargs}, ensure_ascii=False), flush=True)


def dominio(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def e_site_proprio(url: str) -> bool:
    """True apenas se o link for um site de verdade do negocio."""
    if not url:
        return False
    host = dominio(url)
    if not host:
        return False
    return not any(host == a or host.endswith("." + a) for a in AGREGADORES)


def _pausa(base: float = 0.8) -> None:
    """Intervalo irregular entre acoes — carga mais leve e menos padrao robotico."""
    time.sleep(base + random.uniform(0, 0.7))


def _aceitar_consentimento(page) -> None:
    if "consent." not in page.url:
        return
    for sel in S.CONSENT_BUTTONS:
        try:
            botao = page.locator(sel).first
            if botao.count() > 0:
                botao.click(timeout=4000)
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                return
        except (PWTimeout, PWError):
            continue


JS_COLETAR_CARDS = """
(sel) => {
  const feed = document.querySelector(sel.feed);
  if (!feed) return [];
  return Array.from(feed.children).map(div => {
    const a = div.querySelector(sel.link);
    if (!a) return null;
    return {
      nome: a.getAttribute('aria-label') || '',
      url: a.href,
      site_no_card: !!div.querySelector(sel.site),
    };
  }).filter(Boolean);
}
"""

JS_COLETAR_DETALHE = """
(sel) => {
  const q = s => document.querySelector(s);
  const txt = el => (el ? (el.textContent || '').trim() : '');

  const site = q(sel.site);
  const fone = q(sel.fone);
  const bloco = q(sel.nota);
  const spans = bloco ? Array.from(bloco.querySelectorAll('span')) : [];

  return {
    nome: txt(q(sel.titulo)),
    categoria: txt(q(sel.categoria)),
    endereco: (q(sel.endereco)?.getAttribute('aria-label') || txt(q(sel.endereco)))
                .replace(/^Endereço:\\s*/i, '').replace(/^Address:\\s*/i, '').trim(),
    site: site ? site.href : '',
    telefone: fone ? (fone.getAttribute('data-item-id') || '').replace('phone:tel:', '') : '',
    nota: spans.length ? txt(spans[0]) : '',
    avaliacoes: spans.map(s => s.getAttribute('aria-label') || '')
                     .find(t => /avalia|review/i.test(t)) || '',
  };
}
"""

SEL_CARDS = {"feed": S.FEED, "link": S.CARD_LINK, "site": S.CARD_WEBSITE}
SEL_DETALHE = {
    "titulo": S.DETAIL_TITLE,
    "site": S.DETAIL_WEBSITE,
    "fone": S.DETAIL_PHONE,
    "endereco": S.DETAIL_ADDRESS,
    "categoria": S.DETAIL_CATEGORY,
    "nota": S.DETAIL_RATING_BLOCK,
}


def _rolar_feed(page, maximo: int) -> list[dict]:
    """Rola a lista ate carregar `maximo` cards ou o feed parar de crescer."""
    try:
        page.wait_for_selector(S.FEED, timeout=20000)
    except PWTimeout:
        # Busca muito especifica: o Maps pula a lista e abre o local direto.
        if page.locator(S.DETAIL_TITLE).count() > 0:
            emitir("status", msg="Resultado unico — abrindo direto.")
            return [{"nome": "", "url": page.url, "site_no_card": False}]
        emitir("erro", msg="A lista de resultados nao carregou (layout mudou ou bloqueio do Google).")
        return []

    feed = page.locator(S.FEED)
    anterior, parado = 0, 0

    while True:
        cards = page.evaluate(JS_COLETAR_CARDS, SEL_CARDS)
        if len(cards) >= maximo:
            return cards[:maximo]

        if any(page.get_by_text(t, exact=False).count() > 0 for t in S.END_OF_LIST):
            return cards[:maximo]

        if len(cards) == anterior:
            parado += 1
            if parado >= 3:
                return cards[:maximo]
        else:
            parado = 0
            anterior = len(cards)

        emitir("status", msg=f"Carregando resultados... ({len(cards)})")
        feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
        _pausa(1.0)


def _abrir_detalhe(page, url: str) -> Optional[dict]:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_selector(S.DETAIL_TITLE, timeout=15000)
    except (PWTimeout, PWError):
        return None
    _pausa(0.5)
    try:
        return page.evaluate(JS_COLETAR_DETALHE, SEL_DETALHE)
    except PWError:
        return None


def buscar(
    termo: str,
    regiao: str,
    maximo: int = 40,
    headless: bool = True,
    apenas_sem_site: bool = True,
) -> Iterator[Lead]:
    """Busca `termo` em `regiao` e devolve os leads encontrados."""
    consulta = f"{termo} em {regiao}".strip()
    url = "https://www.google.com/maps/search/" + urllib.parse.quote(consulta) + "?hl=pt-BR"

    with sync_playwright() as p:
        navegador = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--lang=pt-BR"],
        )
        ctx = navegador.new_context(
            user_agent=USER_AGENT,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1360, "height": 900},
        )
        page = ctx.new_page()

        try:
            emitir("status", msg=f'Buscando "{consulta}"...')
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            _aceitar_consentimento(page)

            cards = _rolar_feed(page, maximo)
            if not cards:
                return

            # Triagem: quem ja mostra botao "Site" no card raramente e lead.
            # Ainda assim confirmamos no detalhe, porque o card as vezes omite.
            candidatos = cards if not apenas_sem_site else [
                c for c in cards if not c["site_no_card"]
            ]
            emitir(
                "status",
                msg=f"{len(cards)} encontrados — verificando {len(candidatos)} em detalhe.",
            )

            vistos: set[str] = set()
            for i, card in enumerate(candidatos, start=1):
                emitir("progresso", atual=i, total=len(candidatos))

                det = _abrir_detalhe(page, card["url"])
                if not det:
                    emitir("erro", msg=f"Falha ao abrir: {card['nome'] or card['url'][:60]}")
                    continue

                nome = det["nome"] or card["nome"]
                if not nome:
                    continue

                tem_site = e_site_proprio(det["site"])
                if apenas_sem_site and tem_site:
                    continue

                chave = extrair_place_key(page.url, nome, det["endereco"])
                if chave in vistos:
                    continue
                vistos.add(chave)

                e164, whats = normalizar_telefone(det["telefone"])
                yield Lead(
                    place_key=chave,
                    nome=nome,
                    categoria=det["categoria"],
                    endereco=det["endereco"],
                    telefone=det["telefone"],
                    telefone_e164=e164,
                    whatsapp=whats,
                    # Guarda o link mesmo quando e agregador: Instagram e a via
                    # mais provavel de achar e-mail depois.
                    site=det["site"],
                    tem_site=tem_site,
                    nota=parse_nota(det["nota"]),
                    avaliacoes=parse_avaliacoes(det["avaliacoes"]),
                    maps_url=page.url,
                    termo=termo,
                    regiao=regiao,
                )
        finally:
            ctx.close()
            navegador.close()


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Busca leads sem site no Google Maps.")
    ap.add_argument("--termo", required=True, help='Ex.: "dentista", "pet shop"')
    ap.add_argument("--regiao", required=True, help='Ex.: "Curitiba PR"')
    ap.add_argument("--max", type=int, default=40, help="Maximo de resultados na lista")
    ap.add_argument("--todos", action="store_true", help="Traz tambem quem tem site")
    ap.add_argument("--visivel", action="store_true", help="Abre o navegador na tela")
    args = ap.parse_args(argv)

    total = sem_site = 0
    try:
        for lead in buscar(
            termo=args.termo,
            regiao=args.regiao,
            maximo=args.max,
            headless=not args.visivel,
            apenas_sem_site=not args.todos,
        ):
            total += 1
            sem_site += 0 if lead.tem_site else 1
            emitir("lead", dados=lead.to_dict())
    except KeyboardInterrupt:
        emitir("erro", msg="Interrompido pelo usuario.")
    except Exception as exc:  # noqa: BLE001 — o app precisa do erro como evento
        emitir("erro", msg=f"{type(exc).__name__}: {exc}")
        emitir("fim", total=total, sem_site=sem_site)
        return 1

    emitir("fim", total=total, sem_site=sem_site)
    return 0


if __name__ == "__main__":
    sys.exit(main())
