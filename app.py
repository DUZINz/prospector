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
from prospector import funil
from prospector import storage
from prospector import whatsapp as zap
from prospector.models import (
    ABORDAGEM_FOLLOWUP1,
    ABORDAGEM_FOLLOWUP2,
    TABELA_PDF,
    TEMPLATES,
    Lead,
    formatar_telefone,
    modelo_inicial,
    montar_link_whatsapp,
    preencher,
)

RAIZ = Path(__file__).resolve().parent

st.set_page_config(page_title="Prospector — leads", page_icon="🔎", layout="wide")


if "leads" not in st.session_state:
    st.session_state.leads = {}
leads_db = st.session_state.leads


@st.cache_resource
def _con_funil():
    """Conexao unica com funil.db — o unico dado que sobrevive entre sessoes."""
    return funil.conectar()


con_funil = _con_funil()

# Status que a tela oferece. Os tres primeiros o funil move sozinho a cada
# envio (ver funil.STATUS_POR_ESTAGIO); os tres seguintes voce marca na mao e
# eles congelam a cadencia. Os ultimos sao valores antigos do banco: ficam na
# lista so para o selectbox nao quebrar em quem ja tem esse status gravado.
STATUS_OPCOES = [
    "novo", "primeiro_contato_enviado", "followup_enviado",
    "respondeu", "interessado", "arquivado",
    "contatado", "negociando", "fechado", "descartado",
]

# Qual mensagem cada acao carrega, e como ela aparece na tabela.
MODELO_DA_ACAO = {
    # None: a 1a mensagem vem de `modelo_inicial` (o pitch geral, com a tabela).
    "inicial": None,
    "followup1": ABORDAGEM_FOLLOWUP1,
    "followup2": ABORDAGEM_FOLLOWUP2,
}
ROTULO_DA_ACAO = {
    "inicial": "1ª mensagem",
    "followup1": "follow-up 1",
    "followup2": "follow-up 2",
}


def modelo_do_lead(acao: str, lead: dict) -> str:
    """Mensagem da vez para esse lead."""
    return MODELO_DA_ACAO[acao] or modelo_inicial(lead)


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
apenas_sem_site = st.sidebar.checkbox(
    "Somente quem nao tem site", value=True,
    help="Vale para a coleta. Desmarque para trazer tambem quem ja tem site e "
         "poder oferecer sistema — o filtro *Site* da tela separa os dois.",
)
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
    do limite de requisicoes dos provedores, e interromper no meio nao pode
    custar o que ja foi consultado. (Fechar a aba ainda perde tudo — os leads
    vivem so em st.session_state.)
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

st.title("🔎 Prospecção de leads")

FILTRO_SITE = {"Sem site": False, "Com site": True, "Todos": None}

f1, f2, f3, f4, f5 = st.columns(5)
with f1:
    filtro_regiao = st.selectbox("Regiao", ["(todas)"] + storage.valores_distintos(leads_db, "regiao"))
with f2:
    filtro_termo = st.selectbox("Categoria", ["(todas)"] + storage.valores_distintos(leads_db, "termo"))
with f3:
    filtro_status = st.multiselect("Status", STATUS_OPCOES, default=["novo"])
with f4:
    filtro_site = st.selectbox(
        "Site", list(FILTRO_SITE), index=0,
        help="Sem site: oferta de landing page/site. Com site: oferta de "
             "sistema, automação, painel ou API.",
    )
with f5:
    so_whatsapp = st.checkbox("So com WhatsApp", value=False)
    so_email = st.checkbox("So com e-mail", value=False)
    so_mei = st.checkbox("So MEI", value=False, help="Exige enriquecimento pela Receita.")
    so_followup = st.checkbox(
        "So aptos p/ follow-up", value=False,
        help=f"Ja receberam mensagem e o prazo venceu "
             f"({funil.HORAS_ATE_FOLLOWUP1}h apos a 1a, "
             f"{funil.HORAS_ATE_FOLLOWUP2}h apos o 1o follow-up).",
    )

# Historico do funil por cima da sessao, ANTES de filtrar: sem isso um lead
# que voce ja moveu para "contatado" voltaria como "novo" depois de refazer a
# busca, e o filtro de status olharia o valor errado.
funil.aplicar_em_sessao(con_funil, leads_db)

filtros = {
    "regiao": None if filtro_regiao == "(todas)" else filtro_regiao,
    "termo": None if filtro_termo == "(todas)" else filtro_termo,
    "status": filtro_status or None,
    "tem_site": FILTRO_SITE[filtro_site],
    "com_whatsapp": so_whatsapp,
    "com_email": so_email,
    "apenas_mei": so_mei,
}
registros = storage.listar(leads_db, **filtros)

if enriquecer_agora:
    rodar_enriquecimento(filtros, lote_receita)
    registros = storage.listar(leads_db, **filtros)

# Fora do storage.listar de proposito: aptidao a follow-up depende do relogio
# e do funil, nao dos campos do lead — e o storage nao conhece o funil.
if so_followup:
    registros = [r for r in registros if funil.apto_a_followup(r)]

if not registros:
    st.info("Nenhum lead com esses filtros. Faca uma busca na barra lateral.")
    st.stop()

df = pd.DataFrame(registros)

# Acao da vez de cada lead: qual mensagem sai agora, ou quantos dias faltam.
acoes = [
    funil.acao_da_vez(r.get("estagio_contato", 0), r.get("data_ultimo_contato", ""))
    for r in registros
]

# A fila e a metrica olham TODOS os leads da sessao, nao o recorte da tabela.
# Motivo: assim que voce marca uma mensagem como enviada o lead vira
# "contatado" e sai do filtro padrao ("novo") — se a fila respeitasse o filtro,
# nenhum follow-up apareceria nela justamente no dia de mandar.
# So entra quem tem WhatsApp valido: sem numero nao ha o que abrir.
prontos = [
    (r, funil.acao_da_vez(r.get("estagio_contato", 0), r.get("data_ultimo_contato", ""))[0])
    for r in storage.listar(leads_db)
]
prontos = [(r, acao) for r, acao in prontos if acao in MODELO_DA_ACAO and r.get("whatsapp")]

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Leads", len(df))
m2.metric("Com WhatsApp", int((df["whatsapp"] != "").sum()))
m3.metric(
    "Prontos p/ enviar", len(prontos),
    help="Leads com mensagem liberada agora (1ª ou follow-up vencido). "
         "Conta todos os leads da sessão, independente dos filtros acima.",
)
m4.metric("Com e-mail", int((df.get("email", pd.Series(dtype=str)) != "").sum()))
m5.metric("MEI", int((df.get("mei", pd.Series(dtype=float)) == 1).sum()))
m6.metric("Sem consultar", int((df.get("cnpj_consultado", pd.Series(dtype=str)) == "").sum()))

COLUNAS = [
    "nome", "categoria", "telefone", "whatsapp", "situacao", "enviei_agora",
    "email", "porte", "mei", "site", "endereco", "cnpj", "razao_social",
    "nota", "avaliacoes", "status", "observacoes", "maps_url", "place_key",
]

# `situacao` e `enviei_agora` sao colunas de tela, montadas aqui.
df["situacao"] = ""
df["enviei_agora"] = False

visao = df[COLUNAS].copy()
visao["telefone"] = [
    formatar_telefone(e, b) for e, b in zip(df["telefone_e164"], df["telefone"])
]

# A coluna WhatsApp so vira link quando ha mensagem liberada. Enquanto o lead
# esta no prazo de espera, ou ja recebeu as tres, o link fica vazio e quem
# explica o porque e a coluna `situacao` ao lado — LinkColumn nao sabe exibir
# texto comum sem virar um link quebrado.
links, situacoes = [], []
for registro, (acao, faltam) in zip(registros, acoes):
    url = registro.get("whatsapp") or ""
    if not url:
        links.append("")
        situacoes.append("sem WhatsApp")
    elif acao in MODELO_DA_ACAO:
        links.append(montar_link_whatsapp(registro, modelo_do_lead(acao, registro)))
        situacoes.append(f"pronto · {ROTULO_DA_ACAO[acao]}")
    elif acao == "aguardando":
        links.append("")
        situacoes.append(f"aguardando ({faltam}h)")
    else:
        links.append("")
        situacoes.append("sequência concluída")

visao["whatsapp"] = links
visao["situacao"] = situacoes

# ------------------------------ fila de hoje ------------------------------

if prontos:
    # Do mais atrasado para o mais recente: quem esperou mais fura a fila.
    # A 1a mensagem nao tem atraso (nunca foi contatado), entao fica no fim.
    fila = sorted(
        (
            {
                "nome": r["nome"],
                "lead": r,
                "rotulo": ROTULO_DA_ACAO[acao],
                "texto": preencher(modelo_do_lead(acao, r), r),
                "link": montar_link_whatsapp(r, modelo_do_lead(acao, r)),
                "atraso": funil.atraso_em_horas(
                    r.get("estagio_contato", 0), r.get("data_ultimo_contato", "")
                ),
            }
            for r, acao in prontos
        ),
        key=lambda i: i["atraso"],
        reverse=True,
    )

    with st.expander(f"📤 Fila de hoje — {len(fila)} mensagem(ns) pronta(s)", expanded=False):
        st.caption(
            "Esta fila ignora os filtros da tabela — ela é a lista do dia inteiro."
        )

        # --- envio automatico, com o PDF anexado ---
        # Uma sessao de navegador para o lote inteiro; quem envia e o WhatsApp
        # Web dirigido pelo Playwright, entao o PDF sobe como documento mesmo.
        col_qtd, col_int = st.columns(2)
        quantos = col_qtd.number_input(
            "Enviar quantos agora", 1, min(len(fila), 50), min(len(fila), 10),
            help="Comece pequeno. Lote grande de mensagem igual é o que derruba número.",
        )
        # Botao de calibragem: o numero certo depende da idade e do histórico do
        # seu chip. Se começar a cair entrega, aumente antes de reduzir volume.
        intervalo = col_int.number_input("Segundos entre um envio e outro", 10, 300, 45)

        if not TABELA_PDF.exists():
            st.error(f"PDF não encontrado em {TABELA_PDF} — o envio sairia sem o anexo.")
        elif st.button(f"📎 Enviar {quantos} com o PDF anexado", type="primary"):
            lote = fila[: int(quantos)]
            barra = st.progress(0.0, "abrindo o WhatsApp Web...")
            enviados, falhas = 0, []
            itens = [(i, it["lead"]["whatsapp"], it["texto"]) for i, it in enumerate(lote)]
            for feitos, (i, erro) in enumerate(
                zap.enviar_lote(itens, intervalo=float(intervalo)), start=1
            ):
                item = lote[i]
                if erro:
                    falhas.append(f"{item['nome']}: {erro}")
                else:
                    # So carimba o funil depois do envio confirmado — assim uma
                    # falha no meio do lote nao "queima" o lead.
                    registro = funil.registrar_envio(con_funil, item["lead"])
                    for campo in funil.CAMPOS_MESCLADOS:
                        leads_db[item["lead"]["place_key"]][campo] = registro[campo]
                    enviados += 1
                barra.progress(feitos / len(lote), f"{feitos} de {len(lote)} — {item['nome']}")
            barra.empty()
            st.success(f"{enviados} enviado(s) com {TABELA_PDF.name}.")
            for falha in falhas:
                st.warning(falha)
            st.caption("Sessão nova? Rode `python -m prospector.whatsapp --login` uma vez.")

        st.divider()

        for item in fila[:50]:
            atraso = f" · {item['atraso']}h de atraso" if item["atraso"] else ""
            col_a, col_b = st.columns([4, 1])
            col_a.markdown(f"**{item['nome']}** — {item['rotulo']}{atraso}")
            col_b.markdown(f"[abrir]({item['link']})")

        if len(fila) > 50:
            st.caption(f"...e mais {len(fila) - 50}. Use os filtros para trabalhar em lotes.")

        st.divider()
        st.caption("Ou abra as conversas e envie na mão — aqui o PDF vai no clipe.")
        # window.open em sequencia, com folga entre um e outro: disparar tudo no
        # mesmo instante faz o navegador tratar como enxurrada de pop-up.
        urls_json = json.dumps([i["link"] for i in fila[:50]])
        # st.html (e nao um iframe): rodando na propria pagina, o window.open
        # sai de um clique real do usuario, que e o que o bloqueador de pop-up
        # aceita. Dentro de iframe com sandbox ele barraria tudo.
        st.html(
            f"""
            <button id="abrir-tudo" style="
                padding: 0.6rem 1rem; font-size: 0.9rem; font-weight: 600;
                cursor: pointer; border-radius: 6px; border: 1px solid #d0d0d0;
                background: #fff;">
              Abrir todos em novas abas ({len(fila[:50])})
            </button>
            <span id="andamento" style="margin-left: 0.75rem; font-size: 0.85rem;
                  font-family: sans-serif; color: #555;"></span>
            <script>
              const urls = {urls_json};
              const botao = document.getElementById('abrir-tudo');
              const andamento = document.getElementById('andamento');
              botao.addEventListener('click', () => {{
                botao.disabled = true;
                let bloqueadas = 0;
                urls.forEach((url, i) => {{
                  setTimeout(() => {{
                    const aba = window.open(url, '_blank');
                    if (!aba) bloqueadas++;
                    andamento.textContent = `${{i + 1}} de ${{urls.length}}` +
                      (bloqueadas ? ` — ${{bloqueadas}} bloqueada(s) pelo navegador` : '');
                    if (i === urls.length - 1) botao.disabled = false;
                  }}, i * 400);
                }});
              }});
            </script>
            """,
            unsafe_allow_javascript=True,
        )
        st.caption(
            "⚠️ Na primeira vez o navegador vai pedir permissão de pop-up — é o "
            "comportamento normal ao abrir várias abas de uma vez. Permita para "
            "`web.whatsapp.com` e clique de novo."
        )

# ------------------------------ mensagens prontas ------------------------------

# Copia rapida fora do fluxo do funil: escolha o lead, escolha o pitch, copie.
# O botao de copiar e o nativo do st.code — nao ha JS proprio aqui.
with st.expander("💬 Mensagens prontas", expanded=False):
    # Selecionado pela place_key, nao pelo dict: o lead muda de status durante a
    # sessao e o Streamlit perderia a selecao ao comparar dicts diferentes.
    por_chave = {r["place_key"]: r for r in registros}
    lead_escolhido = por_chave[
        st.selectbox(
            "Lead", list(por_chave),
            format_func=lambda k: f"{por_chave[k]['nome']} — "
                                  f"{'com site' if por_chave[k]['tem_site'] else 'sem site'}",
        )
    ]
    nome_modelo = st.selectbox(
        "Template", list(TEMPLATES),
        help="Variáveis: {saudacao}, {nome_lead}, {nome_empresa}, {negocio}, {link_site}.",
    )
    modelo = TEMPLATES[nome_modelo]

    st.code(preencher(modelo, lead_escolhido), language=None, wrap_lines=True)

    link_direto = montar_link_whatsapp(lead_escolhido, modelo)
    if link_direto:
        st.markdown(f"[Abrir no WhatsApp com essa mensagem]({link_direto})")
    else:
        st.caption("Sem WhatsApp válido — copie o texto acima e envie por e-mail.")

    # O link acima leva so o texto. Para o PDF sair junto, quem envia e o
    # Playwright dirigindo o WhatsApp Web (perfil logado uma vez com --login).
    if "anexo" in modelo and link_direto:
        if not TABELA_PDF.exists():
            st.error(f"PDF não encontrado em {TABELA_PDF} — a mensagem cita um anexo que não existe.")
        elif st.button("📤 Enviar com o PDF anexado", type="primary"):
            with st.spinner("Abrindo o WhatsApp Web e enviando..."):
                try:
                    zap.enviar(link_direto, preencher(modelo, lead_escolhido))
                    st.success(f"Mensagem + {TABELA_PDF.name} enviados.")
                except Exception as erro:  # rede, seletor mudado, sessao caida
                    st.error(f"Não enviou: {erro}")
                    st.caption("Sessão nova? Rode `python -m prospector.whatsapp --login` uma vez.")
        st.download_button(
            "📄 Baixar a tabela (envio manual)",
            TABELA_PDF.read_bytes(),
            file_name=TABELA_PDF.name,
            mime="application/pdf",
        )

editado = st.data_editor(
    visao,
    use_container_width=True,
    hide_index=True,
    height=520,
    # `cnpj` editavel de proposito: quando a busca automatica nao acha, voce cola
    # o numero na mao e o proximo enriquecimento completa o resto.
    disabled=[
        c for c in COLUNAS
        if c not in ("status", "observacoes", "cnpj", "enviei_agora")
    ],
    column_config={
        "nome": st.column_config.TextColumn("Nome", width="medium"),
        "situacao": st.column_config.TextColumn(
            "Situação", width="small",
            help="Em que ponto da sequência o lead está.",
        ),
        "enviei_agora": st.column_config.CheckboxColumn(
            "Enviei essa mensagem", width="small",
            help="Marque depois de enviar e clique em Salvar: avança o estágio "
                 "e agenda o próximo follow-up.",
        ),
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
        "status": st.column_config.SelectboxColumn("Status", options=STATUS_OPCOES),
        "observacoes": st.column_config.TextColumn("Notas", width="medium"),
        "place_key": None,
    },
    key="tabela",
)

c1, c2, c3 = st.columns([1, 1, 3])

with c1:
    if st.button("Salvar alteracoes", type="primary", use_container_width=True):
        alterados = enviados = 0
        for antes, depois in zip(visao.itertuples(), editado.itertuples()):
            lead = leads_db.get(depois.place_key)
            if lead is None:
                continue

            mudou = (
                antes.status != depois.status
                or antes.observacoes != depois.observacoes
            )
            if mudou:
                storage.atualizar_status(
                    leads_db, depois.place_key, depois.status, depois.observacoes or ""
                )
            if (antes.cnpj or "") != (depois.cnpj or ""):
                lead["cnpj"] = receita.so_digitos(depois.cnpj)
                lead["cnpj_consultado"] = ""
                mudou = True

            if depois.enviei_agora:
                # Avanca o estagio e carimba a data no banco, devolvendo o
                # registro para a sessao refletir sem reconsultar.
                registro = funil.registrar_envio(con_funil, lead)
                for campo in funil.CAMPOS_MESCLADOS:
                    lead[campo] = registro[campo]
                enviados += 1
                mudou = True
            elif mudou:
                # Status/notas editados na mao tambem precisam sobreviver ao
                # fechar da aba — mas sem mexer no estagio do funil.
                funil.registrar_edicao(con_funil, lead)

            alterados += 1 if mudou else 0

        if enviados:
            st.success(
                f"{alterados} lead(s) atualizados — {enviados} marcado(s) como enviado(s). "
                "O próximo follow-up já está agendado."
            )
        elif alterados:
            st.success(f"{alterados} lead(s) atualizados.")
        else:
            st.info("Nada mudou.")
        st.rerun()

exportar = editado.drop(columns=["place_key"])
with c2:
    st.download_button(
        "Excel", para_excel(exportar), "leads.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with c3:
    st.download_button(
        "CSV", exportar.to_csv(index=False).encode("utf-8-sig"),
        "leads.csv", "text/csv",
    )

st.caption(
    "O Google Maps nao guarda e-mail de empresa — nenhuma fonte do Maps traz esse campo. "
    "Quando a coluna *Link social* estiver preenchida, o e-mail costuma estar na bio do Instagram."
)
