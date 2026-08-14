"""
Prospector — encontra negocios sem site proprio no Google Maps.

Rodar:  streamlit run app.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from prospector import cnpj as receita
from prospector import storage
from prospector.models import Lead, formatar_telefone

RAIZ = Path(__file__).resolve().parent

st.set_page_config(page_title="Prospector — leads sem site", page_icon="🔎", layout="wide")


if "leads" not in st.session_state:
    st.session_state.leads = {}
leads_db = st.session_state.leads


def rodar_busca(termo: str, regiao: str, maximo: int, apenas_sem_site: bool, visivel: bool):
    """Executa o scraper como subprocesso e consome o NDJSON linha a linha.

    Subprocesso, e nao import direto: a API sincrona do Playwright quebra quando
    chamada de dentro da thread do Streamlit (conflito de event loop).
    """
    cmd = [
        sys.executable, "-u", "-m", "prospector.scraper",
        "--termo", termo, "--regiao", regiao, "--max", str(maximo),
    ]
    if not apenas_sem_site:
        cmd.append("--todos")
    if visivel:
        cmd.append("--visivel")

    # PYTHONIOENCODING: sem isso o subprocesso escreve em cp1252 no Windows e os
    # acentos chegam como "Escrit?rio". O `encoding=` abaixo so decodifica.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

    proc = subprocess.Popen(
        cmd, cwd=str(RAIZ), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
    )

    leads: list[Lead] = []
    erros: list[str] = []
    caixa_status = st.empty()
    barra = st.progress(0.0, text="Iniciando...")

    for linha in proc.stdout:
        linha = linha.strip()
        if not linha:
            continue
        try:
            ev = json.loads(linha)
        except json.JSONDecodeError:
            continue

        tipo = ev.get("tipo")
        if tipo == "status":
            caixa_status.info(ev["msg"])
        elif tipo == "progresso":
            atual, total = ev["atual"], max(ev["total"], 1)
            barra.progress(atual / total, text=f"Verificando {atual} de {total}...")
        elif tipo == "lead":
            leads.append(Lead(**ev["dados"]))
        elif tipo == "erro":
            erros.append(ev["msg"])
        elif tipo == "fim":
            barra.progress(1.0, text=f"Concluido — {ev['sem_site']} sem site.")

    proc.wait()
    stderr = (proc.stderr.read() or "").strip()
    if proc.returncode != 0 and stderr:
        erros.append(stderr[-1500:])

    caixa_status.empty()
    return leads, erros


def para_excel(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="leads")
    return buf.getvalue()


# ------------------------------ barra lateral ------------------------------

st.sidebar.header("Nova busca")

termos_txt = st.sidebar.text_area(
    "Categorias (uma por linha)",
    value="dentista\npet shop\nadvogado",
    height=110,
    help="Use os mesmos termos que voce digitaria no Maps.",
)
regioes_txt = st.sidebar.text_area(
    "Cidades / bairros (uma por linha)",
    value="Curitiba PR",
    height=90,
    help="Bairro traz mais resultados que cidade: o Maps corta a lista em ~120 por busca.",
)
maximo = st.sidebar.slider("Maximo de resultados por busca", 20, 120, 40, step=10)
apenas_sem_site = st.sidebar.checkbox("Somente quem nao tem site", value=True)
visivel = st.sidebar.checkbox(
    "Mostrar o navegador", value=False,
    help="Util para ver onde travou quando o Google muda o layout.",
)

if st.sidebar.button("Buscar", type="primary", use_container_width=True):
    termos = [t.strip() for t in termos_txt.splitlines() if t.strip()]
    regioes = [r.strip() for r in regioes_txt.splitlines() if r.strip()]

    if not termos or not regioes:
        st.sidebar.error("Preencha ao menos uma categoria e uma cidade.")
    else:
        total_novos = total_atualizados = 0
        todos_erros: list[str] = []

        for regiao in regioes:
            for termo in termos:
                st.write(f"### {termo} — {regiao}")
                leads, erros = rodar_busca(termo, regiao, maximo, apenas_sem_site, visivel)
                novos, atualizados = storage.salvar(leads_db, leads)
                total_novos += novos
                total_atualizados += atualizados
                todos_erros += erros
                st.caption(f"{novos} novos, {atualizados} ja conhecidos.")

        st.success(f"Busca finalizada: {total_novos} leads novos, {total_atualizados} atualizados.")
        if todos_erros:
            with st.expander(f"{len(todos_erros)} avisos durante a coleta"):
                for e in todos_erros:
                    st.text(e)


st.sidebar.divider()
st.sidebar.header("Enriquecer pela Receita")
st.sidebar.caption(
    "Busca o CNPJ pelo nome e traz **e-mail** e **porte (MEI)** — os dois campos "
    "que o Google Maps nao tem."
)
lote_receita = st.sidebar.slider("Leads por vez", 10, 200, 50, step=10)
enriquecer_agora = st.sidebar.button(
    "Buscar e-mail e CNPJ", use_container_width=True,
    help="Consulta so os leads ainda nao consultados, respeitando os filtros da tela.",
)


def rodar_enriquecimento(filtros: dict, limite: int) -> None:
    """Consulta a Receita lead a lead, gravando cada resultado na hora.

    Gravar a cada lead (e nao no fim) e proposital: a consulta e lenta por causa
    do limite de requisicoes dos provedores, e fechar a aba no meio nao pode
    custar o trabalho ja feito.
    """
    pendentes = storage.pendentes_de_receita(leads_db, limite=limite, **filtros)
    if not pendentes:
        st.info("Nenhum lead pendente com esses filtros — todos ja foram consultados.")
        return

    barra = st.progress(0.0, text=f"0 de {len(pendentes)}...")
    achados = com_email = meis = 0

    for i, r in enumerate(pendentes, start=1):
        try:
            dados = receita.enriquecer(
                nome=r["nome"], endereco=r.get("endereco") or "",
                regiao=r.get("regiao") or "", cnpj=r.get("cnpj") or "",
            )
        except Exception as exc:  # noqa: BLE001 — um lead ruim nao derruba o lote
            st.warning(f"{r['nome']}: {type(exc).__name__}")
            dados = None

        storage.salvar_receita(leads_db, r["place_key"], dados)
        if dados:
            achados += 1
            com_email += 1 if dados.email else 0
            meis += 1 if dados.mei else 0
        barra.progress(i / len(pendentes), text=f"{i} de {len(pendentes)}...")

    barra.empty()
    st.success(
        f"{achados} de {len(pendentes)} identificados na Receita — "
        f"{com_email} com e-mail, {meis} MEI."
    )
    if achados < len(pendentes):
        st.caption(
            f"{len(pendentes) - achados} nao foram identificados. Quase sempre e nome "
            "fantasia muito diferente da razao social. Cole o CNPJ na coluna *CNPJ* "
            "e clique de novo — com o numero em maos ele acerta sempre."
        )


# ------------------------------ painel principal ------------------------------

st.title("🔎 Leads sem site proprio")

f1, f2, f3, f4 = st.columns(4)
with f1:
    filtro_regiao = st.selectbox("Regiao", ["(todas)"] + storage.valores_distintos(leads_db, "regiao"))
with f2:
    filtro_termo = st.selectbox("Categoria", ["(todas)"] + storage.valores_distintos(leads_db, "termo"))
with f3:
    filtro_status = st.multiselect(
        "Status", ["novo", "contatado", "negociando", "fechado", "descartado"],
        default=["novo"],
    )
with f4:
    so_whatsapp = st.checkbox("So com WhatsApp", value=False)
    so_email = st.checkbox("So com e-mail", value=False)
    so_mei = st.checkbox("So MEI", value=False, help="Exige enriquecimento pela Receita.")

registros = storage.listar(
    leads_db,
    regiao=None if filtro_regiao == "(todas)" else filtro_regiao,
    termo=None if filtro_termo == "(todas)" else filtro_termo,
    status=filtro_status or None,
    apenas_sem_site=True,
    com_whatsapp=so_whatsapp,
    com_email=so_email,
    apenas_mei=so_mei,
)

if enriquecer_agora:
    rodar_enriquecimento(
        {
            "regiao": None if filtro_regiao == "(todas)" else filtro_regiao,
            "termo": None if filtro_termo == "(todas)" else filtro_termo,
            "status": filtro_status or None,
            "apenas_sem_site": True,
        },
        lote_receita,
    )
    registros = storage.listar(
        leads_db,
        regiao=None if filtro_regiao == "(todas)" else filtro_regiao,
        termo=None if filtro_termo == "(todas)" else filtro_termo,
        status=filtro_status or None,
        apenas_sem_site=True,
        com_whatsapp=so_whatsapp,
        com_email=so_email,
        apenas_mei=so_mei,
    )

if not registros:
    st.info("Nenhum lead com esses filtros. Faca uma busca na barra lateral.")
    st.stop()

df = pd.DataFrame(registros)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Leads", len(df))
m2.metric("Com WhatsApp", int((df["whatsapp"] != "").sum()))
m3.metric("Com e-mail", int((df.get("email", pd.Series(dtype=str)) != "").sum()))
m4.metric("MEI", int((df.get("mei", pd.Series(dtype=float)) == 1).sum()))
m5.metric("Sem consultar", int((df.get("cnpj_consultado", pd.Series(dtype=str)) == "").sum()))

COLUNAS = [
    "nome", "categoria", "telefone", "whatsapp", "email", "porte", "mei",
    "site", "endereco", "cnpj", "razao_social", "nota", "avaliacoes",
    "status", "observacoes", "maps_url", "place_key",
]
visao = df[COLUNAS].copy()
visao["telefone"] = [
    formatar_telefone(e, b) for e, b in zip(df["telefone_e164"], df["telefone"])
]

editado = st.data_editor(
    visao,
    use_container_width=True,
    hide_index=True,
    height=520,
    # `cnpj` editavel de proposito: quando a busca automatica nao acha, voce cola
    # o numero na mao e o proximo enriquecimento completa o resto.
    disabled=[c for c in COLUNAS if c not in ("status", "observacoes", "cnpj")],
    column_config={
        "nome": st.column_config.TextColumn("Nome", width="medium"),
        "email": st.column_config.TextColumn("E-mail", width="medium"),
        "porte": st.column_config.TextColumn("Porte", width="small"),
        "mei": st.column_config.CheckboxColumn("MEI", width="small"),
        "cnpj": st.column_config.TextColumn("CNPJ", width="small", help="Cole aqui se o automatico nao achar."),
        "razao_social": st.column_config.TextColumn("Razao social", width="medium"),
        "telefone": st.column_config.TextColumn("Telefone", width="small"),
        "whatsapp": st.column_config.LinkColumn("WhatsApp", display_text="abrir"),
        # Preenchido = tem Instagram/link, mas nao site proprio.
        "site": st.column_config.LinkColumn("Link social", display_text="ver"),
        "maps_url": st.column_config.LinkColumn("Maps", display_text="mapa"),
        "nota": st.column_config.NumberColumn("Nota", format="%.1f", width="small"),
        "avaliacoes": st.column_config.NumberColumn("Aval.", width="small"),
        "status": st.column_config.SelectboxColumn(
            "Status", options=["novo", "contatado", "negociando", "fechado", "descartado"],
        ),
        "observacoes": st.column_config.TextColumn("Notas", width="medium"),
        "place_key": None,
    },
    key="tabela",
)

c1, c2, c3 = st.columns([1, 1, 3])

with c1:
    if st.button("Salvar alteracoes", type="primary", use_container_width=True):
        alterados = 0
        for antes, depois in zip(visao.itertuples(), editado.itertuples()):
            mudou = (
                antes.status != depois.status
                or antes.observacoes != depois.observacoes
            )
            if mudou:
                storage.atualizar_status(
                    leads_db, depois.place_key, depois.status, depois.observacoes or ""
                )
            if (antes.cnpj or "") != (depois.cnpj or ""):
                leads_db[depois.place_key]["cnpj"] = receita.so_digitos(depois.cnpj)
                leads_db[depois.place_key]["cnpj_consultado"] = ""
                mudou = True
            alterados += 1 if mudou else 0
        st.success(f"{alterados} lead(s) atualizados.") if alterados else st.info("Nada mudou.")
        st.rerun()

exportar = editado.drop(columns=["place_key"])
with c2:
    st.download_button(
        "Excel", para_excel(exportar), "leads_sem_site.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with c3:
    st.download_button(
        "CSV", exportar.to_csv(index=False).encode("utf-8-sig"),
        "leads_sem_site.csv", "text/csv",
    )

st.caption(
    "O Google Maps nao guarda e-mail de empresa — nenhuma fonte do Maps traz esse campo. "
    "Quando a coluna *Link social* estiver preenchida, o e-mail costuma estar na bio do Instagram."
)
