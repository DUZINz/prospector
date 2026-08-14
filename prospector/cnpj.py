"""
Enriquecimento de leads pela base publica da Receita Federal.

Resolve duas coisas que o Google Maps nao da:

    1. E-MAIL       — o Maps nao tem esse campo; a Receita tem.
    2. PORTE (MEI)  — o unico jeito confiavel de saber se o lead e MEI.

O caminho e sempre em duas etapas, porque o Maps tambem nao da o CNPJ:

    nome + municipio  --(busca)-->  CNPJ  --(consulta)-->  email, porte, MEI

Cada etapa tem varios provedores em cascata: se o primeiro cair ou mudar o
formato, o proximo assume. Rode o diagnostico para ver quais respondem daqui:

    python -m prospector.cnpj --diagnostico

Consulta avulsa, para conferir um CNPJ na mao:

    python -m prospector.cnpj --cnpj 47960950000121
    python -m prospector.cnpj --nome "Padaria Sao Jorge" --municipio "Curitiba" --uf PR
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Optional

TIMEOUT = 25
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) prospector/1.0"

# Confianca minima para aceitar que o CNPJ encontrado e mesmo o do lead.
# Abaixo disso preferimos nao preencher a inventar vinculo errado.
LIMIAR_SIMILARIDADE = 0.65

# Palavras que descrevem o ramo, nao o negocio. Duas empresas diferentes podem
# ter todas elas em comum, entao sozinhas nao provam nada.
GENERICOS = {
    "advocacia", "advogado", "advogados", "associados", "sociedade", "individual",
    "escritorio", "clinica", "consultorio", "centro", "instituto", "grupo",
    "pet", "shop", "petshop", "agropecuaria", "animais", "veterinaria",
    "padaria", "panificadora", "restaurante", "lanchonete", "bar", "mercado",
    "comercial", "industria", "distribuidora", "transportes", "solucoes",
    "assessoria", "consultoria", "estetica", "beleza", "salao", "barbearia",
    "odontologia", "odontologica", "medica", "saude", "farmacia",
    "construtora", "engenharia", "imobiliaria", "auto", "oficina", "mecanica",
}


# ----------------------------------------------------------------- utilidades


def so_digitos(txt: Optional[str]) -> str:
    return re.sub(r"\D", "", txt or "")


def normalizar_nome(txt: str) -> str:
    """'Advocacia Sao Jorge LTDA - ME' -> 'advocacia sao jorge'.

    Remove acento, tipo societario e pontuacao para que a comparacao entre o
    nome fantasia do Maps e a razao social da Receita nao falhe por causa deles.
    """
    t = unicodedata.normalize("NFKD", txt or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(
        r"\b(ltda|me|epp|eireli|sa|s a|mei|cia|company|comercio|servicos|"
        r"empreendimentos|participacoes|do|da|de|dos|das|e)\b",
        " ",
        t,
    )
    return re.sub(r"\s+", " ", t).strip()


def similaridade(a: str, b: str) -> float:
    """Quanto o nome do Maps e a razao social da Receita falam do mesmo negocio.

    Comparacao letra-a-letra sozinha nao serve: a Receita enfia palavras no meio
    ("Amigo Fiel" vira "AMIGO FIEL COMERCIO DE ANIMAIS LTDA") e a nota despenca
    mesmo estando certo. Por isso a nota principal e sobreposicao de PALAVRAS.

    Exige ainda que a sobreposicao tenha ao menos uma palavra propria — duas
    empresas quaisquer podem compartilhar "advocacia" e "associados" sem ter
    nenhuma relacao entre si.
    """
    na, nb = normalizar_nome(a), normalizar_nome(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return 1.0

    # A nota sai SO das palavras proprias. Contar as genericas inflava o placar:
    # "Pet Shop Amigo Fiel" e "Pet Shop Bom Amigo" compartilham 3 de 4 palavras
    # e sao negocios diferentes. Tirando "pet" e "shop", sobra 1 de 2.
    ta = set(na.split()) - GENERICOS
    tb = set(nb.split()) - GENERICOS
    if not ta or not tb:
        # Nome feito so de termos do ramo ("Escritorio de Advocacia") nao
        # identifica ninguem — nao da para casar com seguranca.
        return 0.0

    comum = ta & tb
    if not comum:
        return 0.0
    return len(comum) / min(len(ta), len(tb))


def extrair_municipio_uf(endereco: str, regiao: str = "") -> tuple[str, str]:
    """Tira cidade e UF do endereco do Maps; cai na regiao da busca se falhar.

    Formato tipico: "R. Pedro Gusso, 4127 - Cidade Industrial, Curitiba - PR, 81315-000"
    """
    m = re.search(r",\s*([^,]+?)\s*[-–]\s*([A-Z]{2})\b", endereco or "")
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # "Curitiba PR" / "Curitiba - PR" / "Curitiba/PR"
    m = re.match(r"\s*(.+?)\s*[-/ ]\s*([A-Za-z]{2})\s*$", regiao or "")
    if m:
        return m.group(1).strip(), m.group(2).upper()
    return (regiao or "").strip(), ""


class LimitadorDeRitmo:
    """Espaca as chamadas por provedor. O cnpj.ws publico corta em 3/minuto."""

    def __init__(self) -> None:
        self._ultima: dict[str, float] = {}

    def esperar(self, chave: str, intervalo: float) -> None:
        agora = time.monotonic()
        falta = intervalo - (agora - self._ultima.get(chave, 0.0))
        if falta > 0:
            time.sleep(falta)
        self._ultima[chave] = time.monotonic()


RITMO = LimitadorDeRitmo()


def _http(url: str, metodo: str = "GET", corpo: Optional[dict] = None) -> tuple[int, str]:
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    cabecalhos = {"User-Agent": UA, "Accept": "application/json"}
    if dados:
        cabecalhos["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


# ------------------------------------------------------------------- modelo


@dataclass
class DadosCNPJ:
    cnpj: str = ""
    razao_social: str = ""
    nome_fantasia: str = ""
    email: str = ""
    telefone: str = ""
    porte: str = ""
    mei: Optional[bool] = None
    simples: Optional[bool] = None
    situacao: str = ""
    abertura: str = ""
    cnae: str = ""
    municipio: str = ""
    uf: str = ""
    fonte: str = ""
    confianca: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _texto(v) -> str:
    return "" if v is None else str(v).strip()


# ------------------------------------------------- provedores: CNPJ -> dados


def _via_minhareceita(cnpj: str) -> Optional[DadosCNPJ]:
    """minhareceita.org — espelho aberto da base da Receita. Traz email e MEI."""
    RITMO.esperar("minhareceita", 1.2)
    st, corpo = _http(f"https://minhareceita.org/{cnpj}")
    if st != 200:
        return None
    d = json.loads(corpo)
    return DadosCNPJ(
        cnpj=cnpj,
        razao_social=_texto(d.get("razao_social")),
        nome_fantasia=_texto(d.get("nome_fantasia")),
        email=_texto(d.get("email")).lower(),
        telefone=_texto(d.get("ddd_telefone_1")),
        porte=_texto(d.get("porte") or d.get("descricao_porte")),
        mei=d.get("opcao_pelo_mei"),
        simples=d.get("opcao_pelo_simples"),
        situacao=_texto(d.get("descricao_situacao_cadastral")),
        abertura=_texto(d.get("data_inicio_atividade")),
        cnae=_texto(d.get("cnae_fiscal_descricao")),
        municipio=_texto(d.get("municipio")),
        uf=_texto(d.get("uf")),
        fonte="minhareceita",
    )


def _via_cnpjws(cnpj: str) -> Optional[DadosCNPJ]:
    """publica.cnpj.ws — o unico que devolve o flag MEI ja resolvido. 3 req/min."""
    RITMO.esperar("cnpjws", 21.0)
    st, corpo = _http(f"https://publica.cnpj.ws/cnpj/{cnpj}")
    if st != 200:
        return None
    d = json.loads(corpo)
    est = d.get("estabelecimento") or {}
    simples = d.get("simples") or {}
    cidade = est.get("cidade") or {}
    estado = est.get("estado") or {}
    ddd, fone = _texto(est.get("ddd1")), _texto(est.get("telefone1"))
    return DadosCNPJ(
        cnpj=cnpj,
        razao_social=_texto(d.get("razao_social")),
        nome_fantasia=_texto(est.get("nome_fantasia")),
        email=_texto(est.get("email")).lower(),
        telefone=f"{ddd}{fone}" if fone else "",
        porte=_texto((d.get("porte") or {}).get("descricao")),
        mei=(simples.get("mei") == "Sim") if simples.get("mei") is not None else None,
        simples=(simples.get("simples") == "Sim") if simples.get("simples") is not None else None,
        situacao=_texto(est.get("situacao_cadastral")),
        abertura=_texto(est.get("data_inicio_atividade")),
        cnae=_texto((est.get("atividade_principal") or {}).get("descricao")),
        municipio=_texto(cidade.get("nome")),
        uf=_texto(estado.get("sigla")),
        fonte="cnpj.ws",
    )


def _via_brasilapi(cnpj: str) -> Optional[DadosCNPJ]:
    """BrasilAPI — estavel, mas nem sempre traz email."""
    RITMO.esperar("brasilapi", 1.5)
    st, corpo = _http(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}")
    if st != 200:
        return None
    d = json.loads(corpo)
    return DadosCNPJ(
        cnpj=cnpj,
        razao_social=_texto(d.get("razao_social")),
        nome_fantasia=_texto(d.get("nome_fantasia")),
        email=_texto(d.get("email") or d.get("correio_eletronico")).lower(),
        telefone=_texto(d.get("ddd_telefone_1")),
        porte=_texto(d.get("porte") or d.get("descricao_porte")),
        mei=d.get("opcao_pelo_mei"),
        simples=d.get("opcao_pelo_simples"),
        situacao=_texto(d.get("descricao_situacao_cadastral")),
        abertura=_texto(d.get("data_inicio_atividade")),
        cnae=_texto(d.get("cnae_fiscal_descricao")),
        municipio=_texto(d.get("municipio")),
        uf=_texto(d.get("uf")),
        fonte="brasilapi",
    )


PROVEDORES_CONSULTA = [
    ("minhareceita", _via_minhareceita),
    ("brasilapi", _via_brasilapi),
    ("cnpj.ws", _via_cnpjws),
]


def consultar_cnpj(cnpj: str) -> Optional[DadosCNPJ]:
    """Consulta um CNPJ, tentando os provedores em ordem ate um responder.

    Prefere um resultado COM e-mail: e o campo que motiva a consulta. Se o
    primeiro provedor responder sem e-mail, guarda e tenta o proximo.
    """
    d = so_digitos(cnpj)
    if len(d) != 14:
        return None

    reserva: Optional[DadosCNPJ] = None
    for _nome, fn in PROVEDORES_CONSULTA:
        try:
            r = fn(d)
        except Exception:  # noqa: BLE001 — provedor fora do ar nao derruba o lote
            continue
        if not r or not r.razao_social:
            continue
        if r.email:
            return r
        reserva = reserva or r
    return reserva


# ------------------------------------------------- provedores: nome -> CNPJ


def _buscar_casadosdados(nome: str, municipio: str, uf: str) -> list[dict]:
    """casadosdados.com.br — desativado o endpoint publico gratuito (verificado
    em 2026-08): v2 devolve 404, v4/v5 exigem api-key paga (401 sem ela). Nao
    ha, no momento, nenhuma API gratuita de busca-por-NOME no Brasil — so as
    de consulta por numero de CNPJ (que continuam de pe, ver PROVEDORES_CONSULTA).
    Isso fica aqui so para o --diagnostico continuar relatando o estado real;
    nao e um bug de parser para "consertar".
    """
    RITMO.esperar("casadosdados", 2.0)
    corpo = {
        "query": {
            "termo": [nome],
            "atividade_principal": [],
            "natureza_juridica": [],
            "uf": [uf] if uf else [],
            "municipio": [municipio.upper()] if municipio else [],
            "situacao_cadastral": "ATIVA",
        },
        "range_query": {},
        "extras": {},
        "page": 1,
    }
    st, texto = _http(
        "https://api.casadosdados.com.br/v2/public/cnpj/search", "POST", corpo
    )
    if st != 200:
        return []
    d = json.loads(texto)
    itens = ((d.get("data") or {}).get("cnpj")) or []
    return [
        {
            "cnpj": so_digitos(i.get("cnpj")),
            "nome": _texto(i.get("nome_fantasia")) or _texto(i.get("razao_social")),
            "razao_social": _texto(i.get("razao_social")),
            "municipio": _texto(i.get("municipio")),
        }
        for i in itens
        if so_digitos(i.get("cnpj"))
    ]


PROVEDORES_BUSCA = [("casadosdados", _buscar_casadosdados)]


def buscar_cnpj_por_nome(
    nome: str, municipio: str, uf: str = ""
) -> tuple[str, float, str]:
    """Devolve (cnpj, confianca, fonte). CNPJ vazio quando nada bate o limiar.

    A busca por nome e a parte fragil do processo: nome fantasia do Maps quase
    nunca e igual a razao social da Receita. Por isso pontuamos cada candidato
    e so aceitamos acima de LIMIAR_SIMILARIDADE — melhor deixar em branco do
    que colar um CNPJ de outra empresa no lead.
    """
    if not nome:
        return "", 0.0, ""

    for fonte, fn in PROVEDORES_BUSCA:
        try:
            candidatos = fn(nome, municipio, uf)
        except Exception:  # noqa: BLE001
            continue
        if not candidatos:
            continue

        melhor, melhor_nota = "", 0.0
        for c in candidatos:
            nota = max(
                similaridade(nome, c["nome"]),
                similaridade(nome, c["razao_social"]),
            )
            # Cidade diferente da buscada quase sempre e homonimo de outro lugar.
            if municipio and c["municipio"]:
                if normalizar_nome(municipio) != normalizar_nome(c["municipio"]):
                    nota *= 0.55
            if nota > melhor_nota:
                melhor, melhor_nota = c["cnpj"], nota

        if melhor_nota >= LIMIAR_SIMILARIDADE:
            return melhor, round(melhor_nota, 3), fonte

    return "", 0.0, ""


def enriquecer(
    nome: str, endereco: str = "", regiao: str = "", cnpj: str = ""
) -> Optional[DadosCNPJ]:
    """Ponto de entrada: de um lead do Maps para os dados da Receita.

    `cnpj` preenchido pula a busca por nome — use quando voce ja souber o numero.
    """
    if so_digitos(cnpj):
        dados = consultar_cnpj(cnpj)
        if dados:
            dados.confianca = 1.0
        return dados

    municipio, uf = extrair_municipio_uf(endereco, regiao)
    achado, confianca, _fonte = buscar_cnpj_por_nome(nome, municipio, uf)
    if not achado:
        return None

    dados = consultar_cnpj(achado)
    if dados:
        dados.confianca = confianca
    return dados


# ------------------------------------------------------------------- CLI


CNPJ_TESTE = "47960950000121"  # Magazine Luiza — matriz, ativa, publica


def _diagnostico() -> int:
    print("Testando os provedores a partir desta maquina...\n")
    ok_consulta = 0

    print("CONSULTA (CNPJ -> dados)")
    for nome, fn in PROVEDORES_CONSULTA:
        try:
            ini = time.monotonic()
            r = fn(CNPJ_TESTE)
            ms = int((time.monotonic() - ini) * 1000)
            if r and r.razao_social:
                ok_consulta += 1
                print(
                    f"  OK   {nome:14} {ms:5}ms  "
                    f"email={'sim' if r.email else 'NAO':3}  "
                    f"mei={r.mei}  porte={r.porte or '-'}"
                )
            else:
                print(f"  --   {nome:14} {ms:5}ms  respondeu vazio")
        except Exception as e:  # noqa: BLE001
            print(f"  FALHA {nome:14}       {type(e).__name__}: {e}")

    print("\nBUSCA (nome -> CNPJ)")
    ok_busca = 0
    for nome, fn in PROVEDORES_BUSCA:
        try:
            ini = time.monotonic()
            r = fn("Magazine Luiza", "Franca", "SP")
            ms = int((time.monotonic() - ini) * 1000)
            if r:
                ok_busca += 1
                print(f"  OK   {nome:14} {ms:5}ms  {len(r)} candidatos")
            else:
                print(f"  --   {nome:14} {ms:5}ms  nenhum candidato")
        except Exception as e:  # noqa: BLE001
            print(f"  FALHA {nome:14}       {type(e).__name__}: {e}")

    print()
    if ok_consulta and ok_busca:
        print("Tudo certo: enriquecimento automatico funciona.")
        return 0
    if ok_consulta:
        print(
            "Consulta funciona, busca por nome nao.\n"
            "O enriquecimento automatico nao vai achar CNPJ sozinho, mas voce\n"
            "ainda pode colar o CNPJ na coluna do app e ele completa o resto."
        )
        return 0
    print("Nenhum provedor respondeu. Verifique a internet, VPN ou firewall.")
    return 1


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Enriquecimento pela base da Receita.")
    ap.add_argument("--diagnostico", action="store_true", help="Testa os provedores")
    ap.add_argument("--cnpj", help="Consulta um CNPJ direto")
    ap.add_argument("--nome", help="Busca o CNPJ pelo nome do negocio")
    ap.add_argument("--municipio", default="", help='Ex.: "Curitiba"')
    ap.add_argument("--uf", default="", help='Ex.: "PR"')
    args = ap.parse_args(argv)

    if args.diagnostico:
        return _diagnostico()

    if args.cnpj or args.nome:
        d = enriquecer(
            nome=args.nome or "",
            regiao=f"{args.municipio} {args.uf}".strip(),
            cnpj=args.cnpj or "",
        )
        if not d:
            print("Nada encontrado.")
            return 1
        print(json.dumps(d.to_dict(), ensure_ascii=False, indent=2))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
