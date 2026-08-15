"""
Funil de contato — o unico dado do prospector que sobrevive entre sessoes.

Os leads do Maps vivem em `st.session_state` e somem ao fechar a aba (ver
`storage.py`), e esta certo: sao resultado de busca, refazer e barato. Mas
"quem eu ja abordei e quando" nao pode sumir — sem isso voce manda a mesma
primeira mensagem duas vezes para o mesmo negocio.

Por isso aqui tem SQLite, num arquivo separado e pequeno (`funil.db`), com so
o que o funil precisa. O arquivo guarda nome e telefone reais de quem foi
abordado: e dado sensivel, esta no .gitignore e nao deve ser versionado.

A sequencia de contato tem 3 mensagens e termina:

    estagio 0  nunca contatado          -> manda a abordagem inicial
    estagio 1  1a mensagem enviada      -> espera DIAS_ATE_FOLLOWUP1
    estagio 2  1o follow-up enviado     -> espera DIAS_ATE_FOLLOWUP2
    estagio 3  2o follow-up enviado     -> encerrado, nao insiste mais
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Dias de espera antes de liberar a proxima mensagem. Ajuste aqui.
DIAS_ATE_FOLLOWUP1 = 4  # apos a 1a mensagem
DIAS_ATE_FOLLOWUP2 = 6  # apos o 1o follow-up (~10 dias desde o inicio)

ESTAGIO_FINAL = 3  # sequencia encerrada

BANCO = Path(__file__).resolve().parent / "funil.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS contatos (
    place_key             TEXT PRIMARY KEY,
    nome                  TEXT NOT NULL,
    whatsapp              TEXT DEFAULT '',
    regiao                TEXT DEFAULT '',
    termo                 TEXT DEFAULT '',
    status                TEXT DEFAULT 'contatado',
    observacoes           TEXT DEFAULT '',
    estagio_contato       INTEGER DEFAULT 0,
    data_primeiro_contato TEXT DEFAULT '',
    data_ultimo_contato   TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_contatos_estagio ON contatos(estagio_contato);
"""

# Campos que o funil manda de volta para a sessao, sobrescrevendo o que veio
# da busca. Sao os campos "seus", nao do scraper.
CAMPOS_MESCLADOS = (
    "status",
    "observacoes",
    "estagio_contato",
    "data_primeiro_contato",
    "data_ultimo_contato",
)


def conectar(caminho: Path | str = BANCO) -> sqlite3.Connection:
    # check_same_thread=False: o Streamlit reusa a conexao entre threads de
    # script run. O acesso e serializado por ele, que roda um script por vez.
    con = sqlite3.connect(str(caminho), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# ------------------------------------------------------------------ leitura


def buscar(con: sqlite3.Connection, place_key: str) -> Optional[dict]:
    linha = con.execute(
        "SELECT * FROM contatos WHERE place_key = ?", (place_key,)
    ).fetchone()
    return dict(linha) if linha else None


def todos(con: sqlite3.Connection) -> dict[str, dict]:
    """Tudo de uma vez, indexado por place_key — evita N consultas no merge."""
    return {
        r["place_key"]: dict(r)
        for r in con.execute("SELECT * FROM contatos")
    }


# ------------------------------------------------------------------ escrita


def upsert(con: sqlite3.Connection, dados: dict) -> None:
    """Insere ou atualiza um lead no funil. Espera as chaves do schema."""
    con.execute(
        """INSERT INTO contatos (
               place_key, nome, whatsapp, regiao, termo, status, observacoes,
               estagio_contato, data_primeiro_contato, data_ultimo_contato)
           VALUES (:place_key, :nome, :whatsapp, :regiao, :termo, :status,
                   :observacoes, :estagio_contato, :data_primeiro_contato,
                   :data_ultimo_contato)
           ON CONFLICT(place_key) DO UPDATE SET
               nome=excluded.nome,
               whatsapp=excluded.whatsapp,
               regiao=excluded.regiao,
               termo=excluded.termo,
               status=excluded.status,
               observacoes=excluded.observacoes,
               estagio_contato=excluded.estagio_contato,
               data_primeiro_contato=excluded.data_primeiro_contato,
               data_ultimo_contato=excluded.data_ultimo_contato""",
        {
            "place_key": dados["place_key"],
            "nome": dados.get("nome") or "",
            "whatsapp": dados.get("whatsapp") or "",
            "regiao": dados.get("regiao") or "",
            "termo": dados.get("termo") or "",
            "status": dados.get("status") or "contatado",
            "observacoes": dados.get("observacoes") or "",
            "estagio_contato": int(dados.get("estagio_contato") or 0),
            "data_primeiro_contato": dados.get("data_primeiro_contato") or "",
            "data_ultimo_contato": dados.get("data_ultimo_contato") or "",
        },
    )
    con.commit()


def registrar_envio(con: sqlite3.Connection, lead: dict, quando: str = "") -> dict:
    """Marca que a mensagem da vez foi enviada: avanca o estagio e carimba a data.

    Devolve o registro atualizado (ja gravado), para o chamador refletir na
    sessao sem precisar reconsultar.
    """
    hoje = quando or date.today().isoformat()
    atual = buscar(con, lead["place_key"]) or {}

    estagio = int(atual.get("estagio_contato") or lead.get("estagio_contato") or 0) + 1
    primeiro = atual.get("data_primeiro_contato") or lead.get("data_primeiro_contato") or hoje

    status = lead.get("status") or atual.get("status") or "novo"
    # Quem recebeu mensagem nao e mais "novo" — avanca sozinho, mas nao
    # atropela um status que voce ja moveu na mao (negociando, fechado...).
    if status == "novo" and estagio >= 1:
        status = "contatado"

    registro = {
        "place_key": lead["place_key"],
        "nome": lead.get("nome") or atual.get("nome") or "",
        "whatsapp": lead.get("whatsapp") or atual.get("whatsapp") or "",
        "regiao": lead.get("regiao") or atual.get("regiao") or "",
        "termo": lead.get("termo") or atual.get("termo") or "",
        "status": status,
        "observacoes": lead.get("observacoes") or atual.get("observacoes") or "",
        "estagio_contato": estagio,
        "data_primeiro_contato": primeiro,
        "data_ultimo_contato": hoje,
    }
    upsert(con, registro)
    return registro


def registrar_edicao(con: sqlite3.Connection, lead: dict) -> None:
    """Grava status/observacoes editados na mao, sem mexer no estagio.

    So persiste quem ja esta no funil ou quem saiu de "novo" — nao adianta
    encher o banco com lead que voce nunca tocou.
    """
    ja_existe = buscar(con, lead["place_key"]) is not None
    if not ja_existe and (lead.get("status") or "novo") == "novo":
        return

    atual = buscar(con, lead["place_key"]) or {}
    upsert(
        con,
        {
            **lead,
            "estagio_contato": atual.get("estagio_contato", lead.get("estagio_contato", 0)),
            "data_primeiro_contato": atual.get("data_primeiro_contato", ""),
            "data_ultimo_contato": atual.get("data_ultimo_contato", ""),
        },
    )


# ------------------------------------------------------------ regra do funil


def _dias_desde(data_iso: str, hoje: Optional[date] = None) -> Optional[int]:
    if not data_iso:
        return None
    try:
        d = datetime.strptime(data_iso, "%Y-%m-%d").date()
    except ValueError:
        return None
    return ((hoje or date.today()) - d).days


def acao_da_vez(
    estagio: int, data_ultimo_contato: str = "", hoje: Optional[date] = None
) -> tuple[str, int]:
    """Qual mensagem esse lead deve receber agora — o coracao do follow-up.

    Devolve (acao, dias_restantes):

        ("inicial", 0)       nunca contatado, manda a abordagem
        ("followup1", 0)     passou o prazo depois da 1a mensagem
        ("followup2", 0)     passou o prazo depois do 1o follow-up
        ("aguardando", n)    dentro do prazo — faltam n dias
        ("concluido", 0)     as 3 mensagens ja sairam, nao insiste mais
    """
    estagio = int(estagio or 0)
    if estagio <= 0:
        return ("inicial", 0)
    if estagio >= ESTAGIO_FINAL:
        return ("concluido", 0)

    prazo = DIAS_ATE_FOLLOWUP1 if estagio == 1 else DIAS_ATE_FOLLOWUP2
    passados = _dias_desde(data_ultimo_contato, hoje)
    # Sem data (registro antigo ou corrompido) preferimos liberar a mensagem a
    # travar o lead para sempre.
    if passados is None or passados >= prazo:
        return ("followup1" if estagio == 1 else "followup2", 0)
    return ("aguardando", prazo - passados)


def esta_pronto(estagio: int, data_ultimo_contato: str = "", hoje: Optional[date] = None) -> bool:
    """True quando existe mensagem para enviar agora."""
    acao, _ = acao_da_vez(estagio, data_ultimo_contato, hoje)
    return acao in ("inicial", "followup1", "followup2")


def atraso_em_dias(
    estagio: int, data_ultimo_contato: str = "", hoje: Optional[date] = None
) -> int:
    """Ha quantos dias esse lead esta esperando alem do prazo. Ordena a fila."""
    acao, _ = acao_da_vez(estagio, data_ultimo_contato, hoje)
    if acao not in ("followup1", "followup2"):
        return 0
    passados = _dias_desde(data_ultimo_contato, hoje)
    if passados is None:
        return 0
    prazo = DIAS_ATE_FOLLOWUP1 if int(estagio) == 1 else DIAS_ATE_FOLLOWUP2
    return max(0, passados - prazo)


def listar_pendentes_followup(
    con: sqlite3.Connection, hoje: Optional[date] = None
) -> list[dict]:
    """Quem ja esta no funil e passou do prazo — do mais atrasado ao mais recente.

    So follow-ups: a 1a mensagem sai de quem ainda nem entrou no banco, e essa
    lista vem da sessao (ver app.py).
    """
    pendentes = [
        r
        for r in todos(con).values()
        if esta_pronto(r["estagio_contato"], r["data_ultimo_contato"], hoje)
        and int(r["estagio_contato"] or 0) >= 1
    ]
    pendentes.sort(
        key=lambda r: atraso_em_dias(r["estagio_contato"], r["data_ultimo_contato"], hoje),
        reverse=True,
    )
    return pendentes


# --------------------------------------------------------------------- merge


def aplicar_em_sessao(con: sqlite3.Connection, leads_db: dict) -> int:
    """Traz o historico do banco por cima dos leads da sessao.

    Sem isto, reiniciar o Streamlit e refazer a busca traria todo mundo como
    "novo" de novo — e voce mandaria a primeira mensagem pela segunda vez.
    """
    salvos = todos(con)
    tocados = 0
    for place_key, lead in leads_db.items():
        registro = salvos.get(place_key)
        if not registro:
            continue
        for campo in CAMPOS_MESCLADOS:
            lead[campo] = registro[campo]
        tocados += 1
    return tocados
