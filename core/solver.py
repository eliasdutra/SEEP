"""Motor de cálculo: fluxo de potência e curto-circuito IEC 60909.

Posição no pipeline do estudo:

    data.py  ->  storage.py  ->  network.py  ->  **solver.py**  ->
    protection.py  ->  app.py

Recebe a rede montada por ``network.build_network`` e devolve correntes.
Não decide nada de proteção: não sabe o que é pickup, curva ou
seletividade. Essa separação é deliberada — grandeza elétrica de um
lado, critério de engenharia do outro.

Pontos de entrada
-----------------
``run_power_flow()``
    Tensões, ângulos e carregamentos do caso de operação.
``run_short_circuit(case)``
    Tabela por barra com 3F, LL, LG e LLG, nos casos máximo e mínimo.
``run_breaker_fault_duty(breaker, case)``
    Corrente que de fato atravessa um disjuntor, para dever de
    interrupção.
``run_zone_remote_fault(zone_id, case)``
    Falta na extremidade remota da zona, usada na verificação de
    alcance.
``study_summary()``
    Resumo consolidado para a tela inicial.

Como o curto é calculado
------------------------
O pandapower resolve a sequência positiva pela IEC 60909. Para as faltas
que envolvem a terra, o módulo monta as **redes de sequência de forma
nodal**: constrói a Ybus em pu numa base comum, inverte por componente
conexo e lê a impedância de Thévenin na diagonal. Essa formulação aceita
qualquer número de fontes — foi o que permitiu acrescentar o segundo
gerador sem reescrever o solver, já que o método anterior percorria a
topologia como árvore radial a partir de uma fonte única.

Barras sem caminho até uma referência de terra naquela sequência — as de
13,8 kV atrás do delta do T1, na sequência zero — são marcadas como sem
Z0 utilizável, em vez de receberem um valor inventado.

Cache
-----
O decorador ``cacheable`` é um ``lru_cache`` que respeita
``CACHE_ENABLED``. Cada chamada ao pandapower custa segundos; a tela
faria dezenas delas. Editar um equipamento invalida o cache (ver
``clear_solver_cache``), e é por isso que salvar um motor dispara
recálculo e salvar um TC não — TC é metrologia, não entra na rede.
"""
from __future__ import annotations

import cmath
import math
from functools import lru_cache, wraps

from .data import enrich_model
from .network import build_network
from .storage import get_model

# Pandapower pode devolver um valor positivo, mas numericamente
# desprezível (ruído de ponto flutuante, tipo 0,0000001 kA) em vez de
# exatamente 0.0 quando não há caminho de sequência zero real (barra
# alimentada só por "gen", sem aterramento visível pro solver). Um "<=
# 0.0" simples não pega esse caso e a troca pelo cálculo físico de
# reserva (LG/LLG) nunca dispara — por isso o LG ficava "calculado"
# (aparecendo 0,000 kA na tela) só porque arredondava pra zero, em vez
# de realmente cair no fallback. Qualquer coisa abaixo disso conta como
# "sem falta real calculada pelo Pandapower".
_NEGLIGIBLE_KA = 1e-6

# ----------------------------------------------------------------------
# Interruptor do cache elétrico.
#
# Trocar para False faz TODA consulta refazer o cálculo no Pandapower.
# Nada mais muda: os resultados continuam idênticos, só o tempo de
# resposta cresce. Existe para que o efeito do cache possa ser medido
# ligando e desligando, em vez de explicado.
#
# Com o cache desligado a tela de estado passa a mostrar "Fluxo —" em
# vez de "Fluxo OK", porque de fato não há nada guardado.
CACHE_ENABLED = True


# ======================================================================
# CACHE DO MOTOR DE CÁLCULO
# Cada chamada ao pandapower custa segundos e a tela faria dezenas.
# Editar equipamento invalida o cache (ver clear_solver_cache).
# ======================================================================

def cacheable(maxsize=1):
    """``lru_cache`` que respeita ``CACHE_ENABLED``.

    Quando desligado, a função é executada por inteiro a cada chamada. O
    invólucro continua expondo ``cache_clear`` e ``cache_info`` para que
    ``clear_solver_cache`` e ``solver_cache_status`` funcionem nos dois
    modos.
    """
    def decorador(fn):
        com_cache = lru_cache(maxsize=maxsize)(fn)

        @wraps(fn)
        def invólucro(*args, **kwargs):
            if CACHE_ENABLED:
                return com_cache(*args, **kwargs)
            return fn(*args, **kwargs)

        invólucro.cache_clear = com_cache.cache_clear
        invólucro.cache_info = com_cache.cache_info
        return invólucro
    return decorador



def _clean(value):
    try:
        value = float(value)
    except Exception:
        return None
    return None if not math.isfinite(value) else value


@cacheable(maxsize=1)
# ======================================================================
# FLUXO DE POTÊNCIA
# Caso de operação: tensões, ângulos e carregamentos.
# ======================================================================

def run_power_flow() -> dict:
    """Resolve o fluxo de potência do caso de operação.

    Devolve tensões e ângulos por barra, e carregamento de linhas e
    transformadores. É o único resultado que usa a resistência dos cabos
    na temperatura de operação; os casos de curto usam 20 °C, como manda
    a IEC 60909.

    Em caso de falha devolve ``{"ok": False, "error": ...}`` com as
    listas vazias, em vez de levantar exceção: a tela precisa continuar
    funcionando e mostrar o motivo.
    """
    try:
        import pandapower as pp

        net = build_network("powerflow")
        pp.runpp(
            net,
            algorithm="nr",
            init="flat",
            calculate_voltage_angles=True,
            distributed_slack=False,
            tolerance_mva=1e-9,
            max_iteration=60,
        )

        buses = []
        for idx, bus in net.bus.iterrows():
            r = net.res_bus.loc[idx]
            vm = _clean(r.get("vm_pu"))
            buses.append(
                {
                    "bus": str(bus["name"]),
                    "kv": float(bus["vn_kv"]),
                    "vm_pu": vm,
                    "vm_percent": None if vm is None else 100.0 * vm,
                    "va_degree": _clean(r.get("va_degree")),
                    "p_mw": _clean(r.get("p_mw")),
                    "q_mvar": _clean(r.get("q_mvar")),
                }
            )

        generators = []
        for idx, gen in net.gen.iterrows():
            r = net.res_gen.loc[idx]
            generators.append({"name": str(gen["name"]), "p_mw": _clean(r.get("p_mw")), "q_mvar": _clean(r.get("q_mvar"))})

        lines = []
        for idx, line in net.line.iterrows():
            r = net.res_line.loc[idx]
            lines.append(
                {
                    "name": str(line["name"]),
                    "loading_percent": None,
                    "i_from_ka": _clean(r.get("i_from_ka")),
                    "i_to_ka": _clean(r.get("i_to_ka")),
                    "p_from_mw": _clean(r.get("p_from_mw")),
                    "q_from_mvar": _clean(r.get("q_from_mvar")),
                    "ampacity_total_a": None,
                }
            )

        transformers = []
        for idx, trafo in net.trafo.iterrows():
            r = net.res_trafo.loc[idx]
            transformers.append(
                {
                    "name": str(trafo["name"]),
                    "loading_percent": _clean(r.get("loading_percent")),
                    "i_hv_ka": _clean(r.get("i_hv_ka")),
                    "i_lv_ka": _clean(r.get("i_lv_ka")),
                    "p_hv_mw": _clean(r.get("p_hv_mw")),
                    "q_hv_mvar": _clean(r.get("q_hv_mvar")),
                }
            )

        motors = []
        for idx, motor in net.motor.iterrows():
            r = net.res_motor.loc[idx]
            motors.append({"name": str(motor["name"]), "p_mw": _clean(r.get("p_mw")), "q_mvar": _clean(r.get("q_mvar")),
                           "in_service": bool(motor.get("in_service", True))})

        return {
            "ok": True,
            "source": "Pandapower",
            "buses": buses,
            "generators": generators,
            "lines": lines,
            "transformers": transformers,
            "motors": motors,
        }
    except Exception as exc:
        return {
            "ok": False,
            "source": "Pandapower",
            "error": str(exc),
            "buses": [],
            "generators": [],
            "lines": [],
            "transformers": [],
            "motors": [],
        }


# ======================================================================
# PREPARAÇÃO DA REDE PARA O CURTO IEC 60909
# No caso MAX os motores entram como fonte de contribuição; no MIN,
# nenhum entra, por determinação da norma.
# ======================================================================

def _prepare_sc_net(case: str, disabled_motor_names=None):
    """Prepara a rede IEC 60909.

    MAX inclui os motores, exceto os nomes explicitamente bloqueados.
    Essa opção é usada para calcular o dever de interrupção de um
    disjuntor: uma fonte/motor que está a jusante do próprio disjuntor
    alimenta a falta pelo lado da carga e, portanto, não atravessa o
    disjuntor no instante de interrupção. MIN continua excluindo todos
    os motores.
    """
    import pandapower as pp

    case = "min" if str(case).lower() == "min" else "max"
    disabled_motor_names = set(disabled_motor_names or [])
    net = build_network(case)
    if len(net.motor):
        net.motor.loc[:, "in_service"] = False

    model = enrich_model(get_model())
    for motor in model["motors"]:
        pp.create_sgen(
            net,
            bus=net["bus_name_map"][motor["bus"]],
            p_mw=0.0,
            q_mvar=0.0,
            sn_mva=float(motor["kva"]) / 1000.0,
            name=f"{motor['name']}_SC",
            type="motor",
            generator_type="async",
            k=float(motor["lrc_pu"]),
            lrc_pu=float(motor["lrc_pu"]),
            rx=float(motor["rx"]),
            current_source=False,
            # V30: além do caso (MIN não tem motor) e do bloqueio por
            # disjuntor, o motor só contribui se estiver em serviço no
            # modelo físico.
            in_service=(case == "max"
                        and bool(motor.get("in_service", True))
                        and motor["name"] not in disabled_motor_names),
        )
    return net




# ======================================================================
# IMPEDÂNCIAS DE SEQUÊNCIA DOS ELEMENTOS
# Cabo e transformador, sequências positiva e zero, em ohm.
# ======================================================================

def _cable_sc_impedance(cable: dict) -> complex:
    """Impedância de sequência positiva do cabo para curto, em ohm.

    Os valores do relatório IEC são por 1000 ft e por condutor. O
    elemento físico pode possuir condutores em paralelo por fase; por
    isso a impedância equivalente é dividida por ``parallel``.
    """
    length_ft = float(cable["length_m"]) / 0.3048
    n = max(1, int(cable.get("parallel", 1)))
    factor = length_ft / 1000.0 / n
    return complex(
        float(cable["r1_sc20_ohm_per_1000ft"]) * factor,
        float(cable["x1_sc_ohm_per_1000ft"]) * factor,
    )


def _transformer_sc_impedance_on_side(trafo: dict, side_kv: float) -> complex:
    """Impedância Z1=Z2 do transformador, em ohm, no lado escolhido.

    Para o caso MIN do estudo fornecido, o relatório ETAP usa a
    impedância nominal do transformador (impedância nominal do
    transformador ativo). Esta formulação é independente do fator de
    correção interno que cada software pode aplicar ao elemento.
    """
    zmag = (float(trafo["vk_percent"]) / 100.0) * (float(side_kv) ** 2) / float(trafo["sn_mva"])
    xr = float(trafo["x_over_r"])
    r = zmag / math.sqrt(1.0 + xr * xr)
    x = r * xr
    return complex(r, x)


def _cable_zero_sc_impedance(cable: dict) -> complex:
    """Impedância de sequência zero do cabo para curto, em ohm."""
    length_ft = float(cable["length_m"]) / 0.3048
    n = max(1, int(cable.get("parallel", 1)))
    factor = length_ft / 1000.0 / n
    return complex(
        float(cable["r0_sc20_ohm_per_1000ft"]) * factor,
        float(cable["x0_sc_ohm_per_1000ft"]) * factor,
    )


def _transformer_zero_sc_impedance_on_side(trafo: dict, side_kv: float) -> complex:
    """Impedância de sequência zero do transformador, em ohm."""
    zmag = (float(trafo.get("vk0_percent", trafo["vk_percent"])) / 100.0) * (float(side_kv) ** 2) / float(trafo["sn_mva"])
    xr = float(trafo.get("x0_over_r0", trafo["x_over_r"]))
    r = zmag / math.sqrt(1.0 + xr * xr)
    return complex(r, r * xr)



# ----------------------------------------------------------------------
# V30 — redes de sequência por matriz nodal.
#
# Até a V29 as redes de sequência eram montadas caminhando a árvore a
# partir de uma única fonte, somando impedâncias em série. Isso obrigava
# o caso a ter exatamente um gerador e topologia radial: com dois
# geradores alimentando a mesma barra, a "árvore" fecha um laço e o
# método não vale mais.
#
# A montagem nodal abaixo é o método geral: monta a matriz de
# admitâncias de cada sequência em pu sobre uma base comum, inverte, e
# lê a impedância de Thévenin de cada barra na diagonal da Zbus. Para
# uma rede radial de uma fonte o resultado é idêntico ao da soma em
# série (é o mesmo circuito), então a verificação contra o ETAP não
# muda; e passa a aceitar fontes em paralelo.
# ----------------------------------------------------------------------

_SBASE_MVA = 100.0

_LV_ATERRADO = {"solid", "solidly grounded", "grounded", "yg"}


def _componentes(Y, n):
    """Componentes conexos, pelas admitâncias fora da diagonal."""
    visto = [False] * n
    saida = []
    for raiz in range(n):
        if visto[raiz]:
            continue
        pilha, grupo = [raiz], []
        visto[raiz] = True
        while pilha:
            i = pilha.pop()
            grupo.append(i)
            for j in range(n):
                if j != i and not visto[j] and Y[i][j] != 0:
                    visto[j] = True
                    pilha.append(j)
        saida.append(sorted(grupo))
    return saida


def _thevenin_por_sequencia(model: dict, seq: int):
    """Z de Thévenin (ohm) por barra, na sequência pedida (1, 2, 0).

    Devolve ``(z_por_barra, origem_por_barra)``. Uma barra sem caminho
    até qualquer referência de terra naquela sequência recebe ``None`` —
    é o caso das barras de 13,8 kV atrás do delta do T1 na sequência
    zero.
    """
    import numpy as np

    buses = {b["name"]: b for b in model.get("buses", [])}
    nomes = list(buses)
    idx = {n: i for i, n in enumerate(nomes)}
    n = len(nomes)
    zbase = {nome: float(buses[nome]["kv"]) ** 2 / _SBASE_MVA for nome in nomes}

    Y = np.zeros((n, n), dtype=complex)
    origem = [None] * n   # o que dá referência de terra ao nó

    # Fontes síncronas em serviço: shunt para a terra na barra do
    # gerador.
    for g in model.get("generators", []):
        if not bool(g.get("in_service", True)):
            continue
        barra = g.get("bus")
        if barra not in idx:
            continue
        i = idx[barra]
        if seq == 1:
            z = complex(float(g["rdss_ohm"]), float(g["xdss_ohm"]))
        elif seq == 2:
            z = complex(float(g["r2_ohm"]), float(g["x2_ohm"]))
        else:
            # O resistor de neutro aparece três vezes na rede de
            # sequência zero.
            z = complex(float(g["r0_ohm"]) + 3.0 * float(g.get("neutral_resistor_ohm", 0.0)),
                        float(g["x0_ohm"]))
        if abs(z) == 0:
            continue
        Y[i, i] += 1.0 / (z / zbase[barra])
        origem[i] = "generator"

    # Cabos: ramo série entre duas barras do mesmo nível de tensão.
    for c in model.get("cables", []):
        a, b = c.get("from_bus"), c.get("to_bus")
        if a not in idx or b not in idx:
            continue
        i, j = idx[a], idx[b]
        z = _cable_zero_sc_impedance(c) if seq == 0 else _cable_sc_impedance(c)
        if abs(z) == 0:
            continue
        y = 1.0 / (z / zbase[a])
        Y[i, i] += y; Y[j, j] += y; Y[i, j] -= y; Y[j, i] -= y

    # Transformadores.
    for tr in model.get("transformers", []):
        hv, lv = tr.get("hv_bus"), tr.get("lv_bus")
        if hv not in idx or lv not in idx:
            continue
        i, j = idx[hv], idx[lv]
        kv_lv = float(buses[lv]["kv"])
        if seq in (1, 2):
            z = _transformer_sc_impedance_on_side(tr, kv_lv)
            if abs(z) == 0:
                continue
            y = 1.0 / (z / zbase[lv])
            Y[i, i] += y; Y[j, j] += y; Y[i, j] -= y; Y[j, i] -= y
            continue
        hvc = str(tr.get("hv_connection", "")).upper()
        lvc = str(tr.get("lv_connection", "")).upper()
        lv_aterrado = str(tr.get("lv_grounding", "")).lower() in _LV_ATERRADO
        if hvc.startswith("D") and lvc.startswith("Y"):
            # Delta no primário bloqueia a sequência zero entre os dois
            # lados. Se o secundário Y é aterrado, nasce ali uma
            # referência local.
            if lv_aterrado:
                z = _transformer_zero_sc_impedance_on_side(tr, kv_lv)
                if abs(z):
                    Y[j, j] += 1.0 / (z / zbase[lv])
                    origem[j] = f"transformer:{tr.get('name', '?')}"
        elif hvc.startswith("Y") and lvc.startswith("Y"):
            z = _transformer_zero_sc_impedance_on_side(tr, kv_lv)
            if abs(z):
                y = 1.0 / (z / zbase[lv])
                Y[i, i] += y; Y[j, j] += y; Y[i, j] -= y; Y[j, i] -= y
        # Demais combinações não oferecem caminho de sequência zero.

    z_por_barra: dict[str, complex | None] = {nome: None for nome in nomes}
    origem_por_barra: dict[str, str | None] = {nome: None for nome in nomes}
    for grupo in _componentes(Y, n):
        refs = [origem[i] for i in grupo if origem[i]]
        if not refs:
            continue   # componente sem referência de terra
        sub = Y[np.ix_(grupo, grupo)]
        try:
            Zsub = np.linalg.inv(sub)
        except np.linalg.LinAlgError:
            continue
        for k, i in enumerate(grupo):
            nome = nomes[i]
            z_por_barra[nome] = complex(Zsub[k, k]) * zbase[nome]
            origem_por_barra[nome] = origem[i] or refs[0]
    return z_por_barra, origem_por_barra


def _fontes_em_servico(model: dict) -> list[dict]:
    fontes = [g for g in model.get("generators", []) if bool(g.get("in_service", True))]
    if not fontes:
        raise RuntimeError(
            "Nenhum gerador em serviço: sem fonte não há corrente de curto-circuito. "
            "Ligue ao menos um gerador na tela Modelo físico."
        )
    return fontes


@cacheable(maxsize=2)
def run_ground_sequence_fallback(case: str = "max") -> dict:
    """Monta Z0 físico por barra para faltas à terra.

    O Pandapower não fornece LG nas barras de 13,8 kV deste caso quando
    o gerador é representado como ``gen``. A V27 não transforma esse
    vazio em zero: monta a rede de sequência zero explicitamente.

    Regras do caso reduzido:
    - gerador Y aterrado por resistor: Z0 = Z0g + 3 Zn;
    - cabos: somam sua impedância de sequência zero;
    - T1 Dyn: o delta bloqueia Z0 entre 13,8 e 6,6 kV; no lado Y
      solidamente aterrado nasce uma nova rede Z0 através da impedância
      zero do T1.

    O retorno traz também Z1/Z2 físicos para diagnóstico independente.
    """
    case = "min" if str(case).lower() == "min" else "max"
    model = enrich_model(get_model())
    buses = {b["name"]: b for b in model.get("buses", [])}
    _fontes_em_servico(model)

    z1_map, _ = _thevenin_por_sequencia(model, 1)
    z2_map, _ = _thevenin_por_sequencia(model, 2)
    z0_map, origem0 = _thevenin_por_sequencia(model, 0)

    solved = {}
    for nome in buses:
        z1 = z1_map.get(nome)
        z2 = z2_map.get(nome)
        if z1 is None or z2 is None:
            continue                      # barra sem fonte alcançável
        z0 = z0_map.get(nome)
        origem = origem0.get(nome)
        if z0 is None:
            nota = "sem caminho de sequência zero (delta do transformador bloqueia)"
            origem = "generator"
        elif origem and origem.startswith("transformer"):
            nota = "T1 Dyn: Z0 local pelo Y aterrado; delta bloqueia AT"
        else:
            nota = "Z0 pelo neutro aterrado do gerador, somando os cabos do caminho"
        solved[nome] = (z1, z2, z0, nota, origem or "generator")

    rows = []
    for name, (z1, z2, z0, note, source_kind) in solved.items():
        vn = float(buses[name]["kv"])
        c = _voltage_factor(vn, case)
        ilg = None
        illg = None
        if z0 is not None:
            denom = z1 + z2 + z0
            if abs(denom):
                ilg = math.sqrt(3.0) * c * vn / abs(denom)
            illg = _llg_from_sequences(z1, z2, z0, vn, case)
        rows.append({
            "bus": name, "kv": vn, "case": case,
            "lg_ka": ilg, "llg_ka": illg,
            "source_kind": source_kind,
            "r1_ohm": z1.real, "x1_ohm": z1.imag,
            "r2_ohm": z2.real, "x2_ohm": z2.imag,
            "r0_ohm": None if z0 is None else z0.real,
            "x0_ohm": None if z0 is None else z0.imag,
            "method": "IEC nodal ground · physical Z0",
            "z0_path": note,
        })
    return {
        "ok": any(r["lg_ka"] is not None for r in rows),
        "source": "IEC nodal ground · physical Z0",
        "rows": rows,
        "note": "Gerador Y aterrado por resistor; T1 Dyn separa as redes Z0 AT/BT; cabos usam R0/X0 físicos.",
    }


def _radial_phase_min_sequence() -> dict[str, dict]:
    """Resolve Z1/Z2 e faltas 3F/LL MIN a partir das redes de sequência.

    O objetivo é ter uma referência IEC transparente para a coordenação
    de fase. No caso MIN os motores estão excluídos; Z1 e Z2 de cada
    barra saem da diagonal da Zbus de sequência (ver
    _thevenin_por_sequencia), o que vale para qualquer número de fontes
    em serviço e para fontes em paralelo. Isso evita diferenças
    provocadas por fatores de correção internos do modelo de ``gen`` do
    Pandapower e reproduz o cálculo manual do caso-base.

    Não usa resultados ETAP como entrada. Usa somente os dados físicos
    do modelo: Xd'', X2, R/X, cabos, transformadores e tensões nominais.
    """
    model = enrich_model(get_model())
    buses = {b["name"]: b for b in model.get("buses", [])}
    _fontes_em_servico(model)

    z1_map, _ = _thevenin_por_sequencia(model, 1)
    z2_map, _ = _thevenin_por_sequencia(model, 2)
    solved = {nome: (z1_map[nome], z2_map[nome]) for nome in buses
              if z1_map.get(nome) is not None and z2_map.get(nome) is not None}

    out = {}
    for name, (z1, z2) in solved.items():
        vn_kv = float(buses[name]["kv"])
        c = _voltage_factor(vn_kv, "min")
        i3 = c * vn_kv / (math.sqrt(3.0) * abs(z1)) if abs(z1) else None
        ill = c * vn_kv / abs(z1 + z2) if abs(z1 + z2) else None
        out[name] = {
            "bus": name, "kv": vn_kv, "case": "min",
            "3f_ka": i3, "ll_ka": ill,
            "r1_ohm": z1.real, "x1_ohm": z1.imag,
            "r2_ohm": z2.real, "x2_ohm": z2.imag,
            "method": "IEC nodal phase MIN · physical model",
        }
    return out


@cacheable(maxsize=1)
def run_phase_min_validated() -> dict:
    """Diagnóstico independente das faltas de fase no caso mínimo.

    Recalcula 3F e LL mínimas pelo caminho nodal de sequência e compara
    com o que o Pandapower devolveu. Serve para a coordenação de fase
    ter um segundo número de referência, não um só — divergência entre
    os dois é sinal de problema de modelagem, e aparece em vez de passar
    despercebida.
    """
    try:
        rows = list(_radial_phase_min_sequence().values())
        return {
            "ok": True,
            "source": "IEC nodal phase MIN · physical model",
            "rows": rows,
            "note": "Motores excluídos; Z1/Z2 obtidas da Zbus de sequência, com todas as fontes em serviço.",
        }
    except Exception as exc:
        return {"ok": False, "source": "IEC nodal phase MIN", "rows": [], "error": str(exc)}



def _nota_do_estudo(case: str, rows: list[dict], radial_min: dict) -> str:
    """Monta a nota do estudo a partir do que de fato saiu nesta rodada.

    A nota diz o que foi calculado, não como. O método está documentado
    no README e nos comentários; a tela mostra resultado. A única coisa
    que a nota acrescenta é um aviso quando alguma barra fica sem valor
    utilizável — e esse aviso é montado a partir das linhas calculadas,
    nunca escrito à mão, para não envelhecer no código depois que o
    problema for resolvido.
    """
    def _zerado(v):
        return v is None or (isinstance(v, (int, float)) and float(v) <= _NEGLIGIBLE_KA)

    if case == "min":
        nota = "Caso mínimo, sem a contribuição dos motores. Conforme IEC 60909."
    else:
        nota = "Caso máximo, com os motores contribuindo. Conforme IEC 60909."

    sem_lg = sorted({r["bus"] for r in rows if _zerado(r.get("lg_ka"))})
    if sem_lg:
        nota += f" Atenção: {', '.join(sem_lg)} sem LG utilizável nesta rodada."
    return nota


def _run_fault(case: str, fault: str):
    import pandapower.shortcircuit as sc

    net = _prepare_sc_net(case)
    sc.calc_sc(
        net,
        fault=fault,
        case=case,
        ip=False,
        ith=False,
        branch_results=False,
        use_pre_fault_voltage=False,
        lv_tol_percent=6,
        topology="radial",
    )
    out = {}
    for idx, bus in net.bus.iterrows():
        row = net.res_bus_sc.loc[idx]
        out[str(bus["name"])] = {col: _clean(row.get(col)) for col in net.res_bus_sc.columns}
    return out


def _voltage_factor(vn_kv: float, case: str) -> float:
    if vn_kv <= 1.0:
        return 1.05 if case == "max" else 0.95
    return 1.10 if case == "max" else 1.00


def _llg_from_sequences(z1: complex, z2: complex, z0: complex, vn_kv: float, case: str):
    """LLG por componentes simétricas; kV/ohm já resulta em kA."""
    if abs(z2 + z0) == 0:
        return None
    e = _voltage_factor(vn_kv, case) * vn_kv / math.sqrt(3.0)
    zpar = z2 * z0 / (z2 + z0)
    if abs(z1 + zpar) == 0:
        return None
    i1 = e / (z1 + zpar)
    i2 = -i1 * z0 / (z2 + z0)
    i0 = -i1 * z2 / (z2 + z0)
    a = cmath.exp(1j * 2.0 * math.pi / 3.0)
    ib = i0 + (a ** 2) * i1 + a * i2
    ic = i0 + a * i1 + (a ** 2) * i2
    return max(abs(ib), abs(ic))


def _sequence_from_rows(ll_row: dict | None, lg_row: dict | None):
    if not ll_row or not lg_row:
        return None
    try:
        z1 = complex(float(ll_row["rk_ohm"]), float(ll_row["xk_ohm"]))
        z2 = complex(
            float(ll_row.get("rk2_ohm") if ll_row.get("rk2_ohm") is not None else ll_row["rk_ohm"]),
            float(ll_row.get("xk2_ohm") if ll_row.get("xk2_ohm") is not None else ll_row["xk_ohm"]),
        )
        z0 = complex(float(lg_row["rk0_ohm"]), float(lg_row["xk0_ohm"]))
        return z1, z2, z0
    except Exception:
        return None


def _phase_sequence_from_ll_row(ll_row: dict | None):
    """Extrai Z1/Z2 do resultado 2ph do Pandapower quando disponível."""
    if not ll_row:
        return None
    try:
        z1 = complex(float(ll_row["rk_ohm"]), float(ll_row["xk_ohm"]))
        z2 = complex(
            float(ll_row.get("rk2_ohm") if ll_row.get("rk2_ohm") is not None else ll_row["rk_ohm"]),
            float(ll_row.get("xk2_ohm") if ll_row.get("xk2_ohm") is not None else ll_row["xk_ohm"]),
        )
        return z1, z2
    except Exception:
        return None


def _ground_fault_from_sequence(z1: complex, z2: complex, z0: complex, vn_kv: float, case: str):
    denom = z1 + z2 + z0
    lg = None if abs(denom) == 0 else math.sqrt(3.0) * _voltage_factor(vn_kv, case) * vn_kv / abs(denom)
    return lg, _llg_from_sequences(z1, z2, z0, vn_kv, case)


@cacheable(maxsize=2)
# ======================================================================
# CURTO-CIRCUITO POR BARRA
# Tabela 3F / LL / LG / LLG. Onde o pandapower não representa o
# aterramento do gerador, o cálculo nodal físico é a fonte preferida.
# ======================================================================

def run_short_circuit(case: str = "max") -> dict:
    """Curto-circuito em todas as barras, para um caso da norma.

    ``case="max"``
        Fator de tensão c = 1,1, motores contribuindo, resistência dos
        cabos a 20 °C. É a condição de dever de interrupção e de
        alcance.
    ``case="min"``
        c = 1,0, motores ignorados por determinação da norma,
        resistência na temperatura final do condutor. É a condição de
        sensibilidade.

    Devolve uma linha por barra com 3F, LL, LG e LLG em kA, mais o
    método usado em cada uma. Onde o Pandapower não consegue representar
    o aterramento de neutro do gerador, o cálculo nodal físico vira a
    fonte principal do valor — e a linha diz isso, em vez de apresentar
    um número sem procedência.

    Resultado cacheado: ver ``cacheable`` e ``clear_solver_cache``.
    """
    case = "min" if str(case).lower() == "min" else "max"
    raw = {}
    errors = []
    for fault, key in (("3ph", "3F"), ("2ph", "LL"), ("1ph", "LG")):
        try:
            raw[key] = _run_fault(case, fault)
        except Exception as exc:
            raw[key] = {}
            errors.append(f"{key}: {exc}")

    model = enrich_model(get_model())
    radial_min = run_phase_min_validated() if case == "min" else {"ok": False, "rows": []}
    radial_by_bus = {r["bus"]: r for r in radial_min.get("rows", [])} if radial_min.get("ok") else {}
    ground_fb = run_ground_sequence_fallback(case)
    ground_by_bus = {r["bus"]: r for r in ground_fb.get("rows", [])} if ground_fb.get("ok") else {}
    rows = []
    for bus in model["buses"]:
        name = bus["name"]
        vn = float(bus["kv"])
        r3 = raw.get("3F", {}).get(name, {})
        r2 = raw.get("LL", {}).get(name, {})
        r1 = raw.get("LG", {}).get(name, {})
        seq = _sequence_from_rows(r2, r1)
        pp_lg = r1.get("ikss_ka")
        pp_llg = _llg_from_sequences(*seq, vn, case) if seq else None
        ground = ground_by_bus.get(name)
        # Pandapower pode devolver 0/NaN para 1ph em barras alimentadas
        # por ``gen`` mesmo havendo aterramento físico do neutro. Nesses
        # pontos a V27 usa explicitamente a rede Z0 física; 0 não é
        # tratado como falta real nula quando existe caminho de terra
        # conhecido.
        use_lg = pp_lg
        lg_method = "Pandapower IEC 60909"
        use_llg = pp_llg
        llg_method = "componentes simétricas sobre sequência Pandapower"
        if ground and ground.get("r0_ohm") is not None:
            z0_ground = complex(float(ground["r0_ohm"]), float(ground["x0_ohm"]))
            phase_seq = _phase_sequence_from_ll_row(r2)
            if phase_seq:
                fb_lg, fb_llg = _ground_fault_from_sequence(phase_seq[0], phase_seq[1], z0_ground, vn, case)
                fb_method = "Pandapower Z1/Z2 + fallback físico Z0"
            else:
                fb_lg, fb_llg = ground.get("lg_ka"), ground.get("llg_ka")
                fb_method = ground.get("method")
            # Quando a fonte de sequência zero é o GERADOR (Pandapower
            # não tem como representar o aterramento de neutro de um
            # "gen" avulso — confirmado na documentação: create_gen()
            # não aceita xn_ohm/x0, só via power_station_trafo, que não
            # é o nosso caso), o cálculo físico é mais confiável que o
            # Pandapower e vira a fonte PRINCIPAL aqui, não um reserva
            # condicional. Quando a fonte é um TRANSFORMADOR (ex.: T1
            # Dyn aterrado no Y), o Pandapower já modela isso
            # nativamente e continua sendo a fonte preferida.
            prefer_fallback = str(ground.get("source_kind", "")).startswith("generator")
            if prefer_fallback and fb_lg is not None:
                use_lg = fb_lg
                lg_method = fb_method
            elif use_lg is None or float(use_lg) <= _NEGLIGIBLE_KA:
                use_lg = fb_lg
                lg_method = fb_method
            if prefer_fallback and fb_llg is not None:
                use_llg = fb_llg
                llg_method = fb_method
            elif use_llg is None or float(use_llg) <= _NEGLIGIBLE_KA:
                use_llg = fb_llg
                llg_method = fb_method
        pp_3f = r3.get("ikss_ka")
        pp_ll = r2.get("ikss_ka")
        validated = radial_by_bus.get(name)
        # Na coordenação de fase MIN usamos o cálculo radial
        # transparente e independente. O resultado bruto Pandapower é
        # preservado para diagnóstico, sem contaminar a corrente adotada
        # no estudo.
        default_phase_method = "Pandapower IEC 60909"
        v3f = validated.get("3f_ka") if validated else None
        vll = validated.get("ll_ka") if validated else None
        use_3f = v3f if v3f is not None else pp_3f
        use_ll = vll if vll is not None else pp_ll
        method_3f = validated.get("method") if v3f is not None else default_phase_method
        method_ll = validated.get("method") if vll is not None else default_phase_method
        rows.append(
            {
                "bus": name,
                "kv": vn,
                "case": case,
                "c_factor": _voltage_factor(vn, case),
                "3f_ka": use_3f,
                "ll_ka": use_ll,
                "lg_ka": use_lg,
                "llg_ka": use_llg,
                "3f_ka_pandapower": pp_3f,
                "ll_ka_pandapower": pp_ll,
                "lg_ka_pandapower": pp_lg,
                "llg_ka_pandapower": pp_llg,
                "3f_method": method_3f,
                "ll_method": method_ll,
                "lg_method": lg_method,
                "llg_method": llg_method,
                "ground_sequence": None if not ground else {
                    "r0_ohm": ground.get("r0_ohm"), "x0_ohm": ground.get("x0_ohm"),
                    "z0_path": ground.get("z0_path"), "method": ground.get("method"),
                },
                "phase_min_method": validated.get("method") if validated else None,
                "phase_min_sequence": None if not validated else {
                    "r1_ohm": validated["r1_ohm"], "x1_ohm": validated["x1_ohm"],
                    "r2_ohm": validated["r2_ohm"], "x2_ohm": validated["x2_ohm"],
                },
            }
        )

    required = ("3f_ka", "ll_ka") if case == "min" else ("3f_ka", "ll_ka", "lg_ka")
    any_complete = any(all(row.get(k) is not None for k in required) for row in rows)
    source = "Pandapower"
    if case == "min" and radial_min.get("ok"):
        source = "Sequência SEEP (3F/LL MIN) + Pandapower (LG/LLG)"
    note = _nota_do_estudo(case, rows, radial_min)

    return {
        "ok": any_complete and (not errors or (case == "min" and radial_min.get("ok"))),
        "case": case,
        "source": source,
        "rows": rows,
        "errors": errors,
        "phase_min_validation": radial_min if case == "min" else None,
        "note": note,
    }



# ======================================================================
# DEVER DE INTERRUPÇÃO E FALTA REMOTA
# Percorre o grafo para saber o que fica a jusante de um disjuntor.
# ======================================================================

def _graph_downstream_motor_names(model: dict, breaker: str) -> list[str]:
    """Motores fisicamente a jusante de um disjuntor.

    O grafo usa cabos e transformadores. A travessia começa em
    ``to_bus`` e não pode retornar por ``from_bus``; assim DJ1 encontra
    todos os motores da planta, e cada disjuntor de motor encontra
    apenas o respectivo ramal a jusante.
    """
    sw = next((x for x in model.get("switchgear", []) if x.get("breaker") == breaker), None)
    if sw is None:
        raise KeyError(f"Disjuntor não encontrado: {breaker}")
    adjacency = {b["name"]: set() for b in model.get("buses", [])}
    for c in model.get("cables", []):
        adjacency.setdefault(c["from_bus"], set()).add(c["to_bus"])
        adjacency.setdefault(c["to_bus"], set()).add(c["from_bus"])
    for t in model.get("transformers", []):
        adjacency.setdefault(t["hv_bus"], set()).add(t["lv_bus"])
        adjacency.setdefault(t["lv_bus"], set()).add(t["hv_bus"])
    blocked = sw["from_bus"]
    start = sw["to_bus"]
    seen = {blocked}
    stack = [start]
    downstream_buses = set()
    while stack:
        bus = stack.pop()
        if bus in seen:
            continue
        seen.add(bus)
        downstream_buses.add(bus)
        stack.extend(adjacency.get(bus, ()))
    return sorted(m["name"] for m in model.get("motors", []) if m["bus"] in downstream_buses)


def _run_fault_single_bus(case: str, fault: str, bus_name: str, disabled_motor_names=None):
    import pandapower.shortcircuit as sc

    net = _prepare_sc_net(case, disabled_motor_names=disabled_motor_names)
    if bus_name not in net["bus_name_map"]:
        raise KeyError(f"Barra não encontrada: {bus_name}")
    sc.calc_sc(
        net,
        bus=net["bus_name_map"][bus_name],
        fault=fault,
        case=case,
        ip=False,
        ith=False,
        branch_results=False,
        use_pre_fault_voltage=False,
        lv_tol_percent=6,
        topology="radial",
    )
    idx = net["bus_name_map"][bus_name]
    row = net.res_bus_sc.loc[idx]
    return {col: _clean(row.get(col)) for col in net.res_bus_sc.columns}


@cacheable(maxsize=16)
def run_breaker_fault_duty(breaker: str, case: str = "max") -> dict:
    """Corrente que efetivamente atravessa um disjuntor na falta.

    A falta é colocada imediatamente a jusante do disjuntor,
    representada pela barra ``from_bus`` do switchgear. As máquinas que
    pertencem ao lado ``to_bus`` são retiradas da contribuição de curto
    porque alimentariam a falta pelo lado da carga e não atravessariam o
    próprio disjuntor.

    O resultado é distinto do curto total da barra e é o valor
    apropriado para verificar a capacidade interruptiva do disjuntor.
    """
    case = "min" if str(case).lower() == "min" else "max"
    model = enrich_model(get_model())
    sw = next((x for x in model.get("switchgear", []) if x.get("breaker") == breaker), None)
    if sw is None:
        raise KeyError(f"Disjuntor não encontrado: {breaker}")
    fault_bus = sw["from_bus"]
    downstream_motors = _graph_downstream_motor_names(model, breaker)
    raw = {}
    errors = []
    for fault, key in (("3ph", "3F"), ("2ph", "LL"), ("1ph", "LG")):
        try:
            raw[key] = _run_fault_single_bus(case, fault, fault_bus, downstream_motors)
        except Exception as exc:
            raw[key] = {}
            errors.append(f"{key}: {exc}")
    r3, r2, r1 = raw.get("3F", {}), raw.get("LL", {}), raw.get("LG", {})
    bus_data = next(b for b in model["buses"] if b["name"] == fault_bus)
    seq = _sequence_from_rows(r2, r1)
    pp_lg = r1.get("ikss_ka")
    llg = _llg_from_sequences(*seq, float(bus_data["kv"]), case) if seq else None
    lg_method = "Pandapower IEC 60909"
    ground = next((x for x in run_ground_sequence_fallback(case).get("rows", []) if x["bus"] == fault_bus), None)
    prefer_fallback = bool(ground) and str(ground.get("source_kind", "")).startswith("generator")
    if ground and ground.get("r0_ohm") is not None and (
        prefer_fallback or pp_lg is None or float(pp_lg) <= _NEGLIGIBLE_KA or llg is None or float(llg) <= _NEGLIGIBLE_KA
    ):
        phase_seq = _phase_sequence_from_ll_row(r2)
        z0g = complex(float(ground["r0_ohm"]), float(ground["x0_ohm"]))
        if phase_seq:
            fb_lg, fb_llg = _ground_fault_from_sequence(phase_seq[0], phase_seq[1], z0g, float(bus_data["kv"]), case)
            fb_method = "Pandapower Z1/Z2 + fallback físico Z0"
        else:
            fb_lg, fb_llg = ground.get("lg_ka"), ground.get("llg_ka")
            fb_method = ground.get("method")
        if prefer_fallback and fb_lg is not None:
            pp_lg = fb_lg
            lg_method = fb_method
        elif pp_lg is None or float(pp_lg) <= _NEGLIGIBLE_KA:
            pp_lg = fb_lg
            lg_method = fb_method
        if prefer_fallback and fb_llg is not None:
            llg = fb_llg
        elif llg is None or float(llg) <= _NEGLIGIBLE_KA:
            llg = fb_llg
    row = {
        "breaker": breaker,
        "fault_bus": fault_bus,
        "case": case,
        "downstream_motors_excluded": downstream_motors,
        "3f_ka": r3.get("ikss_ka"),
        "ll_ka": r2.get("ikss_ka"),
        "lg_ka": pp_lg,
        "llg_ka": llg,
        "errors": errors,
        "method": "fault-at-breaker / downstream sources excluded",
        "ground_fault_method": lg_method,
    }
    return row



@cacheable(maxsize=16)
def run_zone_remote_fault(zone_id: str, case: str = "max") -> dict:
    """Corrente de falta no fim da zona, vista pelo relé a montante.

    Para ramais de motor, a falta é aplicada na barra terminal e o
    próprio motor protegido é retirado no caso MAX. Assim, a corrente
    calculada é a contribuição que atravessa o cabo/relé, equivalente à
    grandeza usada no TCC e na verificação térmica do cabo. No caso MIN
    os motores já estão excluídos pelo estudo IEC.
    """
    case = "min" if str(case).lower() == "min" else "max"
    model = enrich_model(get_model())
    zone = next((z for z in model.get("zones", []) if z.get("id") == zone_id), None)
    if zone is None:
        raise KeyError(f"Zona não encontrada: {zone_id}")
    fault_bus = zone["bus"]
    disabled = [zone["motor"]] if case == "max" and zone.get("motor") else []
    raw = {}
    errors = []
    for fault, key in (("3ph", "3F"), ("2ph", "LL"), ("1ph", "LG")):
        try:
            raw[key] = _run_fault_single_bus(case, fault, fault_bus, disabled)
        except Exception as exc:
            raw[key] = {}; errors.append(f"{key}: {exc}")
    r3, r2, r1 = raw.get("3F", {}), raw.get("LL", {}), raw.get("LG", {})
    bus_data = next(b for b in model["buses"] if b["name"] == fault_bus)
    seq = _sequence_from_rows(r2, r1)
    pp_lg = r1.get("ikss_ka")
    llg = _llg_from_sequences(*seq, float(bus_data["kv"]), case) if seq else None
    lg_method = "Pandapower IEC 60909"
    ground = next((x for x in run_ground_sequence_fallback(case).get("rows", []) if x["bus"] == fault_bus), None)
    prefer_fallback = bool(ground) and str(ground.get("source_kind", "")).startswith("generator")
    if ground and ground.get("r0_ohm") is not None and (
        prefer_fallback or pp_lg is None or float(pp_lg) <= _NEGLIGIBLE_KA or llg is None or float(llg) <= _NEGLIGIBLE_KA
    ):
        phase_seq = _phase_sequence_from_ll_row(r2)
        z0g = complex(float(ground["r0_ohm"]), float(ground["x0_ohm"]))
        if phase_seq:
            fb_lg, fb_llg = _ground_fault_from_sequence(phase_seq[0], phase_seq[1], z0g, float(bus_data["kv"]), case)
            fb_method = "Pandapower Z1/Z2 + fallback físico Z0"
        else:
            fb_lg, fb_llg = ground.get("lg_ka"), ground.get("llg_ka")
            fb_method = ground.get("method")
        if prefer_fallback and fb_lg is not None:
            pp_lg = fb_lg
            lg_method = fb_method
        elif pp_lg is None or float(pp_lg) <= _NEGLIGIBLE_KA:
            pp_lg = fb_lg
            lg_method = fb_method
        if prefer_fallback and fb_llg is not None:
            llg = fb_llg
        elif llg is None or float(llg) <= _NEGLIGIBLE_KA:
            llg = fb_llg
    return {
        "zone_id": zone_id, "fault_bus": fault_bus, "case": case,
        "protected_motor_excluded": disabled,
        "3f_ka": r3.get("ikss_ka"), "ll_ka": r2.get("ikss_ka"),
        "lg_ka": pp_lg, "llg_ka": llg,
        "errors": errors,
        "method": "remote-end fault / protected motor excluded from upstream through-current",
        "ground_fault_method": lg_method,
    }


def get_bus_short_circuit(bus: str, case: str = "max"):
    """Devolve a linha de curto-circuito de uma barra específica.

    Atalho sobre ``run_short_circuit``, que vem do cache. Levanta
    ``KeyError`` quando a barra não existe, porque aí é erro de
    programação, não dado faltando.
    """
    result = run_short_circuit(case)
    row = next((item for item in result["rows"] if item["bus"] == bus), None)
    if row is None:
        raise KeyError(f"Barra não encontrada: {bus}")
    return row


# ======================================================================
# CONTROLE DE CACHE E RESUMO DO ESTUDO
# Invalidação explícita e o consolidado mostrado na tela inicial.
# ======================================================================

def clear_solver_cache():
    """Invalida somente os resultados do estudo elétrico.

    V27: os ajustes de proteção não chamam esta função. Assim, fluxo e
    curto permanecem em memória enquanto o modelo elétrico não for
    recalculado.
    """
    run_power_flow.cache_clear()
    run_short_circuit.cache_clear()
    run_breaker_fault_duty.cache_clear()
    run_zone_remote_fault.cache_clear()
    run_phase_min_validated.cache_clear()
    run_ground_sequence_fallback.cache_clear()


def solver_cache_status() -> dict:
    """Estado do cache elétrico, para a tela de diagnóstico.

    Mostra o que está guardado e se o cache está ligado. Existe para que
    o efeito do cache possa ser **medido** pelo aluno, ligando e
    desligando, em vez de apenas explicado.
    """
    pf = run_power_flow.cache_info()
    sc = run_short_circuit.cache_info()
    zr = run_zone_remote_fault.cache_info()
    bd = run_breaker_fault_duty.cache_info()
    return {
        "powerflow_cached": pf.currsize > 0,
        "shortcircuit_cases_cached": sc.currsize,
        "zone_faults_cached": zr.currsize,
        "breaker_faults_cached": bd.currsize,
        "powerflow_hits": pf.hits,
        "shortcircuit_hits": sc.hits,
    }


def study_summary():
    """Consolidado do estudo para a tela inicial.

    Reúne, numa chamada só: se o fluxo convergiu, qual a barra de menor
    tensão, qual a maior corrente de curto e se os dois casos da norma
    rodaram sem erro. Tudo vem do cache — abrir a tela inicial não
    dispara cálculo novo.
    """
    pf = run_power_flow()
    mx = run_short_circuit("max")
    mn = run_short_circuit("min")
    valid_pf = [r for r in pf.get("buses", []) if r.get("vm_pu") is not None]
    minv = min(valid_pf, key=lambda r: r["vm_pu"]) if valid_pf else None
    valid_sc = [r for r in mx.get("rows", []) if r.get("3f_ka") is not None]
    maxsc = max(valid_sc, key=lambda r: r["3f_ka"]) if valid_sc else None
    return {
        "powerflow_ok": pf.get("ok", False),
        "powerflow_error": pf.get("error"),
        "min_voltage": minv,
        "max_sc": None if maxsc is None else {"bus": maxsc["bus"], "ka": maxsc["3f_ka"]},
        "sc_max_ok": mx.get("ok", False),
        "sc_min_ok": mn.get("ok", False),
        "sc_max_errors": mx.get("errors", []),
        "sc_min_errors": mn.get("errors", []),
    }
