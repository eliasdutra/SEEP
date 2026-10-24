"""Tradução do modelo físico do SEEP para uma rede do pandapower.

Posição no pipeline do estudo:

    data.py  ->  storage.py  ->  **network.py**  ->  solver.py  ->
    protection.py  ->  app.py

Este é o único módulo que conhece a API do pandapower na hora de
*montar* a rede. Tudo o que vem antes dele é dicionário Python puro;
tudo o que vem depois recebe um objeto ``net`` já construído. Essa
fronteira é o que permite trocar o motor de cálculo sem reescrever o
modelo, e é também o que torna o modelo testável sem ter o pandapower
instalado.

Ponto de entrada
----------------
``build_network(case)`` devolve a rede montada para um dos três casos:

``"powerflow"``
    Resistência dos cabos na temperatura de operação exportada pelo
    relatório.
``"max"`` / ``"min"``
    Resistência a 20 °C, como nos relatórios da IEC 60909.

Decisões de projeto que valem explicar em aula
----------------------------------------------
* Gerador e motor fora de serviço (campo ``in_service``) simplesmente
  não entram na rede. É assim que a tela "Modelo físico" muda o nível
  de curto: não existe chave no cálculo, existe equipamento que deixa
  de existir.
* Sem nenhum gerador em serviço o sistema fica sem fonte e sem barra
  de referência, e a montagem é recusada com mensagem explícita, em
  vez de devolver um resultado sem significado.
* A rede carrega ``bus_name_map``, ``study_case`` e
  ``model_snapshot``, para que o solver consiga voltar do índice
  numérico do pandapower ao nome do equipamento sem consultar o banco
  de novo.
"""
from __future__ import annotations
from typing import Literal

from .storage import get_model
from .data import enrich_model


def _ohm_per_1000ft_to_ohm_per_km(value: float) -> float:
    return float(value) * 1000.0 / 304.8


def build_network(case: Literal["powerflow", "max", "min"] = "powerflow"):
    """Monta o caso reduzido no Pandapower.

    powerflow: R de cabos do Data Report (temperatura operacional
    exportada). max/min: R de cabos a 20 °C exatamente como nos
    relatórios IEC 60909.
    """
    try:
        import pandapower as pp
    except Exception as exc:
        raise RuntimeError("pandapower não está instalado. Execute setup_windows.bat.") from exc

    model = enrich_model(get_model())
    net = pp.create_empty_network(sn_mva=100.0, f_hz=float(model.get("frequency_hz", 60.0)))

    bus_map = {}
    for b in model["buses"]:
        bus_map[b["name"]] = pp.create_bus(net, vn_kv=float(b["kv"]), name=b["name"])

    # Geradores síncronos do caso. Como slack no fluxo, P/Q resultam da
    # rede. V30: um gerador pode estar fora de serviço (campo
    # "in_service"). Nesse caso ele não entra na rede, e a contribuição
    # dele para o curto-circuito desaparece — que é justamente o efeito
    # a ser demonstrado em aula.
    em_servico = [g for g in model["generators"] if bool(g.get("in_service", True))]
    if not em_servico:
        raise RuntimeError(
            "Nenhum gerador em serviço: o sistema fica sem fonte e sem barra de "
            "referência. Ligue ao menos um gerador na tela Modelo físico."
        )
    for g in em_servico:
        idx = pp.create_gen(
            net,
            bus=bus_map[g["bus"]],
            p_mw=0.0,
            vm_pu=1.0,
            sn_mva=float(g["sn_mva"]),
            name=g["name"],
            slack=True,
            slack_weight=1.0,
            vn_kv=float(g["kv"]),
            xdss_pu=float(g["xdss_pu"]),
            rdss_ohm=float(g["rdss_ohm"]),
            cos_phi=float(g["pf"]),
            pg_percent=0.0,
            in_service=True,
        )
        # Mantemos os dados completos de sequência no DataFrame para
        # diagnóstico e para o solver complementar de componentes
        # simétricas.
        for key in (
            "x0_pu", "r0_ohm", "x0_ohm", "x2_pu", "r2_ohm", "x2_ohm",
            "neutral_resistor_ohm", "neutral_current_a",
        ):
            net.gen.loc[idx, key] = float(g[key])

    # Cabos.
    for c in model["cables"]:
        parallel = max(1, int(c["parallel"]))
        if case == "powerflow":
            r1 = float(c["r1_pf_ohm_per_km"])
            x1 = float(c["x1_pf_ohm_per_km"])
            r0 = float(c["r0_pf_ohm_per_km"])
            x0 = float(c["x0_pf_ohm_per_km"])
        else:
            r1 = _ohm_per_1000ft_to_ohm_per_km(c["r1_sc20_ohm_per_1000ft"])
            x1 = _ohm_per_1000ft_to_ohm_per_km(c["x1_sc_ohm_per_1000ft"])
            r0 = _ohm_per_1000ft_to_ohm_per_km(c["r0_sc20_ohm_per_1000ft"])
            x0 = _ohm_per_1000ft_to_ohm_per_km(c["x0_sc_ohm_per_1000ft"])

        # Ampacidade não foi exportada para este caso. O valor numérico
        # alto só satisfaz a assinatura do Pandapower; NÃO é mostrado
        # como rating físico.
        idx = pp.create_line_from_parameters(
            net,
            from_bus=bus_map[c["from_bus"]],
            to_bus=bus_map[c["to_bus"]],
            length_km=float(c["length_km"]),
            r_ohm_per_km=r1,
            x_ohm_per_km=x1,
            c_nf_per_km=0.0,
            max_i_ka=999.0,
            parallel=parallel,
            name=c["name"],
            type="cs",
        )
        net.line.loc[idx, "r0_ohm_per_km"] = r0
        net.line.loc[idx, "x0_ohm_per_km"] = x0
        net.line.loc[idx, "c0_nf_per_km"] = 0.0
        net.line.loc[idx, "endtemp_degree"] = 75.0 if case == "powerflow" else 20.0
        net.line.loc[idx, "size_mm2"] = float(c["size_mm2"])
        net.line.loc[idx, "parallel_cond"] = parallel
        net.line.loc[idx, "ampacity_total_a"] = float("nan")

    # Transformadores Dyn ativos no modelo com secundário solidamente
    # aterrado.
    for t in model["transformers"]:
        tidx = pp.create_transformer_from_parameters(
            net,
            hv_bus=bus_map[t["hv_bus"]],
            lv_bus=bus_map[t["lv_bus"]],
            sn_mva=float(t["sn_mva"]),
            vn_hv_kv=float(t["vn_hv_kv"]),
            vn_lv_kv=float(t["vn_lv_kv"]),
            vk_percent=float(t["vk_percent"]),
            vkr_percent=float(t["vkr_percent"]),
            pfe_kw=0.0,
            i0_percent=0.0,
            shift_degree=float(t["shift_degree"]),
            vector_group=t["vector_group"],
            name=t["name"],
        )
        # Parâmetros de sequência zero exigidos pelo cálculo monofásico
        # do PP.
        net.trafo.loc[tidx, "vk0_percent"] = float(t["vk0_percent"])
        net.trafo.loc[tidx, "vkr0_percent"] = float(t["vkr0_percent"])
        net.trafo.loc[tidx, "mag0_percent"] = 100.0
        net.trafo.loc[tidx, "mag0_rx"] = 0.0
        net.trafo.loc[tidx, "si0_hv_partial"] = 0.9

    # Motores do fluxo, com os kVA de placa já cadastrados. V30: um
    # motor pode estar fora de serviço (campo "in_service"). Fora de
    # serviço ele não carrega a barra no fluxo e não contribui para o
    # curto — mesmo tratamento dado aos geradores.
    for m in model["motors"]:
        em_servico_m = bool(m.get("in_service", True))
        midx = pp.create_motor(
            net,
            bus=bus_map[m["bus"]],
            pn_mech_mw=float(m["kw"]) / 1000.0,
            cos_phi=float(m["pf"]),
            efficiency_percent=float(m["efficiency_percent"]),
            loading_percent=float(m["study_loading_percent"]),
            name=m["name"],
            lrc_pu=float(m["lrc_pu"]),
            vn_kv=float(m["kv"]),
            rx=float(m["rx"]),
            cos_phi_n=float(m["pf"]),
            efficiency_n_percent=float(m["efficiency_percent"]),
            in_service=em_servico_m,
        )
        net.motor.loc[midx, "model_amp"] = float(m["amp"])
        net.motor.loc[midx, "model_kva"] = float(m["kva"])
        net.motor.loc[midx, "r_percent"] = float(m["r_percent"])
        net.motor.loc[midx, "x_percent"] = float(m["x_percent"])
        net.motor.loc[midx, "x0_percent"] = float(m["x0_percent"])
        net.motor.loc[midx, "x2_percent"] = float(m["x2_percent"])
        net.motor.loc[midx, "sc_enabled"] = case != "min"

    net["bus_name_map"] = bus_map
    net["study_case"] = case
    net["model_snapshot"] = model
    return net
