"""V28 — verificação do coordenograma M-B-0 contra o STAR75 do ETAP.

Fonte da referência
-------------------
Arquivo ``00123.pdf`` (ETAP Star 24.0.3C, folha *Star75*, Barra5, Nom. kV = 6,6,
Plot Ref. kV = 6,6, Fault: Phase, 08-31-2026). Os pontos abaixo foram lidos
diretamente das curvas vetoriais do PDF e convertidos para (A, s) com a
calibração log-log dos eixos.

A calibração foi ancorada em dois valores que já são conhecidos do próprio
modelo — o pickup 51 do Relé11 (230,0 A) e o pickup 50 (7760 A) — e reproduz
esses dois valores com erro < 0,15 %, o que valida a leitura das demais curvas.

Como rodar::

    python -m validation.validate_v28_etap_star75

Saída: uma linha por elemento com o maior desvio encontrado. Retorna código 1
se algum elemento estourar a tolerância.
"""
from __future__ import annotations

import sys

from core.protection import (
    _ctx,
    _cable_damage_trace,
    _motor_capability_traces,
    _motor_start_envelope,
    build_concise_tcc,
    relay_operating_time,
    settings_for_zone,
)

# --- referência extraída do STAR75 -----------------------------------------
# Relé11 - P (curva azul-marinho). Pares (corrente A, tempo s).
ETAP_RELAY11 = [
    (1054.2, 1.3028), (1524.0, 0.6074), (2203.3, 0.2876),
    (4604.9, 0.0653), (7759.0, 0.0653),
]
ETAP_RELAY11_PICKUP_A = 230.0
ETAP_RELAY11_INST_A = 7759.0

# M-B-0-100% (curva preta de partida).
ETAP_MOTOR_START = [
    (154.4, 1.1652), (179.5, 1.0024), (758.2, 1.0024), (1003.5, 0.7573),
    (1003.5, 0.1003), (1032.5, 0.0552), (1142.5, 0.0281), (1395.3, 0.0137),
    (1605.2, 0.0100),
]

# M-B-0 (curva vermelha de capacidade térmica do estator).
ETAP_MOTOR_THERMAL = [
    (239.5, 1001.7), (262.2, 500.9), (293.2, 300.4),
    (370.4, 150.2), (463.0, 87.1), (555.2, 60.1),
]

# Cabo2 - P (reta marrom de dano) — extremos da reta no desenho.
ETAP_CABLE2_DAMAGE = [(724.0, 10.0), (22800.0, 0.01)]

# Cabo2 Ampacity (marca marrom curta no topo).
ETAP_CABLE2_AMPACITY_A = 81.3

# Relé11 - 3P (seta na base): corrente de curto trifásica no ponto do relé.
ETAP_RELAY11_3P_KA = 10.32

TOL_RELAY = 0.02      # 2 % — a curva do PDF é bezier, os nós não são exatos
TOL_GEOMETRY = 0.01   # 1 % — vértices retos (partida, dano, térmica)


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-12)


def _interp_log(xs, ys, x):
    """Interpola em log-log a polilinha (xs, ys) no ponto x."""
    import math
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if xs[i] >= x:
            if xs[i] == xs[i - 1]:
                return ys[i]
            f = (math.log10(x) - math.log10(xs[i - 1])) / (math.log10(xs[i]) - math.log10(xs[i - 1]))
            return 10 ** (math.log10(ys[i - 1]) + f * (math.log10(ys[i]) - math.log10(ys[i - 1])))
    return ys[-1]


def _check(title, pairs, tol, results):
    worst = max((d for _, d in pairs), default=0.0)
    ok = worst <= tol
    results.append((title, worst, tol, ok))
    return ok


def main() -> int:
    _, zones, motors, cables, _, _, _, _ = _ctx()
    results: list[tuple[str, float, float, bool]] = []

    # 1) Relé11 — tempos de atuação nos pontos lidos do Star.
    st = settings_for_zone("Z-R11")
    pairs = []
    for i, t_ref in ETAP_RELAY11:
        t, _stage = relay_operating_time(i, st, "phase")
        pairs.append((i, _rel(t, t_ref) if t else 1.0))
    _check("Relé11 - P OC1 (tempo)", pairs, TOL_RELAY, results)

    pairs = [(0, _rel(float(st["phase_stage1_pickup_a"]), ETAP_RELAY11_PICKUP_A)),
             (1, _rel(float(st["phase_stage3_pickup_a"]), ETAP_RELAY11_INST_A))]
    _check("Relé11 - pickups 51/50", pairs, TOL_RELAY, results)

    # 2) M-B-0-100% — geometria da curva de partida.
    start = _motor_start_envelope(motors["M-B-0"], 6.6)
    pairs = []
    for i_ref, t_ref in ETAP_MOTOR_START:
        pairs.append((i_ref, min(_rel(x, i_ref) + _rel(y, t_ref)
                                 for x, y in zip(start["x"], start["y"]))))
    _check("M-B-0-100% (partida)", pairs, TOL_GEOMETRY, results)

    # 3) M-B-0 — capacidade térmica (pontos ETAP do próprio modelo).
    cap = _motor_capability_traces(motors["M-B-0"])[0]
    pairs = []
    for i_ref, t_ref in ETAP_MOTOR_THERMAL:
        pairs.append((i_ref, min(_rel(x, i_ref) + _rel(y, t_ref)
                                 for x, y in zip(cap["x"], cap["y"]))))
    _check("M-B-0 (capacidade térmica)", pairs, TOL_GEOMETRY, results)

    # 4) Cabo2 - P — reta de dano adiabática.
    cx, cy = _cable_damage_trace(cables["Cabo2"], st.get("cable_k_adiabatic"), 1e5,
                                min_current=max(10.0, float(motors["M-B-0"]["amp"]) * 0.6))
    pairs = [(i_ref, _rel(_interp_log(cx, cy, i_ref), t_ref)) for i_ref, t_ref in ETAP_CABLE2_DAMAGE]
    _check("Cabo2 - P (dano)", pairs, TOL_GEOMETRY, results)

    # 5) Cabo2 Ampacity — marca curta no topo da folha.
    amp = None
    for tr in build_concise_tcc("mb0")["traces"]:
        if tr and tr.get("kind") == "ampacity":
            amp = tr["value_a"]
    pairs = [(0, _rel(amp, ETAP_CABLE2_AMPACITY_A) if amp else 1.0)]
    _check("Cabo2 Ampacity", pairs, TOL_GEOMETRY, results)

    width = max(len(r[0]) for r in results)
    print("Verificação V28 — coordenograma M-B-0 x ETAP Star75 (Barra5 6,6 kV)")
    print("-" * (width + 34))
    for title, worst, tol, ok in results:
        print(f"{title:<{width}}  desvio máx {worst*100:6.2f} %  (tol {tol*100:.0f} %)  {'OK' if ok else 'FALHOU'}")
    print("-" * (width + 34))
    print(f"Referência 3F no ponto do Relé11 (Star75): {ETAP_RELAY11_3P_KA:.2f} kA — "
          "comparar com o valor calculado pelo estudo quando o Pandapower estiver disponível.")
    failed = [r for r in results if not r[3]]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
