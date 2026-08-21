# -*- coding: utf-8 -*-
"""Cadencia de follow-up: prazos em horas, avanco de estagio e anti-spam.

O relogio entra sempre injetado (`agora=`), nunca `datetime.now()` — teste que
depende do relogio de verdade falha sozinho as 23h59.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from prospector import funil
from prospector.models import ABORDAGEM_FOLLOWUP1, preencher

AGORA = datetime(2026, 8, 20, 12, 0, 0)


def quando(horas_atras: float) -> str:
    """Carimbo ISO de N horas antes de AGORA."""
    return (AGORA - timedelta(hours=horas_atras)).isoformat(timespec="seconds")


# ---------------------------------------------------------------- prazos


def test_estagio_zero_sempre_pronto():
    # Nunca contatado nao espera prazo nenhum.
    assert funil.acao_da_vez(0, "", AGORA) == ("inicial", 0)
    assert funil.esta_pronto(0, "", AGORA)


def test_primeiro_followup_respeita_48h():
    # 47h ainda e cedo; 48h em ponto ja libera.
    acao, faltam = funil.acao_da_vez(1, quando(47), AGORA)
    assert acao == "aguardando" and faltam == 1
    assert not funil.esta_pronto(1, quando(47), AGORA)

    assert funil.acao_da_vez(1, quando(48), AGORA) == ("followup1", 0)
    assert funil.esta_pronto(1, quando(72), AGORA)


def test_segundo_followup_respeita_72h():
    assert funil.acao_da_vez(2, quando(71), AGORA)[0] == "aguardando"
    assert funil.acao_da_vez(2, quando(72), AGORA) == ("followup2", 0)


def test_cadencia_encerra_no_estagio_final():
    # Depois da ultima mensagem nao ha o que enviar, por mais tempo que passe.
    assert funil.acao_da_vez(funil.ESTAGIO_FINAL, quando(1000), AGORA) == ("concluido", 0)
    assert not funil.esta_pronto(funil.ESTAGIO_FINAL, quando(1000), AGORA)


def test_data_ilegivel_libera_em_vez_de_travar():
    # Registro antigo/corrompido: melhor liberar a mensagem que prender o lead.
    assert funil.acao_da_vez(1, "", AGORA) == ("followup1", 0)
    assert funil.acao_da_vez(1, "20/08/2026", AGORA) == ("followup1", 0)


def test_le_carimbo_antigo_so_com_data():
    # Registros gravados antes da mudanca so tem "AAAA-MM-DD" (vale meia-noite).
    assert funil.acao_da_vez(1, "2026-08-19", AGORA)[0] == "aguardando"  # 12h
    assert funil.acao_da_vez(1, "2026-08-18", AGORA) == ("followup1", 0)  # 36h...
    # 2026-08-18 00:00 -> 60h atras, passou das 48h.


def test_atraso_ordena_a_fila():
    assert funil.atraso_em_horas(1, quando(50), AGORA) == 2
    assert funil.atraso_em_horas(1, quando(47), AGORA) == 0  # ainda no prazo


# ---------------------------------------------------------------- status


def test_status_segue_o_estagio():
    assert funil.status_do_estagio(0) == "novo"
    assert funil.status_do_estagio(1) == "primeiro_contato_enviado"
    assert funil.status_do_estagio(2) == "followup_enviado"


def test_status_marcado_na_mao_vence_a_cadencia():
    assert funil.status_do_estagio(1, "respondeu") == "respondeu"
    assert funil.status_do_estagio(2, "arquivado") == "arquivado"


def test_quem_respondeu_nao_recebe_cobranca():
    vencido = {"estagio_contato": 1, "data_ultimo_contato": quando(200)}
    assert funil.apto_a_followup({**vencido, "status": "primeiro_contato_enviado"}, AGORA)
    assert not funil.apto_a_followup({**vencido, "status": "respondeu"}, AGORA)
    assert not funil.apto_a_followup({**vencido, "status": "arquivado"}, AGORA)
    # Nunca contatado nao e follow-up, e a 1a mensagem.
    assert not funil.apto_a_followup({"estagio_contato": 0, "status": "novo"}, AGORA)


# ---------------------------------------------------------------- banco


def _con():
    tmp = Path(tempfile.mkdtemp()) / "teste.db"
    return funil.conectar(tmp)


def test_envio_avanca_estagio_e_carimba_hora():
    con = _con()
    lead = {"place_key": "k1", "nome": "Padaria Sol", "status": "novo"}

    r1 = funil.registrar_envio(con, lead, quando(48))
    assert r1["estagio_contato"] == 1
    assert r1["status"] == "primeiro_contato_enviado"
    assert "T" in r1["data_ultimo_contato"]  # tem hora, nao so data
    assert r1["data_primeiro_contato"] == r1["data_ultimo_contato"]

    r2 = funil.registrar_envio(con, lead, quando(0))
    assert r2["estagio_contato"] == 2
    assert r2["status"] == "followup_enviado"
    # O primeiro contato nao se reescreve a cada envio.
    assert r2["data_primeiro_contato"] == r1["data_primeiro_contato"]


def test_cadencia_nao_passa_do_fim_por_mais_que_se_insista():
    con = _con()
    lead = {"place_key": "k2", "nome": "Bar do Ze"}
    for _ in range(6):
        registro = funil.registrar_envio(con, lead, quando(100))
    assert registro["estagio_contato"] == funil.ESTAGIO_FINAL
    assert funil.acao_da_vez(registro["estagio_contato"], registro["data_ultimo_contato"])[0] == "concluido"


def test_fila_lista_vencidos_do_mais_atrasado_ao_menos():
    con = _con()
    funil.registrar_envio(con, {"place_key": "atrasado", "nome": "A"}, quando(200))
    funil.registrar_envio(con, {"place_key": "vencido", "nome": "B"}, quando(50))
    funil.registrar_envio(con, {"place_key": "no_prazo", "nome": "C"}, quando(10))

    fila = funil.listar_pendentes_followup(con, AGORA)
    assert [r["place_key"] for r in fila] == ["atrasado", "vencido"]


# ---------------------------------------------------------------- mensagem


def test_mensagem_de_followup_sai_preenchida():
    lead = {"nome": "Padaria Sol", "whatsapp": "https://wa.me/5541999998888"}
    texto = preencher(ABORDAGEM_FOLLOWUP1, lead)
    assert texto.startswith("Fala, Padaria Sol!")
    assert "Padaria Sol" in texto.split("demanda da ")[1]
    assert "{" not in texto  # nenhuma variavel sobrou por preencher


def test_followup_sem_nome_nao_vira_fala_virgula():
    texto = preencher(ABORDAGEM_FOLLOWUP1, {})
    assert texto.startswith("Fala! Tudo bem?")
    assert "sua empresa" in texto


def test_ponta_a_ponta_48h():
    """Enviou a 1a mensagem, esperou 48h, aparece na fila com o texto certo."""
    con = _con()
    lead = {"place_key": "k3", "nome": "Padaria Sol", "whatsapp": "https://wa.me/5541999998888"}
    funil.registrar_envio(con, lead, quando(48))

    fila = funil.listar_pendentes_followup(con, AGORA)
    assert len(fila) == 1

    acao, _ = funil.acao_da_vez(fila[0]["estagio_contato"], fila[0]["data_ultimo_contato"], AGORA)
    assert acao == "followup1"
    assert "catálogo" in preencher(ABORDAGEM_FOLLOWUP1, fila[0])


if __name__ == "__main__":
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"ok  {nome}")
    print("tudo passou")
