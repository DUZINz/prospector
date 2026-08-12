"""Persistencia em SQLite: leads acumulam entre buscas, sem duplicar."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable

from .models import Lead

BANCO = Path(__file__).resolve().parent.parent / "leads.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    place_key     TEXT PRIMARY KEY,
    nome          TEXT NOT NULL,
    categoria     TEXT,
    endereco      TEXT,
    telefone      TEXT,
    telefone_e164 TEXT,
    whatsapp      TEXT,
    site          TEXT,
    tem_site      INTEGER DEFAULT 0,
    nota          REAL,
    avaliacoes    INTEGER,
    maps_url      TEXT,
    termo         TEXT,
    regiao        TEXT,
    status        TEXT DEFAULT 'novo',
    observacoes   TEXT DEFAULT '',
    primeira_vez  TEXT,
    ultima_vez    TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_regiao ON leads(regiao);
"""


def conectar(caminho: Path | str = BANCO) -> sqlite3.Connection:
    # check_same_thread=False: o Streamlit reusa a conexao (@st.cache_resource)
    # entre threads diferentes de script run. O acesso e serializado pelo proprio
    # Streamlit, que roda um script por vez por sessao.
    con = sqlite3.connect(str(caminho), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def salvar(con: sqlite3.Connection, leads: Iterable[Lead]) -> tuple[int, int]:
    """Insere novos leads; nos ja conhecidos so atualiza os dados coletados.

    `status` e `observacoes` sao preservados — sao seus, nao do scraper.
    Retorna (novos, atualizados).
    """
    hoje = date.today().isoformat()
    novos = atualizados = 0

    for lead in leads:
        existe = con.execute(
            "SELECT 1 FROM leads WHERE place_key = ?", (lead.place_key,)
        ).fetchone()

        if existe:
            con.execute(
                """UPDATE leads SET
                       nome=?, categoria=?, endereco=?, telefone=?, telefone_e164=?,
                       whatsapp=?, site=?, tem_site=?, nota=?, avaliacoes=?,
                       maps_url=?, ultima_vez=?
                   WHERE place_key=?""",
                (
                    lead.nome, lead.categoria, lead.endereco, lead.telefone,
                    lead.telefone_e164, lead.whatsapp, lead.site, int(lead.tem_site),
                    lead.nota, lead.avaliacoes, lead.maps_url, hoje, lead.place_key,
                ),
            )
            atualizados += 1
        else:
            con.execute(
                """INSERT INTO leads (
                       place_key, nome, categoria, endereco, telefone, telefone_e164,
                       whatsapp, site, tem_site, nota, avaliacoes, maps_url,
                       termo, regiao, status, observacoes, primeira_vez, ultima_vez)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    lead.place_key, lead.nome, lead.categoria, lead.endereco,
                    lead.telefone, lead.telefone_e164, lead.whatsapp, lead.site,
                    int(lead.tem_site), lead.nota, lead.avaliacoes, lead.maps_url,
                    lead.termo, lead.regiao, lead.status, lead.observacoes, hoje, hoje,
                ),
            )
            novos += 1

    con.commit()
    return novos, atualizados


def listar(con: sqlite3.Connection, **filtros) -> list[dict]:
    """Filtros aceitos: status, regiao, termo, apenas_sem_site, com_whatsapp."""
    sql = "SELECT * FROM leads WHERE 1=1"
    params: list = []

    if filtros.get("status"):
        marcadores = ",".join("?" * len(filtros["status"]))
        sql += f" AND status IN ({marcadores})"
        params += list(filtros["status"])
    if filtros.get("regiao"):
        sql += " AND regiao = ?"
        params.append(filtros["regiao"])
    if filtros.get("termo"):
        sql += " AND termo = ?"
        params.append(filtros["termo"])
    if filtros.get("apenas_sem_site"):
        sql += " AND tem_site = 0"
    if filtros.get("com_whatsapp"):
        sql += " AND whatsapp <> ''"

    # `avaliacoes IS NULL` primeiro em vez de NULLS LAST: funciona em SQLite antigo.
    sql += " ORDER BY avaliacoes IS NULL, avaliacoes DESC, nome"
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def atualizar_status(con: sqlite3.Connection, place_key: str, status: str, obs: str = "") -> None:
    con.execute(
        "UPDATE leads SET status=?, observacoes=? WHERE place_key=?",
        (status, obs, place_key),
    )
    con.commit()


def valores_distintos(con: sqlite3.Connection, coluna: str) -> list[str]:
    if coluna not in {"regiao", "termo", "status", "categoria"}:
        raise ValueError(f"coluna nao permitida: {coluna}")
    linhas = con.execute(
        f"SELECT DISTINCT {coluna} FROM leads WHERE {coluna} <> '' ORDER BY 1"
    ).fetchall()
    return [r[0] for r in linhas]
