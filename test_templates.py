"""Checagem minima da filtragem por site e dos templates de mensagem.

Rodar:  python test_templates.py
"""

from pathlib import Path

from prospector import storage
from prospector import whatsapp as zap
from prospector.models import (
    PITCH_GERAL,
    PITCH_INTERESSE,
    TABELA_PDF,
    TEMPLATES,
    modelo_inicial,
    montar_link_whatsapp,
    preencher,
)


def _lead(place_key, nome, tem_site, site="", whatsapp=""):
    return {
        "place_key": place_key, "nome": nome, "tem_site": tem_site, "site": site,
        "whatsapp": whatsapp, "status": "novo", "regiao": "Curitiba PR",
        "termo": "dentista", "email": "", "mei": None, "cnpj_consultado": "",
        "avaliacoes": 10,
    }


BASE = {
    "a": _lead("a", "Clinica A", False, whatsapp="https://wa.me/5541999998888"),
    "b": _lead("b", "Clinica B", True, site="https://clinicab.com.br"),
}


def test_filtro_por_site():
    assert [r["place_key"] for r in storage.listar(BASE, tem_site=False)] == ["a"]
    assert [r["place_key"] for r in storage.listar(BASE, tem_site=True)] == ["b"]
    assert len(storage.listar(BASE, tem_site=None)) == 2
    assert len(storage.listar(BASE)) == 2  # sem o filtro = todos


def test_abertura_e_sempre_o_pitch_geral():
    assert modelo_inicial(BASE["a"]) is PITCH_GERAL
    assert modelo_inicial(BASE["b"]) is PITCH_GERAL


def test_sem_texto_legado():
    # O pitch antigo de "voces nao tem site" nao pode voltar.
    fonte = Path("prospector/models.py").read_text(encoding="utf-8")
    for trecho in ("site à altura", "Crio sites sob medida"):
        assert trecho not in fonte, trecho
    # O portfolio, esse sim, faz parte da copy nova.
    assert "portfolio-murex-alpha-23" in PITCH_GERAL


def test_envio_valida_antes_de_abrir_o_navegador():
    assert zap.validar_anexo() == TABELA_PDF.resolve()
    assert zap._numero_para_wid("(41) 99894-1500") == "5541998941500"
    assert zap._numero_para_wid("https://wa.me/5541999998888") == "5541999998888"
    for ruim in ("123", "", "abc"):
        try:
            zap._numero_para_wid(ruim)
        except ValueError:
            continue
        raise AssertionError(f"aceitou numero invalido: {ruim!r}")
    try:
        zap.validar_anexo(Path("nao-existe.pdf"))
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("aceitou anexo inexistente")


def test_variaveis():
    texto = preencher("{nome_lead}|{nome_empresa}|{negocio}|{link_site}", BASE["b"])
    assert texto == "Clinica B|Clinica B|Clinica B|https://clinicab.com.br"
    # Lead sem site nao pode derrubar um template que pede {link_site}.
    assert preencher("[{link_site}]", BASE["a"]) == "[]"
    # Variavel que ninguem conhece vira vazio em vez de KeyError.
    assert preencher("[{inexistente}]", BASE["a"]) == "[]"
    assert "seu negócio" in preencher("Sobre o {negocio}", {})


def test_todos_os_templates_preenchem():
    for nome, modelo in TEMPLATES.items():
        for lead in BASE.values():
            assert "{" not in preencher(modelo, lead), nome
    assert PITCH_INTERESSE in TEMPLATES.values()


def test_pitch_geral():
    com_nome = preencher(PITCH_GERAL, BASE["b"])
    assert com_nome.startswith("Olá, Clinica B! Tudo bem?")
    # Sem nome a saudacao nao pode virar "Olá, !" nem "Olá, seu negócio!".
    for vazio in ({}, {"nome": ""}, {"nome": None}, {"nome": "   "}):
        assert preencher(PITCH_GERAL, vazio).startswith("Olá! Tudo bem?")
    assert PITCH_GERAL in TEMPLATES.values()


def test_pdf_da_tabela_existe():
    assert TABELA_PDF.exists(), TABELA_PDF
    assert TABELA_PDF.name == "EG-Tabela-de-Precos-2026.2.pdf"
    assert TABELA_PDF.read_bytes()[:4] == b"%PDF"


def test_lote_isola_falha(monkeypatch=None):
    """Um numero morto no meio da fila nao pode levar o resto junto."""
    class _Ctx:
        pages = []
        def new_page(self):  # noqa: D102
            return type("P", (), {"set_default_timeout": lambda *a: None})()
        def close(self):  # noqa: D102
            pass

    class _PW:
        chromium = type("C", (), {"launch_persistent_context": lambda *a, **k: _Ctx()})()
        def __enter__(self):  # noqa: D105
            return self
        def __exit__(self, *a):  # noqa: D105
            return False

    zap.sync_playwright = lambda: _PW()
    zap.time.sleep = lambda s: None
    def _falso(page, wid, texto, arquivo):
        if wid.endswith("0000"):
            raise RuntimeError("sem WhatsApp")
    zap._mandar = _falso

    itens = [("a", "41999990000", "oi"), ("b", "41999991111", "oi")]
    assert [(c, e is None) for c, e in zap.enviar_lote(itens, intervalo=0)] == [
        ("a", False), ("b", True)
    ]


def test_link_whatsapp():
    link = montar_link_whatsapp(BASE["a"])
    assert link.startswith("https://wa.me/5541999998888?text=")
    assert "Clinica%20A" in link
    assert "%0A" in link  # quebras de linha escapadas
    assert montar_link_whatsapp(BASE["b"]) == ""  # sem WhatsApp, sem link


if __name__ == "__main__":
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"ok  {nome}")
    print("tudo passou")
