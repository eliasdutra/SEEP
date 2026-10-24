"""V28 — o coordenograma M-B-0 tem de bater com o STAR75 do ETAP.

Referência: 00123.pdf (ETAP Star 24.0.3C, Star75, Barra5 6,6 kV, Fault: Phase).
Os valores esperados vêm das curvas vetoriais desse PDF; ver
docs/CHANGELOG_V28.md e validation/validate_v28_etap_star75.py.
"""
from __future__ import annotations

import pytest

from core import protection


def _traces(view="mb0"):
    return {t["kind"]: t for t in protection.build_concise_tcc(view)["traces"] if t}


# --- 1. patamar de 20 x Is na característica inversa -----------------------

def test_curva_inversa_congela_em_20x_is():
    """IEC 60255-151: acima de 20 x Is o tempo fica no valor de 20 x Is."""
    t20 = protection.relay_time(20 * 230.0, 230.0, 0.325, "IEC_EI")
    t40 = protection.relay_time(40 * 230.0, 230.0, 0.325, "IEC_EI")
    assert t20 == pytest.approx(0.0652, rel=0.01)
    assert t40 == pytest.approx(t20, rel=1e-9)


def test_tempos_do_relay11_batem_com_o_star75():
    st = protection.settings_for_zone("Z-R11")
    for corrente, esperado in ((1054.2, 1.3028), (2203.3, 0.2876), (4604.9, 0.0653)):
        t, _ = protection.relay_operating_time(corrente, st, "phase")
        assert t == pytest.approx(esperado, rel=0.02), corrente


def test_relay11_no_50p_usa_o_patamar_e_nao_a_curva():
    """Em 7760 A o Star mostra 0,0653 s, não 0,0229 s."""
    st = dict(protection.settings_for_zone("Z-R11"))
    st["phase_stage3_pickup_a"] = None          # isola o estágio inverso
    t, _ = protection.relay_operating_time(7759.0, st, "phase")
    assert t == pytest.approx(0.0653, rel=0.02)


# --- 2. curva de partida do motor ------------------------------------------

def test_partida_do_motor_reproduz_a_geometria_do_star():
    motor = protection._ctx()[2]["M-B-0"]
    tr = protection._motor_start_envelope(motor, 6.6)
    xs, ys = tr["x"], tr["y"]
    assert min(xs) == pytest.approx(154.4, rel=0.001)      # vertical na FLA
    assert max(xs) == pytest.approx(1605.2, rel=0.01)      # fim da cauda
    assert min(ys) == pytest.approx(0.01, rel=1e-6)
    # patamar no tempo de aceleração
    assert any(y == pytest.approx(1.0, rel=0.005) and 700 < x < 800 for x, y in zip(xs, ys))
    # vertical na corrente de rotor bloqueado
    assert sum(1 for x in xs if x == pytest.approx(1003.6, rel=0.002)) >= 2


# --- 3. elementos da folha --------------------------------------------------

def test_marca_de_ampacidade_do_cable2():
    tr = _traces()["ampacity"]
    assert tr["value_a"] == pytest.approx(81.3, rel=0.01)
    assert tr["mark"] == "top"
    assert max(tr["y"]) <= 1000.0 and min(tr["y"]) > 100.0   # marca curta no topo


def test_marca_de_pickup_por_rele():
    tr = _traces()["pickup_mark"]
    assert tr["value_a"] == pytest.approx(230.0, rel=0.001)
    assert max(tr["y"]) == pytest.approx(1000.0, rel=1e-6)


def test_curva_do_rele_termina_no_piso_da_folha():
    tr = _traces()["relay_effective"]
    assert tr["y"][-1] == pytest.approx(0.01, rel=1e-6)
    assert tr["x"][-1] == pytest.approx(7760.0, rel=0.001)
    assert max(tr["x"]) == tr["x"][-1]      # não sobra traço rente à base


def test_dano_do_cable2_bate_com_o_star75():
    tr = _traces()["cable"]
    assert min(tr["x"]) == pytest.approx(724.0, rel=0.01)
    assert max(tr["x"]) == pytest.approx(22800.0, rel=0.01)


def test_capacidade_termica_do_motor_bate_com_o_star75():
    tr = _traces()["motor_thermal_exact"]
    assert min(tr["x"]) == pytest.approx(239.5, rel=0.01)
    assert max(tr["x"]) == pytest.approx(555.2, rel=0.01)


# --- 4. metadados da folha --------------------------------------------------

@pytest.mark.parametrize("view", ["mb0", "mb6", "t1", "general"])
def test_toda_vista_tem_unifilar_e_carimbo(view):
    d = protection.build_concise_tcc(view)
    # A Vista Geral junta relés de ramais diferentes: um fio vertical único não
    # representaria o gráfico, então ela não desenha unifilar (ver
    # _view_single_line). As outras três seguem com o painel ao lado.
    if view == "general":
        assert d["single_line"]["elements"] == []
    else:
        assert d["single_line"]["elements"]
    assert d["sheet"]["sheet"] and d["sheet"]["left"] and d["sheet"]["right"]
    assert "500" in d["etap_axis"]["x_tick_text"]
    assert len(d["etap_axis"]["x_tick_vals"]) == len(d["etap_axis"]["x_tick_text"])
