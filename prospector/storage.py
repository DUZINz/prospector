"""Leads em memoria: vivem em st.session_state, somem ao fechar a aba ou dar F5.

Cada lead e um dict indexado por place_key. Sem arquivo, sem SQLite — o
Excel/CSV exportado pela tela e o unico jeito de nao perder o trabalho.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from .models import Lead

# Campos da Receita que todo lead carrega, mesmo antes de ser consultado.
CAMPOS_RECEITA = {
    "cnpj": "", "razao_social": "", "email": "", "porte": "",
    "mei": None, "simples": None, "cnae": "", "situacao": "", "abertura": "",
    "cnpj_confianca": 0.0, "cnpj_fonte": "", "cnpj_consultado": "",
}

# Campos do funil de contato. Vivem de verdade em funil.db (que sobrevive entre
# sessoes); aqui ficam so os valores neutros, para a tabela sempre ter a coluna
# mesmo antes de o lead entrar no funil. O merge de funil.py sobrescreve.
CAMPOS_FUNIL = {
    "estagio_contato": 0,
    "data_primeiro_contato": "",
    "data_ultimo_contato": "",
}


def salvar(leads_db: dict, leads: Iterable[Lead]) -> tuple[int, int]:
    """Insere novos leads; nos ja conhecidos so atualiza os dados coletados.

    `status`, `observacoes`, `primeira_vez` e os campos da Receita sao
    preservados — sao seus, nao do scraper. Retorna (novos, atualizados).
    """
    hoje = date.today().isoformat()
    novos = atualizados = 0

    for lead in leads:
        dados = lead.to_dict()
        existente = leads_db.get(lead.place_key)
        if existente:
            dados["status"] = existente["status"]
            dados["observacoes"] = existente["observacoes"]
            dados["primeira_vez"] = existente["primeira_vez"]
            for campo, padrao in {**CAMPOS_RECEITA, **CAMPOS_FUNIL}.items():
                dados[campo] = existente.get(campo, padrao)
            atualizados += 1
        else:
            dados.update(CAMPOS_RECEITA)
            dados.update(CAMPOS_FUNIL)
            novos += 1
        dados["ultima_vez"] = hoje
        leads_db[lead.place_key] = dados

    return novos, atualizados


def listar(leads_db: dict, **filtros) -> list[dict]:
    """Filtros: status, regiao, termo, apenas_sem_site, com_whatsapp, com_email, apenas_mei."""
    registros = list(leads_db.values())

    if filtros.get("status"):
        alvo = set(filtros["status"])
        registros = [r for r in registros if r["status"] in alvo]
    if filtros.get("regiao"):
        registros = [r for r in registros if r["regiao"] == filtros["regiao"]]
    if filtros.get("termo"):
        registros = [r for r in registros if r["termo"] == filtros["termo"]]
    if filtros.get("apenas_sem_site"):
        registros = [r for r in registros if not r["tem_site"]]
    if filtros.get("com_whatsapp"):
        registros = [r for r in registros if r["whatsapp"]]
    if filtros.get("com_email"):
        registros = [r for r in registros if r["email"]]
    if filtros.get("apenas_mei"):
        registros = [r for r in registros if r["mei"] is True]

    registros.sort(key=lambda r: (r["avaliacoes"] is None, -(r["avaliacoes"] or 0), r["nome"]))
    return registros


def atualizar_status(leads_db: dict, place_key: str, status: str, obs: str = "") -> None:
    if place_key in leads_db:
        leads_db[place_key]["status"] = status
        leads_db[place_key]["observacoes"] = obs


def valores_distintos(leads_db: dict, coluna: str) -> list[str]:
    if coluna not in {"regiao", "termo", "status", "categoria"}:
        raise ValueError(f"coluna nao permitida: {coluna}")
    return sorted({r[coluna] for r in leads_db.values() if r.get(coluna)})


def pendentes_de_receita(leads_db: dict, limite: int = 50, **filtros) -> list[dict]:
    """Leads que ainda nao foram consultados na Receita, respeitando os filtros da tela."""
    todos = listar(leads_db, **filtros)
    return [r for r in todos if not r["cnpj_consultado"]][:limite]


def salvar_receita(leads_db: dict, place_key: str, dados, quando: str = "") -> None:
    """Grava o resultado do enriquecimento. `dados` None marca a tentativa falha."""
    registro = leads_db.get(place_key)
    if registro is None:
        return

    quando = quando or date.today().isoformat()
    if dados is None:
        registro["cnpj_consultado"] = quando
        return

    registro.update(
        cnpj=dados.cnpj, razao_social=dados.razao_social, email=dados.email,
        porte=dados.porte, mei=dados.mei, simples=dados.simples, cnae=dados.cnae,
        situacao=dados.situacao, abertura=dados.abertura,
        cnpj_confianca=dados.confianca, cnpj_fonte=dados.fonte,
        cnpj_consultado=quando,
    )
