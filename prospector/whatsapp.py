"""Envio real pelo WhatsApp Web: manda o texto e ANEXA o PDF como documento.

O `wa.me` so carrega texto na URL — arquivo nenhum passa por ali. Entao aqui a
gente dirige o WhatsApp Web com o Playwright (que o projeto ja usa no scraper),
num perfil de navegador persistente: voce le o QR uma vez e a sessao fica.

Rodar:
    python -m prospector.whatsapp --login            # 1a vez: ler o QR
    python -m prospector.whatsapp 41999998888 --teste  # envio de verdade

Nao e API oficial. Automatizar o WhatsApp Web em volume alto e caminho conhecido
de bloqueio de numero — use com intervalo e em lote pequeno.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from .models import PITCH_GERAL, TABELA_PDF, preencher, so_digitos

# Perfil do Chromium onde a sessao logada do WhatsApp Web vive. Fora do repo:
# e credencial, nao codigo.
PERFIL = Path.home() / ".prospector-whatsapp"

WEB = "https://web.whatsapp.com"

# --- Seletores do WhatsApp Web -----------------------------------------------
# Mesma logica de `selectors.py`: quando o envio parar de funcionar, o problema
# quase sempre esta AQUI. Abra o WhatsApp Web, inspecione e atualize.
CAIXA_MENSAGEM = 'div[contenteditable="true"][data-tab="10"]'
BOTAO_ANEXAR = (
    'button[title="Anexar"], button[aria-label="Anexar"], '
    'span[data-icon="plus-rounded"], span[data-icon="clip"], '
    'span[data-icon="attach-menu-plus"]'
)
# O input de documento e o unico que NAO restringe a imagem/video.
INPUT_DOCUMENTO = 'input[type="file"]:not([accept*="image"]):not([accept*="video"])'
# Janela de previa que aparece DEPOIS de escolher o arquivo. Sem esperar por ela
# o clique de enviar cai no vazio e o documento fica pendurado — foi exatamente
# o bug de "o texto foi e o PDF nao".
PREVIA_ANEXO = 'div[data-animate-modal-body="true"], div[role="dialog"]'
BOTAO_ENVIAR = 'span[data-icon="send"], span[data-icon="wds-ic-send-filled"], button[aria-label="Enviar"]'
# Confirmacao de que o documento virou mensagem: o balao com o relogio (enviando)
# ou o check (entregue) dentro de uma mensagem de saida.
DOCUMENTO_ENVIADO = 'div.message-out span[data-icon^="msg-"]'
# Some quando a conversa terminou de carregar; enquanto existe, a pagina ainda
# esta montando e digitar cedo demais perde o texto.
CARREGANDO = '[data-testid="chat-loading"]'


def _numero_para_wid(destino: str) -> str:
    """'(41) 99999-8888', '+5541...' ou uma URL wa.me -> '5541999998888'."""
    d = so_digitos(destino)
    if len(d) in (10, 11):  # sem DDI: assume Brasil
        d = "55" + d
    if not d.startswith("55") or len(d) not in (12, 13):
        raise ValueError(f"numero de WhatsApp invalido: {destino!r}")
    return d


def validar_anexo(caminho: Path = TABELA_PDF) -> Path:
    """Garante que o PDF existe e e mesmo um PDF antes de abrir o navegador."""
    caminho = Path(caminho).expanduser().resolve()  # normaliza as barras do Windows
    if not caminho.exists():
        raise FileNotFoundError(f"anexo nao encontrado: {caminho}")
    if caminho.suffix.lower() != ".pdf" or caminho.read_bytes()[:4] != b"%PDF":
        raise ValueError(f"anexo nao e um PDF valido: {caminho}")
    return caminho


def _mandar(page, wid: str, texto: str, arquivo: Path | None) -> None:
    """Uma conversa: abre, manda o texto e sobe o documento.

    Manda em duas mensagens de proposito: a legenda do documento e um campo onde
    Enter dispara, e o pitch tem quebras de linha — colar ali enviaria picado.
    """
    # O ?text= ja deixa o pitch digitado na caixa: um Enter e ele sai.
    page.goto(f"{WEB}/send?phone={wid}&text={_quote(texto)}", wait_until="domcontentloaded")
    try:
        caixa = page.wait_for_selector(CAIXA_MENSAGEM, state="visible")
    except PWTimeout as erro:
        raise RuntimeError(
            "conversa nao abriu — sessao deslogada (rode --login) ou numero sem WhatsApp"
        ) from erro
    page.wait_for_selector(CARREGANDO, state="detached", timeout=15_000)
    caixa.click()
    page.keyboard.press("Enter")

    if arquivo:
        _anexar(page, arquivo)

    # Sem espera a proxima navegacao atropela o envio ainda em transito.
    time.sleep(4)


def _anexar(page, arquivo: Path) -> None:
    """Sobe o documento e so volta quando ele virou mensagem de verdade.

    Cada etapa espera a seguinte aparecer. Se qualquer uma falhar, tira um print
    e levanta: silencio aqui significa lead achando que recebeu a tabela.
    """
    baldes = page.query_selector_all(INPUT_DOCUMENTO)
    if not baldes:
        # O input so entra no DOM depois que o menu do clipe abre.
        page.click(BOTAO_ANEXAR)
        page.wait_for_selector(INPUT_DOCUMENTO, state="attached", timeout=15_000)
        baldes = page.query_selector_all(INPUT_DOCUMENTO)

    enviadas_antes = len(page.query_selector_all(DOCUMENTO_ENVIADO))
    baldes[-1].set_input_files(str(arquivo))  # o ultimo e o de documento; mimetype vem do .pdf

    try:
        previa = page.wait_for_selector(PREVIA_ANEXO, state="visible", timeout=30_000)
        previa.wait_for_selector(BOTAO_ENVIAR, state="visible", timeout=15_000).click()
    except PWTimeout as erro:
        raise RuntimeError(f"a previa do anexo nao abriu — {_print_erro(page)}") from erro

    # Confirmacao: uma mensagem de saida a mais do que antes do upload.
    for _ in range(30):
        if len(page.query_selector_all(DOCUMENTO_ENVIADO)) > enviadas_antes:
            return
        time.sleep(1)
    raise RuntimeError(f"o PDF nao virou mensagem — {_print_erro(page)}")


def _print_erro(page) -> str:
    """Screenshot do estado da tela, para voce ver onde travou."""
    destino = Path.cwd() / f"falha-envio-{int(time.time())}.png"
    try:
        page.screenshot(path=str(destino))
        return f"print em {destino}"
    except Exception:  # navegador ja fechado
        return "sem print"


def enviar_lote(
    itens,
    anexo: Path | None = TABELA_PDF,
    *,
    intervalo: float = 45.0,
    headless: bool = False,
    timeout: int = 90_000,
):
    """Envia varias conversas numa sessao so do navegador.

    `itens` e uma sequencia de (chave, destino, texto) — a chave volta no
    resultado para voce saber qual lead deu certo. Rende (chave, erro) por lead,
    com `erro=None` no sucesso: um numero morto nao derruba o resto da fila.

    `intervalo` e o respiro entre um envio e o outro. Nao mexa para baixo sem
    motivo: rajada de mensagem identica e o que faz o WhatsApp bloquear numero.
    """
    itens = list(itens)
    arquivo = validar_anexo(anexo) if anexo else None

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PERFIL), headless=headless, args=["--disable-blink-features=AutomationControlled"]
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_default_timeout(timeout)
            for i, (chave, destino, texto) in enumerate(itens):
                try:
                    _mandar(page, _numero_para_wid(destino), texto, arquivo)
                    yield chave, None
                except Exception as erro:  # numero invalido, sem WhatsApp, seletor mudado
                    yield chave, erro
                if i < len(itens) - 1:
                    time.sleep(intervalo)
        finally:
            ctx.close()


def enviar(destino: str, texto: str, anexo: Path | None = TABELA_PDF, **kwargs) -> None:
    """Um lead so. Levanta se o envio falhar.

    `destino` aceita telefone em qualquer formato ou a URL wa.me do lead.
    """
    for _, erro in enviar_lote([(None, destino, texto)], anexo, **kwargs):
        if erro:
            raise erro


def _quote(texto: str) -> str:
    from urllib.parse import quote

    return quote(texto, safe="")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("numero", nargs="?", help="telefone do lead (com DDD)")
    ap.add_argument("--nome", default="", help="nome do lead, para a saudacao")
    ap.add_argument("--login", action="store_true", help="abre o WhatsApp Web para ler o QR")
    ap.add_argument("--teste", action="store_true", help="envia de verdade para o numero")
    args = ap.parse_args(argv)

    if args.login:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(PERFIL), headless=False)
            (ctx.pages[0] if ctx.pages else ctx.new_page()).goto(WEB)
            input("Leia o QR e, com as conversas na tela, aperte Enter aqui...")
            ctx.close()
        return 0

    if not args.numero:
        ap.error("informe o numero ou use --login")

    texto = preencher(PITCH_GERAL, {"nome": args.nome})
    anexo = validar_anexo()
    print(f"para   : {_numero_para_wid(args.numero)}")
    print(f"anexo  : {anexo} ({anexo.stat().st_size} bytes)")
    print(f"mensagem:\n{texto}\n")
    if not args.teste:
        print("(dry-run — nada foi enviado; repita com --teste)")
        return 0

    enviar(args.numero, texto, anexo)
    print("enviado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
