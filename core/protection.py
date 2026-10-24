"""Camada de proteção: curvas, ajustes, coordenogramas e especialista.

Posição no pipeline do estudo:

    data.py  ->  storage.py  ->  network.py  ->  solver.py  ->
    **protection.py**  ->  app.py

É o módulo maior do projeto, e por um motivo: aqui mora todo o critério
de engenharia. O solver entrega corrente; este módulo decide se essa
corrente, com um dado ajuste, resulta numa proteção aceitável.

Está organizado em seis blocos, nesta ordem no arquivo:

1. **Biblioteca e curvas** — famílias IEC/IEEE (``CURVES``), modelos
   de relé com faixas reais de pickup e TMS (``RELAY_LIBRARY``) e o
   tempo de atuação (``relay_time``, ``relay_operating_time``).
2. **Ajustes de zona** — leitura, validação e gravação
   (``settings_for_zone``, ``update_settings``,
   ``provisional_settings``).
3. **Coordenogramas (TCC)** — montagem dos traços de relé e das
   curvas físicas de motor, cabo e transformador (``build_tcc``,
   ``build_path_tcc``, ``build_master_tcc``, ``build_concise_tcc``).
4. **Sistema especialista** — sugestão de ajustes por regras
   clássicas (``suggest_phase_settings``).
5. **Folha ETAP STAR** — reprodução da apresentação do relatório
   original.
6. **Verificação em cascata** — percorre um caminho de coordenação par
   por par (``review_coordination``). Aqui o especialista *verifica*;
   não ajusta.

Princípios que valem explicar em aula
-------------------------------------
* **Curva de dano não é objeto de ajuste.** Partida de motor, inrush
  de transformador e curva de dano são referência física fixa; o que
  se ajusta é a curva do relé, que tem de passar entre elas.
* **Dado ausente não vira reprovação.** As verificações devolvem três
  estados: aprovado, reprovado e *pendente*. "Não sei" é uma resposta
  legítima de um estudo de engenharia, e inventar valor para fechar o
  relatório seria pior que admitir a lacuna.
* **Limite de 20 × Is.** Acima desse múltiplo a característica
  inversa não é mais definida pela IEC 60255-151: o tempo congela em
  t(M = 20), como o ETAP desenha (``CURVE_MULTIPLE_LIMIT``).
* **Cada número vem acompanhado de como foi obtido.** As regras do
  especialista registram id, texto e valores de entrada, para o
  engenheiro auditar e, se quiser, discordar.
"""
from __future__ import annotations

import math
import threading
from contextlib import contextmanager
from typing import Iterable

from .data import enrich_model
from .criteria import select_critical_phase_min, select_max_fault_duty, select_max_phase_fault
from .solver import get_bus_short_circuit, run_breaker_fault_duty, run_zone_remote_fault, run_power_flow, run_short_circuit, solver_cache_status
from .storage import delete_settings, get_model, get_settings, save_settings

# Seis curvas oficiais adotadas no TCC. Para IEC: t=TMS*K/(M^a-1). Para
# IEEE: t=TD*(K/(M^a-1)+L).
# ======================================================================
# BLOCO 1 — BIBLIOTECA DE CURVAS E RELÉS
# Famílias IEC/IEEE, modelos de relé com as faixas reais de pickup e
# TMS, e as listas de valores comerciais usadas no arredondamento.
# ======================================================================

CURVES = {
    "IEC_SI": {"label": "IEC Standard Inverse", "family": "IEC", "k": 0.14, "alpha": 0.02, "L": 0.0},
    "IEC_VI": {"label": "IEC Very Inverse", "family": "IEC", "k": 13.5, "alpha": 1.0, "L": 0.0},
    "IEC_EI": {"label": "IEC Extremely Inverse", "family": "IEC", "k": 80.0, "alpha": 2.0, "L": 0.0},
    "IEEE_MI": {"label": "IEEE Moderately Inverse", "family": "IEEE", "k": 0.0515, "alpha": 0.02, "L": 0.114},
    "IEEE_VI": {"label": "IEEE Very Inverse", "family": "IEEE", "k": 19.61, "alpha": 2.0, "L": 0.491},
    "IEEE_EI": {"label": "IEEE Extremely Inverse", "family": "IEEE", "k": 28.2, "alpha": 2.0, "L": 0.1217},
}
# Compatibilidade com os testes das versões anteriores.
IEC_CURVES = {k: v for k, v in CURVES.items() if v["family"] == "IEC"}

RELAY_LIBRARY = {
    "SEPAM_M40": {
        "label": "Schneider Sepam Series 40 M40",
        "application": "Motor",
        "phase_units": 4,
        "earth_units": 4,
        "curves": list(CURVES),
        "stage1_pickup_pu": (0.10, 2.40),       # IDMT, referido a In/TC
        "stage2_pickup_pu": (0.10, 24.00),      # definite time
        "stage3_pickup_pu": (0.10, 24.00),      # instantaneous/DT
        "stage2_delay_s": (0.05, 300.0),
        "stage3_delay_s": (0.0, 300.0),
        "time_setting_ranges": {
            "IEC_SI": (0.04, 4.20),
            "IEC_VI": (0.07, 8.33),
            "IEC_EI": (0.13, 15.47),
            "IEEE_MI": (0.42, 51.86),
            "IEEE_VI": (0.73, 90.57),
            "IEEE_EI": (1.24, 154.32),
        },
        "instantaneous_trip_time_max_s": 0.050,
        "instantaneous_trip_time_typical_s": 0.035,
        "instantaneous_trip_time_source": "Schneider Electric Sepam Series 20/40: saída instantânea confirmada 50/51 < 50 ms; típico 35 ms a 2 Is para Is >= 0,3 In.",
        "notes": "M40 possui quatro unidades 50/51 e quatro 50N/51N; o estudo usa três estágios por função.",
    },
    "MICOM_P241": {
        "label": "Schneider Electric MiCOM P241",
        "application": "Motor / alimentador / transformador (modelo ETAP atual)",
        "phase_units": 4,
        "earth_units": 2,
        "curves": list(CURVES),
        "stage1_pickup_pu": (0.20, 15.00),
        "stage2_pickup_pu": (0.20, 15.00),
        "stage3_pickup_pu": (0.20, 15.00),
        "stage2_delay_s": (0.0, 100.0),
        "stage3_delay_s": (0.0, 100.0),
        "time_setting_ranges": {
            "IEC_SI": (0.025, 1.20),
            "IEC_VI": (0.025, 1.20),
            "IEC_EI": (0.025, 1.20),
            "IEEE_MI": (0.01, 100.0),
            "IEEE_VI": (0.01, 100.0),
            "IEEE_EI": (0.01, 100.0),
        },
        # Manual técnico oficial (Schneider/GE MiCOM P24x, P24x/EN
        # TD/C52, pág. 41), seção "4-Stage non-directional short-circuit
        # protection" — é exatamente a função 50/51 usada nas 5 zonas
        # deste estudo. "DT operation: ±2% or 50 ms whichever is
        # greater": com ajuste DT=0s (instantâneo), o piso físico real
        # de operação é 50 ms, não zero.
        "instantaneous_trip_time_max_s": 0.050,
        "instantaneous_trip_time_typical_s": None,
        "instantaneous_trip_time_source": "Schneider/GE MiCOM P24x Technical Data (P24x/EN TD/C52, pág. 41): "
            "'4-Stage non-directional short-circuit protection · DT operation: ±2% or 50 ms whichever is greater'.",
        "notes": "P241: I>1/I>2 podem ser IDMT ou DT; I>3/I>4 são DT. Faixa OC1 usada no ETAP: 0,2…15 × CT secundário.",
    },
}

PICKUP_STANDARDS = [25, 40, 50, 63, 80, 100, 125, 160, 200, 250, 300, 320, 400, 500, 600, 800, 1000, 1200, 1600, 2000, 2500, 3000, 4000, 5000]
CT_STANDARDS = [50, 100, 150, 200, 300, 400, 500, 600, 800, 1000, 1200, 1600, 2000, 2500, 3000, 4000, 5000]
INST_STANDARDS = [250, 400, 500, 630, 800, 1000, 1200, 1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000, 8000, 10000, 12000, 15000, 20000, 25000, 30000, 40000, 50000]
BREAKER_STANDARDS = [16, 20, 25, 31.5, 40, 50, 63, 80, 100]


# ======================================================================
# CONTEXTO E CONVERSÕES
# _ctx() monta os dicionários por nome usados por quase todo o módulo.
# As demais convertem corrente entre níveis de tensão e leem a FLA do
# equipamento protegido por cada zona.
# ======================================================================

def _ctx():
    model = enrich_model(get_model())
    return (
        model,
        {z["id"]: z for z in model["zones"]},
        {m["name"]: m for m in model["motors"]},
        {c["name"]: c for c in model["cables"]},
        {t["name"]: t for t in model["transformers"]},
        {g["name"]: g for g in model["generators"]},
        {b["name"]: b for b in model["buses"]},
        {p["id"]: p for p in model.get("coordination_paths", [])},
    )


def _next_standard(value, standards):
    value = float(value)
    for standard in standards:
        if float(standard) >= value:
            return float(standard)
    return float(standards[-1])


def _num(value):
    if value in (None, ""):
        return None
    return float(value)


def _shift_current(current_a: float, native_kv: float, reference_kv: float) -> float:
    """Refere uma corrente trifásica a outra tensão, mantendo √3VI."""
    return float(current_a) * float(native_kv) / float(reference_kv)


def _protected_fla(zone, motors, trafos, generators):
    if zone.get("motor") and zone["motor"] in motors:
        return float(motors[zone["motor"]]["amp"])
    if zone.get("transformer") and zone["transformer"] in trafos:
        t = trafos[zone["transformer"]]
        return float(t["fla_lv_a"] if float(zone.get("kv", t["vn_hv_kv"])) == float(t["vn_lv_kv"]) else t["fla_hv_a"])
    if zone.get("generator") and zone["generator"] in generators:
        return float(generators[zone["generator"]]["fla_a"])
    return 100.0


def _sc_value(zone, case="min", fault="3f"):
    """Corrente de falta na barra da zona, no nível do relé."""
    model, _, _, _, _, _, buses, _ = _ctx()
    try:
        row = get_bus_short_circuit(zone["bus"], case)
        value = row.get(f"{fault}_ka")
        if value is None:
            return None
        bus_kv = float(buses[zone["bus"]]["kv"])
        native_kv = float(zone["kv"])
        return float(value) * 1000.0 * bus_kv / native_kv
    except Exception:
        return None


# ======================================================================
# DEVER DE INTERRUPÇÃO DO DISJUNTOR
# Usa a falta imediatamente a jusante do dispositivo, removendo as
# fontes do lado da carga: elas alimentam a falta, mas nao atravessam o
# proprio disjuntor no instante da interrupcao.
# ======================================================================

def breaker_duty_for_zone(zone_id: str, settings: dict | None = None) -> dict:
    """Dever de interrupção e rating físico são grandezas separadas.

    Para zonas com disjuntor físico, a falta MAX é colocada no ponto do
    disjuntor e as fontes/motores que ficam a jusante dele são excluídos
    da contribuição que atravessa o próprio dispositivo. A classe
    recomendada usa a margem de projeto de 10%, mas o campo
    ``breaker_interrupt_ka`` é exclusivamente a corrente nominal de
    interrupção informada pelo usuário/fabricante.
    """
    _, zones, _, _, _, _, _, _ = _ctx()
    if zone_id not in zones:
        raise KeyError(zone_id)
    zone = zones[zone_id]
    breaker = zone.get("breaker")
    settings = settings or settings_for_zone(zone_id)
    rating = settings.get("breaker_interrupt_ka")
    if not breaker:
        return {
            "available": False, "breaker": None, "status": "not_applicable",
            "rating_ka": rating, "reason": "Zona lógica sem disjuntor físico identificado.",
        }
    try:
        row = run_breaker_fault_duty(breaker, "max")
        maximum = select_max_fault_duty(row)
    except Exception as exc:
        return {
            "available": False, "breaker": breaker, "status": "pending",
            "rating_ka": rating, "reason": f"Dever de interrupção indisponível: {exc}",
        }
    if not maximum.get("available"):
        return {
            "available": False, "breaker": breaker, "status": "pending",
            "rating_ka": rating, "fault_bus": row.get("fault_bus"),
            "downstream_motors_excluded": row.get("downstream_motors_excluded", []),
            "reason": "Nenhuma corrente MAX disponível para o ponto do disjuntor.",
        }
    duty = float(maximum["ka"])
    required = duty * 1.10
    recommended = _next_standard(required, BREAKER_STANDARDS)
    model = enrich_model(get_model())
    sw = next((x for x in model.get("switchgear", []) if x.get("breaker") == breaker), None)
    ref = (sw or {}).get("duty_reference")
    validation = None
    if ref and ref.get("max_ka") not in (None, "", 0):
        ref_ka = float(ref["max_ka"])
        delta_pct = 100.0 * (duty - ref_ka) / ref_ka
        validation = {
            "available": True, "reference_ka": ref_ka, "reference_fault": ref.get("fault"),
            "delta_percent": delta_pct, "source": ref.get("source"),
        }
    if rating in (None, "", 0):
        status = "pending"
        reason = "Corrente nominal de interrupção não informada."
    else:
        status = "approved" if float(rating) >= required else "rejected"
        reason = (
            f"Rating informado {float(rating):.2f} kA {'atende' if status == 'approved' else 'não atende'} "
            f"ao critério de projeto {required:.2f} kA (Icc MAX × 1,10)."
        )
    return {
        "available": True, "breaker": breaker, "status": status,
        "fault_bus": row.get("fault_bus"),
        "downstream_motors_excluded": row.get("downstream_motors_excluded", []),
        "faults": {k: row.get(k) for k in ("3f_ka", "ll_ka", "lg_ka", "llg_ka")},
        "governing_fault": maximum["fault"], "duty_ka": duty,
        "design_required_ka": required, "recommended_class_ka": recommended,
        "rating_ka": None if rating in (None, "", 0) else float(rating),
        "reason": reason, "method": row.get("method"), "validation": validation,
    }


# ======================================================================
# BLOCO 2 — AJUSTES DE ZONA
# Leitura, validação e gravação dos ajustes 50/51. O ajuste provisório
# é calculado por regra quando a zona ainda não foi parametrizada.
# ======================================================================

def _default_time_setting(relay_model: str, curve: str):
    lo, hi = RELAY_LIBRARY[relay_model]["time_setting_ranges"][curve]
    target = 0.20 if CURVES[curve]["family"] == "IEC" else 1.0
    return min(max(target, lo), hi)


def _cable_adiabatic_defaults(cable: dict | None) -> dict:
    """Hipótese térmica padrão, só quando o material é conhecido.

    Para condutor de cobre com isolação XLPE, o estudo usa k=143
    A√s/mm², θi=90 °C e θf=250 °C. É uma hipótese conservadora de
    temperatura inicial máxima de serviço e pode ser sobrescrita pelo
    engenheiro.
    """
    if not cable:
        return {"k": None, "theta_i": None, "theta_f": None, "source": None}
    conductor = str(cable.get("conductor") or "").strip().lower()
    insulation = str(cable.get("insulation") or "").strip().lower()
    if conductor == "copper" and insulation == "xlpe":
        return {
            "k": 143.0, "theta_i": 90.0, "theta_f": 250.0,
            "source": "IEC/adiabático Cu-XLPE: k=143 A√s/mm² para 90→250 °C",
        }
    return {"k": None, "theta_i": None, "theta_f": None, "source": None}


def provisional_settings(zone_id: str) -> dict:
    """Ajustes-base da V21: transcrição dos OC1 atuais do ETAP.

    O botão Restaurar ETAP volta exatamente para esses valores. A
    aplicação não recalcula automaticamente o ajuste quando o usuário
    muda um campo; fluxo e curto-circuito são a etapa anterior e
    fornecem as correntes usadas nas verificações e no coordenograma.
    """
    model, zones, _, cables, _, _, _, _ = _ctx()
    zone = zones[zone_id]
    relay_model = zone.get("relay_model", "MICOM_P241")
    src = zone.get("etap_settings") or {}
    cable = cables.get(zone.get("cable"))
    cable_ad = _cable_adiabatic_defaults(cable)
    ct = next((c for c in model.get("cts", []) if c["name"] == zone.get("ct")), None)
    return {
        "relay_model": relay_model,
        "phase_enabled": True,
        "phase_curve": src.get("curve", "IEC_EI"),
        "phase_stage1_pickup_a": _num(src.get("pickup_51_a")),
        "phase_time_setting": _num(src.get("time_setting")),
        # OC1 atual possui uma etapa temporizada 51 e uma high-set 50.
        "phase_stage2_pickup_a": None,
        "phase_stage2_delay_s": None,
        "phase_stage3_pickup_a": _num(src.get("pickup_50_a")),
        "phase_stage3_delay_s": _num(src.get("delay_50_s")) if src.get("delay_50_s") is not None else 0.0,
        "phase_stage3_operating_time_s": None,
        "neutral_enabled": False,
        "neutral_curve": "IEC_EI",
        "neutral_stage1_pickup_a": None,
        "neutral_time_setting": 0.1,
        "neutral_stage2_pickup_a": None,
        "neutral_stage2_delay_s": None,
        "neutral_stage3_pickup_a": None,
        "neutral_stage3_delay_s": None,
        "neutral_stage3_operating_time_s": None,
        "ct_primary_a": _num(ct["primary_a"]) if ct else _num(src.get("ct_primary_a")),
        "ct_secondary_a": _num(ct["secondary_a"]) if ct else _num(src.get("ct_secondary_a")),
        "breaker_interrupt_ka": None,
        "breaker_opening_time_s": None,
        "coordination_margin_s": 0.30,
        "cable_k_adiabatic": cable_ad["k"],
        "cable_theta_initial_c": cable_ad["theta_i"],
        "cable_theta_final_c": cable_ad["theta_f"],
        "cable_ampacity_a": None if not cable else cable.get("ampacity_total_a"),
        "estimated": False,
        "notes": "Ajustes OC1 transcritos do ETAP em 30/08/2026; editáveis pelo usuário.",
    }


def _migrate_old(saved: dict, defaults: dict) -> dict:
    """Aceita banco de V8 se o usuário copiar o DB manualmente."""
    if not saved:
        return defaults
    migrated = dict(saved)
    aliases = {
        "curve": "phase_curve",
        "pickup_51_a": "phase_stage1_pickup_a",
        "tms": "phase_time_setting",
        "pickup_50_a": "phase_stage2_pickup_a",
        "delay_50_s": "phase_stage2_delay_s",
    }
    for old, new in aliases.items():
        if old in saved and new not in saved:
            migrated[new] = saved[old]
    return migrated


def settings_for_zone(zone_id: str) -> dict:
    """Objetivo: devolver os ajustes que valem agora para uma zona.

    É a única porta de leitura de ajuste no programa. Resolve, nesta
    ordem, quatro fontes que podem discordar entre si:

        provisório calculado  ->  salvo no banco  ->  TC da zona
        ->  prévia da tela

    ``provisional_settings``
        O ajuste preliminar que o programa calcula sozinho. Na primeira
        leitura de uma zona ele é **gravado**, para que o estudo tenha
        sempre um ponto de partida registrado em vez de um valor
        implícito.
    ``get_settings``
        O que o usuário salvou. Campo vazio não sobrepõe: vazio é "não
        informado", não é zero.
    TC da zona
        O TC passou a ser equipamento próprio, com ficha em "Modelo
        físico". Então a relação do TC vem dele e vence qualquer valor
        antigo salvo aqui — senão editar o TC não mudaria o ajuste.
    Prévia
        Entra **depois** do ``save_settings``, de propósito: o ajuste
        que o usuário está digitando no coordenograma nunca encosta no
        banco, e basta sair do bloco ``preview_zone_settings`` para o
        desenho voltar ao valor gravado.

    ``relay_model`` é determinado pela zona física e não é editável: o
    relé é o que está instalado no painel, não uma escolha de tela.
    """
    model, zones, _, _, _, _, _, _ = _ctx()
    if zone_id not in zones:
        raise KeyError(zone_id)
    defaults = provisional_settings(zone_id)
    saved = get_settings(zone_id)
    if saved is None:
        save_settings(zone_id, defaults)
        return defaults
    saved = _migrate_old(saved, defaults)
    merged = dict(defaults)
    for key, value in saved.items():
        if key in merged and value != "":
            merged[key] = value
    for key in ("phase_curve", "neutral_curve"):
        if merged.get(key) not in CURVES:
            merged[key] = "IEC_VI"
    # Modelo é determinado pela zona física e não pode ser trocado por
    # edição livre.
    merged["relay_model"] = zones[zone_id].get("relay_model", merged.get("relay_model", "MICOM_P241"))
    # TC agora é equipamento próprio (ver
    # _CTS/EQUIPMENT_FIELD_SCHEMA["cts"]) — se a zona tem um TC
    # vinculado, ele manda, mesmo que sobre um valor antigo salvo de
    # antes dessa mudança (edição direta na tela de ajustes deixou de
    # existir).
    ct = next((c for c in model.get("cts", []) if c["name"] == zones[zone_id].get("ct")), None)
    if ct:
        merged["ct_primary_a"] = _num(ct["primary_a"])
        merged["ct_secondary_a"] = _num(ct["secondary_a"])
    save_settings(zone_id, merged)
    # Prévia: ajuste que o usuário está digitando no coordenograma e
    # ainda não mandou salvar. Entra DEPOIS do save_settings de
    # propósito — assim a prévia nunca encosta no banco, e basta sair do
    # bloco para o desenho voltar ao ajuste gravado.
    patch = _preview_overrides().get(zone_id)
    if patch:
        return apply_settings_patch(merged, patch)
    return merged


# Ajustes de prévia por thread: o servidor roda com threaded=True e duas
# abas podem estar previsualizando zonas diferentes ao mesmo tempo.
_preview_local = threading.local()


def _preview_overrides() -> dict:
    return getattr(_preview_local, "overrides", None) or {}


@contextmanager
def preview_zone_settings(overrides: dict | None):
    """Objetivo: montar TCC ou análise com ajustes ainda não gravados.

        tela digita  ->  preview_zone_settings  ->  build_concise_tcc
        ->  desenho; saindo do bloco, tudo volta ao ajuste salvo

    Gerenciador de contexto. Nada é escrito no banco: o patch vive numa
    variável *thread-local* e desaparece no ``finally``.

    Por thread porque o servidor roda com ``threaded=True`` — duas abas
    podem estar pré-visualizando zonas diferentes ao mesmo tempo, e uma
    não pode ver o rascunho da outra.
    """
    anterior = getattr(_preview_local, "overrides", None)
    _preview_local.overrides = overrides or {}
    try:
        yield
    finally:
        _preview_local.overrides = anterior


def reset_settings(zone_id: str) -> dict:
    """Objetivo: descartar o ajuste salvo e voltar ao preliminar.

    Apaga a linha do banco e grava de novo o provisório calculado. O
    ajuste volta a ser o que o programa propõe, não um ajuste "zerado" —
    a zona nunca fica sem parametrização.
    """
    _, zones, _, _, _, _, _, _ = _ctx()
    if zone_id not in zones:
        raise KeyError(zone_id)
    delete_settings(zone_id)
    settings = provisional_settings(zone_id)
    save_settings(zone_id, settings)
    return settings


def update_settings(zone_id: str, patch: dict) -> dict:
    """Objetivo: aplicar o que o usuário mudou e gravar.

        patch da tela  ->  apply_settings_patch  ->  save_settings

    A lista branca de campos é a mesma usada na prévia, então o que o
    coordenograma mostrou é exatamente o que fica gravado.
    """
    current = apply_settings_patch(settings_for_zone(zone_id), patch)
    save_settings(zone_id, current)
    return current


def apply_settings_patch(current: dict, patch: dict) -> dict:
    """Aplica um patch de ajustes sobre uma cópia, sem gravar.

    Mesma lista branca usada ao salvar, para que a prévia do
    coordenograma e o ajuste definitivo nunca divirjam: o que o desenho
    mostra é exatamente o que o botão salvar vai gravar.
    """
    current = dict(current or {})
    patch = patch or {}
    numeric = {
        "phase_stage1_pickup_a", "phase_time_setting", "phase_stage2_pickup_a", "phase_stage2_delay_s",
        "phase_stage3_pickup_a", "phase_stage3_delay_s", "phase_stage3_operating_time_s",
        "neutral_stage1_pickup_a", "neutral_time_setting", "neutral_stage2_pickup_a", "neutral_stage2_delay_s",
        "neutral_stage3_pickup_a", "neutral_stage3_delay_s", "neutral_stage3_operating_time_s",
        "breaker_interrupt_ka", "breaker_opening_time_s", "coordination_margin_s",
        "cable_k_adiabatic", "cable_theta_initial_c", "cable_theta_final_c", "cable_ampacity_a",
    }
    text = {"phase_curve", "neutral_curve", "notes"}
    flags = {"phase_enabled", "neutral_enabled", "estimated"}
    touched = False
    for key, value in patch.items():
        if key in numeric:
            current[key] = _num(value)
            touched = True
        elif key in text:
            current[key] = str(value or "")
            touched = True
        elif key in flags:
            current[key] = bool(value)
            touched = True
    for key in ("phase_curve", "neutral_curve"):
        if current.get(key) not in CURVES:
            current[key] = "IEC_VI"
    if touched and "estimated" not in patch:
        current["estimated"] = False
    return current


# Limite do múltiplo I/Is em que a característica inversa deixa de
# valer. A IEC 60255-151 e a IEEE C37.112 definem a curva até 20 x Is;
# acima disso o comportamento é do fabricante, e tanto o ETAP quanto os
# relés usuais (MiCOM, Sepam) mantêm o tempo congelado no valor de 20 x
# Is até o estágio 50 assumir. Sem esse patamar a curva desenhada cai
# abaixo da real na faixa de curto: no caso M-B-0 o STAR75 mostra 0,0653
# s constante de 4600 A até o 50P em 7760 A, exatamente t(M=20) = 0,325
# x 80 / (20^2 - 1).
# ======================================================================
# TEMPO DE ATUAÇÃO DO RELÉ
# Característica inversa, estágios definidos e o traço que vai para o
# coordenograma. Acima de 20 × Is a curva congela (IEC 60255-151).
# ======================================================================

CURVE_MULTIPLE_LIMIT = 20.0


def relay_time(current_a, pickup_a, time_setting, curve, multiple_limit=CURVE_MULTIPLE_LIMIT):
    """Objetivo: tempo de atuação da curva inversa, em segundos.

        t(I) = TMS · [ k / (M^α − 1) + L ],  M = I / Is

    ``k``, ``α`` e ``L`` vêm de ``CURVES`` (IEC 60255-151 e
    IEEE C37.112). Devolve ``None``, e não zero, quando o relé
    simplesmente não atua: corrente abaixo do pickup, ou pickup/TMS não
    parametrizados. Zero significaria atuação instantânea — o oposto.

    Acima de ``multiple_limit`` (20 × Is) o múltiplo é
    **congelado**. Não é aproximação: é o que a norma permite e o que
    o relé real faz. Sem esse patamar a curva desenhada cairia abaixo
    da real justamente na faixa de curto, onde a coordenação é
    decidida.
    """
    if pickup_a in (None, 0) or time_setting in (None, 0) or current_a <= pickup_a:
        return None
    cfg = CURVES[curve]
    multiple = float(current_a) / float(pickup_a)
    if multiple_limit not in (None, "", 0):
        multiple = min(multiple, float(multiple_limit))
    denominator = multiple ** cfg["alpha"] - 1.0
    if denominator <= 0:
        return None
    return float(time_setting) * (cfg["k"] / denominator + cfg["L"])


def motor_time_setting_window(motor: dict, pickup_a: float, curve_key: str, margin_s: float = 0.30) -> dict:
    """Calcula a janela de multiplicador de tempo no ponto de LRC.

    Usa somente ILR, tempo de aceleração a 100 % Vt e Hot/Cold Stall.
    Não cria nem interpola uma curva térmica entre esses pontos.
    """
    start = motor.get("start_time_s")
    hot = motor.get("stall_hot_s")
    cold = motor.get("stall_cold_s")
    ilr = motor.get("locked_rotor_current_a")
    if start in (None, "") or ilr in (None, "") or not pickup_a or curve_key not in CURVES:
        return {"available": False}
    base = relay_time(float(ilr), float(pickup_a), 1.0, curve_key)
    if base in (None, 0) or not math.isfinite(float(base)):
        return {"available": False}
    min_ts = (float(start) + float(margin_s)) / float(base)
    max_hot = None if hot in (None, "") else float(hot) / float(base)
    max_cold = None if cold in (None, "") else float(cold) / float(base)
    return {
        "available": True,
        "ilr_a": float(ilr),
        "base_time_at_ts1_s": float(base),
        "start_time_s": float(start),
        "margin_s": float(margin_s),
        "min_time_setting_start": min_ts,
        "max_time_setting_hot": max_hot,
        "max_time_setting_cold": max_cold,
    }


def _prefix(mode: str) -> str:
    return "neutral" if mode == "neutral" else "phase"


def relay_operating_time(current_a: float, settings: dict, mode="phase"):
    """Tempo usado para desenhar a característica efetiva.

    O estágio 3 é tratado como high-set: acima do seu pickup ele governa
    a característica. Se o tempo físico instantâneo foi informado, ele é
    usado; caso contrário o delay programado zero permanece 0 e será
    apenas representado no piso logarítmico do gráfico. A coordenação
    temporal usa ``relay_operation_detail`` e nunca aprova esse zero
    como tempo físico.
    """
    p = _prefix(mode)
    if not settings.get(f"{p}_enabled", True if mode == "phase" else False):
        return None, None
    p3 = settings.get(f"{p}_stage3_pickup_a")
    d3 = settings.get(f"{p}_stage3_delay_s")
    if p3 and d3 is not None and current_a >= float(p3):
        if float(d3) > 0:
            return float(d3), "50-INST" if mode == "phase" else "50N-INST"
        top = settings.get(f"{p}_stage3_operating_time_s")
        if top not in (None, "", 0):
            return float(top), ("50-INST" if mode == "phase" else "50N-INST")
        lib = RELAY_LIBRARY.get(settings.get("relay_model"), {})
        catalog_max = lib.get("instantaneous_trip_time_max_s")
        # No TCC, quando existe limite máximo de fabricante, desenha-se
        # esse limite conservador em vez de um zero fictício. A
        # aprovação por par trata a desigualdade explicitamente.
        return (float(catalog_max) if catalog_max not in (None, "", 0) else 0.0), ("50-INST" if mode == "phase" else "50N-INST")

    options = []
    p1 = settings.get(f"{p}_stage1_pickup_a")
    ts = settings.get(f"{p}_time_setting")
    curve = settings.get(f"{p}_curve")
    if p1 and ts and curve in CURVES:
        t = relay_time(current_a, float(p1), float(ts), curve)
        if t is not None:
            options.append((t, "51" if mode == "phase" else "51N"))
    p2 = settings.get(f"{p}_stage2_pickup_a")
    d2 = settings.get(f"{p}_stage2_delay_s")
    if p2 and d2 is not None and current_a >= float(p2):
        options.append((float(d2), "50-TD" if mode == "phase" else "50N-TD"))
    return min(options, key=lambda x: x[0]) if options else (None, None)


def relay_operation_detail(current_a: float, settings: dict, mode="phase") -> dict:
    """Estágio governante e qualidade do tempo, para a coordenação.

    Delay programado igual a zero significa estágio instantâneo por
    ajuste, não tempo físico zero. Acima do pickup do estágio 3, ele é
    tratado como high-set governante. Sem tempo real de atuação
    informado por ETAP/datasheet, o Δt fica pendente.
    """
    p = _prefix(mode)
    if not settings.get(f"{p}_enabled", True if mode == "phase" else False):
        return {"acts": False, "stage": None, "time_s": None, "time_known": False, "reason": "Função desabilitada."}

    p3 = settings.get(f"{p}_stage3_pickup_a")
    d3 = settings.get(f"{p}_stage3_delay_s")
    if p3 and d3 is not None and current_a >= float(p3):
        stage = "50-INST" if mode == "phase" else "50N-INST"
        # catalog_max só existe quando caímos no limite de catálogo.
        # Precisa nascer aqui: os campos do retorno leem essa variável
        # nos três casos. (Sem isso, um 50 com delay programado > 0 —
        # como o do Relé1, 0,01 s — estourava UnboundLocalError assim
        # que a corrente passava do pickup. Com o GE2 em serviço o curto
        # na Barra3 passa dos 14,7 kA e chega lá.)
        catalog_max = None
        if float(d3) > 0:
            time_s, known, source = float(d3), True, "delay programado"
        else:
            top = settings.get(f"{p}_stage3_operating_time_s")
            if top not in (None, "", 0):
                time_s, known, source = float(top), True, "datasheet/ETAP informado"
            else:
                lib = RELAY_LIBRARY.get(settings.get("relay_model"), {})
                catalog_max = lib.get("instantaneous_trip_time_max_s")
                time_s, known = None, False
                source = "catálogo fabricante (limite máximo)" if catalog_max not in (None, "", 0) else "pending"
        opening = settings.get("breaker_opening_time_s")
        clearing = None if time_s is None or opening in (None, "", 0) else time_s + float(opening)
        return {
            "acts": True, "stage": stage, "time_s": time_s, "time_known": known,
            "time_source": source,
            "time_bound_max_s": None if catalog_max in (None, "", 0) else float(catalog_max),
            "breaker_opening_time_s": None if opening in (None, "", 0) else float(opening),
            "clearing_time_s": clearing,
            "reason": None if known else (
                f"Tempo exato não informado; fabricante fornece limite máximo de {float(catalog_max):.3f} s."
                if catalog_max not in (None, "", 0) else
                "Estágio instantâneo selecionado, mas tempo físico de operação não informado."
            ),
        }

    candidates = []
    p1 = settings.get(f"{p}_stage1_pickup_a")
    ts = settings.get(f"{p}_time_setting")
    curve = settings.get(f"{p}_curve")
    if p1 and ts and curve in CURVES:
        t = relay_time(current_a, float(p1), float(ts), curve)
        if t is not None:
            candidates.append({"stage": "51" if mode == "phase" else "51N", "time_s": float(t)})
    p2 = settings.get(f"{p}_stage2_pickup_a")
    d2 = settings.get(f"{p}_stage2_delay_s")
    if p2 and d2 is not None and current_a >= float(p2):
        candidates.append({"stage": "50-TD" if mode == "phase" else "50N-TD", "time_s": float(d2)})
    if not candidates:
        return {"acts": False, "stage": None, "time_s": None, "time_known": False, "reason": "Nenhum estágio sensibilizado."}
    chosen = min(candidates, key=lambda x: x["time_s"])
    opening = settings.get("breaker_opening_time_s")
    clearing = None if opening in (None, "", 0) else float(chosen["time_s"]) + float(opening)
    return {
        "acts": True, "stage": chosen["stage"], "time_s": chosen["time_s"], "time_known": True,
        "time_source": "curve/setting",
        "breaker_opening_time_s": None if opening in (None, "", 0) else float(opening),
        "clearing_time_s": clearing, "reason": None,
    }


def _instantaneous_drop_current(settings: dict, p: str) -> float | None:
    """Corrente em que o 50 sem retardo corta a curva desenhada.

    O Star desenha um estágio 50 com retardo zero como uma reta vertical
    no pickup, descendo até o piso da folha — não como um patamar
    horizontal no tempo de operação do relé seguindo até o fim da
    escala. Conferido na folha Star86 do ramal M-B-0: o Relé11 desce em
    7.760 A (o pickup 50P), à esquerda da seta de 3P em 10.326 A, e não
    sobra nenhum traço à direita.

    O tempo de catálogo (50 ms do MiCOM P241) continua valendo em
    `relay_operating_time`, ou seja, na aprovação de pares e no cálculo
    manual. Aqui trata-se só de como a curva é desenhada.
    """
    pickup = settings.get(f"{p}_stage3_pickup_a")
    delay = settings.get(f"{p}_stage3_delay_s")
    operating = settings.get(f"{p}_stage3_operating_time_s")
    if pickup in (None, "", 0) or delay is None:
        return None
    if float(delay) > 0 or operating not in (None, "", 0):
        return None  # tem tempo definido: segue patamar
    return float(pickup)


def relay_effective_trace(settings: dict, max_current: float, mode="phase", label="Relé") -> dict | None:
    """Característica efetiva: menor tempo entre 51, 50-TD e 50.

    Em vez de desenhar três funções infinitas sobrepostas, o TCC mostra
    a envoltória realmente vista pela proteção. Nos pickups dos estágios
    50 são inseridos pares de pontos com o mesmo x para representar a
    transição vertical entre tempos.
    """
    p = _prefix(mode)
    if not settings.get(f"{p}_enabled", True if mode == "phase" else False):
        return None
    p1 = settings.get(f"{p}_stage1_pickup_a")
    if not p1:
        return None
    low = max(float(p1) * 1.001, 1e-6)
    high = max(float(max_current), low * 1.2)
    # Estágio 50 sem retardo: a amostragem da parte inversa para logo
    # antes do pickup; o resto da curva é a reta vertical acrescentada
    # no fim.
    inst_x = _instantaneous_drop_current(settings, p)
    if inst_x is not None and low < inst_x < high:
        high = inst_x * (1.0 - 1e-9)
    else:
        inst_x = None
    thresholds = []
    for key in (f"{p}_stage2_pickup_a", f"{p}_stage3_pickup_a"):
        value = settings.get(key)
        if value not in (None, "", 0):
            v = float(value)
            if low < v < high:
                thresholds.append(v)
    thresholds = sorted(set(thresholds))

    # Amostragem logarítmica com pontos extras imediatamente
    # antes/depois dos pickups para que saltos de tempo apareçam como
    # segmentos verticais.
    base = [low * (high / low) ** (i / 319) for i in range(320)]
    probes = list(base)
    for th in thresholds:
        probes.extend([th * (1.0 - 1e-9), th, th * (1.0 + 1e-9)])
    probes = sorted(x for x in probes if low <= x <= high)

    xs, ys = [], []
    last_x = None
    for x in probes:
        t, _stage = relay_operating_time(x, settings, mode)
        if t is None:
            continue
        y = min(1000.0, max(0.01, float(t)))
        # Para o ponto exatamente no pickup, preserva o mesmo x se
        # houver mudança brusca em relação ao valor imediatamente
        # anterior.
        if last_x is not None and abs(x - last_x) / max(x, 1.0) < 2e-9 and ys and abs(y - ys[-1]) > 1e-12:
            xs.append(x); ys.append(y)
        elif not xs or x > xs[-1] or abs(y - ys[-1]) > 1e-12:
            xs.append(x); ys.append(y)
        last_x = x
    if not xs:
        return None
    # Como no Star: assim que a característica encosta no piso da folha
    # (0,01 s) a curva termina ali. Sem isso o traço seguia rente à base
    # até a corrente máxima de amostragem, desenhando uma linha que não
    # existe no ETAP.
    floor = 0.01 * (1.0 + 1e-9)
    for i, y in enumerate(ys):
        if y <= floor:
            xs, ys = xs[:i + 1], ys[:i + 1]
            break
    # Reta vertical do 50 sem retardo, no pickup, até o piso da folha.
    if inst_x is not None and xs and ys[-1] > floor and xs[-1] <= inst_x:
        xs.extend([inst_x, inst_x])
        ys.extend([ys[-1], 0.01])
    suffix = "P" if mode == "phase" else "N"
    return {
        "name": f"{label} — característica efetiva {('51P/50P' if mode == 'phase' else '51N/50N')}",
        "x": xs, "y": ys, "mode": "lines", "kind": "relay_effective",
        "stages": {
            "stage1": settings.get(f"{p}_stage1_pickup_a"),
            "stage2": settings.get(f"{p}_stage2_pickup_a"),
            "stage3": settings.get(f"{p}_stage3_pickup_a"),
        },
    }


def relay_stage_traces(settings: dict, max_current: float, mode="phase", label="Relé", components=False) -> list[dict]:
    """Característica efetiva; os componentes isolados são opcionais.

    ``components=True`` existe para diagnóstico didático. O
    coordenograma de coordenação usa por padrão apenas a envoltória
    efetiva para evitar que as linhas 50-TD/50-INST atravessem o gráfico
    inteiro.
    """
    effective = relay_effective_trace(settings, max_current, mode, label)
    traces = [effective] if effective else []
    if not components:
        return traces
    p = _prefix(mode)
    suffix = "P" if mode == "phase" else "N"
    p1 = settings.get(f"{p}_stage1_pickup_a")
    ts = settings.get(f"{p}_time_setting")
    curve = settings.get(f"{p}_curve")
    p2 = settings.get(f"{p}_stage2_pickup_a")
    p3 = settings.get(f"{p}_stage3_pickup_a")
    if p1 and ts and curve in CURVES:
        low = float(p1) * 1.015
        high = min(max_current, float(p2) if p2 else max_current)
        if high > low:
            xs, ys = [], []
            for i in range(180):
                x = low * (high / low) ** (i / 179)
                t = relay_time(x, float(p1), float(ts), curve)
                if t is not None and 0.01 <= t <= 1000:
                    xs.append(x); ys.append(t)
            if xs:
                traces.append({"name": f"{label} — 51{suffix} isolado", "x": xs, "y": ys, "mode": "lines", "kind": "relay_component", "visible": "legendonly"})
    if p2 is not None:
        end = float(p3) if p3 and float(p3) > float(p2) else max_current
        if end > float(p2):
            traces.append({"name": f"{label} — 50{suffix}-TD isolado", "x": [float(p2), end], "y": [max(.01, float(settings.get(f'{p}_stage2_delay_s') or 0)), max(.01, float(settings.get(f'{p}_stage2_delay_s') or 0))], "mode": "lines", "kind": "relay_component", "visible": "legendonly"})
    if p3 is not None:
        traces.append({"name": f"{label} — 50{suffix} instantâneo isolado", "x": [float(p3), max(max_current, float(p3) * 1.1)], "y": [max(.01, float(settings.get(f'{p}_stage3_delay_s') or 0)), max(.01, float(settings.get(f'{p}_stage3_delay_s') or 0))], "mode": "lines", "kind": "relay_component", "visible": "legendonly"})
    return traces

# ======================================================================
# CURVAS FÍSICAS DOS EQUIPAMENTOS
# Dano térmico de motor, transformador e gerador, e limite adiabático
# do cabo. São referência fixa: o ajuste do relé tem de passar entre
# elas, nunca o contrário.
# ======================================================================

def _motor_thermal_trace(motor):
    points = motor.get("thermal_points") or []
    good = []
    for point in points:
        try:
            mult, sec = float(point[0]), float(point[1])
            if mult > 0 and sec > 0:
                good.append((mult, sec))
        except Exception:
            pass
    if not good:
        return [], []
    good.sort(key=lambda p: p[0])
    return [float(motor["amp"]) * p[0] for p in good], [p[1] for p in good]


def _motor_capability_trace(motor: dict, condition="hot", *, y_min=0.01, y_max=1000.0):
    """Curva estimada de capacidade térmica Hot/Cold do motor.

    Quando o ETAP não fornece os pontos de ``Thermal Limit Curve >
    Points...``, ainda é útil visualizar uma envoltória coerente com os
    dados físicos já cadastrados: corrente nominal, corrente de rotor
    bloqueado (ILR/LRC) e o respectivo tempo de stall Hot/Cold.

    O modelo adotado preserva exatamente o ponto de stall e tende a
    infinito quando I tende a In, representando a margem térmica
    acima da corrente nominal::

        t(I) = t_stall * (ILR² - In²) / (I² - In²),  I > In

    Para I >> In a expressão tende a uma relação I²t, comportamento
    adequado para uma *aproximação de capacidade* no coordenograma. Esta
    curva NÃO é a curva exata do ETAP/fabricante; quando
    ``thermal_points`` estiver disponível, os pontos reais continuam
    tendo precedência.
    """
    if not motor or not motor.get("thermal_curve_enabled", True):
        return [], []
    try:
        rated = float(motor["amp"])
        ilr = float(motor["locked_rotor_current_a"])
        stall = float(motor["stall_hot_s"] if condition == "hot" else motor["stall_cold_s"])
    except (KeyError, TypeError, ValueError):
        return [], []
    if rated <= 0 or ilr <= rated or stall <= 0:
        return [], []

    # Faixa suficiente para mostrar a assíntota térmica e a região de
    # curto.
    current_min = rated * 1.001
    current_max = ilr * 12.0
    numerator = stall * (ilr * ilr - rated * rated)
    xs, ys = [], []
    for i in range(320):
        current = current_min * (current_max / current_min) ** (i / 319)
        denominator = current * current - rated * rated
        if denominator <= 0:
            continue
        time_s = numerator / denominator
        if y_min <= time_s <= y_max:
            xs.append(current)
            ys.append(time_s)
    # Garante que o ponto ETAP de stall faça parte da curva desenhada.
    if y_min <= stall <= y_max:
        pairs = list(zip(xs, ys)) + [(ilr, stall)]
        pairs.sort(key=lambda p: p[0])
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
    return xs, ys


def _motor_capability_traces(motor: dict):
    """Hot/Cold reais, quando exportados, ou estimados pelo stall."""
    # O campo legado thermal_points continua reservado para a curva
    # exata exportada do ETAP. Enquanto ele estiver vazio, usa-se a
    # aproximação.
    if motor.get("thermal_points"):
        tx, ty = _motor_thermal_trace(motor)
        if tx:
            return [{
                "name": f"{motor['name']} — limite térmico (fabricante)",
                "x": tx, "y": ty, "mode": "lines", "kind": "motor_thermal_exact",
                "thermal_source": "ETAP Points",
            }]

    traces = []
    for condition, label, kind, enabled_key in (
        ("hot", "Hot", "motor_thermal_hot", "stall_hot_enabled"),
        ("cold", "Cold", "motor_thermal_cold", "stall_cold_enabled"),
    ):
        # Se o ETAP deixou Hot/Cold desmarcado, o tempo digitado não é
        # usado como substituto da Thermal Curve. Sem Points exportados,
        # não se fabrica uma curva de capacidade.
        if not motor.get(enabled_key, False):
            continue
        x, y = _motor_capability_trace(motor, condition)
        if x:
            traces.append({
                "name": f"{motor['name']} — {label} · capacidade estimada",
                "x": x, "y": y, "mode": "lines", "kind": kind,
                "thermal_source": "stall-capacity approximation",
            })
    return traces



def _transformer_rated_current_a(trafo: dict, side="hv"):
    """Corrente nominal do transformador no lado selecionado."""
    side = "lv" if str(side).lower() == "lv" else "hv"
    kv = float(trafo["vn_lv_kv"] if side == "lv" else trafo["vn_hv_kv"])
    return float(trafo["sn_mva"]) * 1e6 / (math.sqrt(3.0) * kv * 1e3)


def _transformer_damage_trace(trafo: dict, *, y_min=0.01, y_max=1000.0):
    """Curva de capacidade/dano do transformador no lado AT.

    Se ``damage_points_pu`` estiver preenchido, usa os pontos reais do
    estudo (múltiplos da corrente nominal AT x tempo) — prioridade
    máxima.

    Caso contrário, monta a curva ANSI/IEEE C57.109 de verdade
    (categoria I a IV pelo kVA nominal), não uma estimativa genérica:
    - Térmica (falta infrequente, ≤10 na vida do trafo): independente da
      impedância, t = 1250 / (I/FLA)², válida acima de 5× a corrente
      nominal (abaixo disso o guia usa a Tabela 2 de capacidade térmica
      a curto prazo, que não é uma curva de dano e não é desenhada
      aqui).
    - Mecânica (falta frequente): depende da impedância do trafo, começa
      em 70 % (Categoria II) ou 50 % (Categoria III/IV) da MAIOR
      corrente de curto que o trafo realmente vê no sistema. Essa
      corrente máxima vem do próprio curto-circuito MAX já calculado
      pelo estudo (Bus HV/LV), não é copiada do ETAP — mesmo princípio
      já usado no resto do app.
    """
    if not trafo:
        return [], [], None
    rated = _transformer_rated_current_a(trafo, "hv")
    exact = trafo.get("damage_points_pu") or []
    points = []
    for pt in exact:
        try:
            mult, sec = float(pt[0]), float(pt[1])
            if mult > 0 and sec > 0:
                points.append((rated * mult, sec))
        except Exception:
            pass
    if points:
        points.sort(key=lambda z: z[0])
        return [x for x, _ in points], [y for _, y in points], "ETAP Points"

    try:
        sn_kva = float(trafo["sn_mva"]) * 1000.0
    except (KeyError, TypeError, ValueError):
        return [], [], None
    category = trafo.get("damage_category")
    if not category:
        category = "I" if sn_kva <= 500 else "II" if sn_kva <= 5000 else "III" if sn_kva <= 30000 else "IV"
    i2t_thermal = float(trafo.get("damage_i2t_thermal") or 1250.0)

    xs, ys = [], []

    # --- Curva térmica (falta infrequente): t = 1250 / (I/FLA)²
    # ------------- Válida de 5x a corrente nominal até o ponto onde
    # encontra a corrente máxima de curto (não faz sentido desenhar além
    # do que o sistema pode realmente entregar).
    i_min_thermal = 5.0 * rated
    max_fault_a = None
    try:
        hv_bus = trafo.get("hv_bus")
        if hv_bus:
            row = get_bus_short_circuit(hv_bus, "max")
            sel = select_max_phase_fault(row)
            if sel.get("available"):
                max_fault_a = float(sel["ka"]) * 1000.0
    except Exception:
        max_fault_a = None
    i_max_thermal = max_fault_a if max_fault_a and max_fault_a > i_min_thermal else i_min_thermal * 20.0
    for i in range(160):
        current = i_min_thermal * (i_max_thermal / i_min_thermal) ** (i / 159)
        mult = current / rated
        time_s = i2t_thermal / (mult * mult)
        if y_min <= time_s <= y_max:
            xs.append(current)
            ys.append(time_s)

    # --- Curva mecânica (falta frequente): depende da impedância
    # ----------- Categoria II começa em 70 % do Imax; III/IV em 50 %. K
    # é ancorado em t = 2 s no Imax real do sistema (não em 1/Zt com
    # fonte infinita).
    if category in ("II", "III", "IV") and max_fault_a:
        start_frac = 0.70 if category == "II" else 0.50
        i_start = start_frac * max_fault_a
        mult_max = max_fault_a / rated
        k_mech = 2.0 * mult_max * mult_max
        mxs, mys = [], []
        for i in range(120):
            current = i_start * (max_fault_a / i_start) ** (i / 119)
            mult = current / rated
            time_s = k_mech / (mult * mult)
            if y_min <= time_s <= y_max:
                mxs.append(current)
                mys.append(time_s)
        if mxs:
            xs = mxs + [None] + xs  # None quebra a linha no Plotly
            ys = mys + [None] + ys

    if not xs:
        return [], [], None
    return xs, ys, f"ANSI C57.109 Cat.{category}"


def _generator_damage_trace(gen: dict, *, y_min=0.01, y_max=1000.0):
    """Curva de dano do estator do gerador — só os pontos reais do ETAP.

    O I²t≤30 (ANSI/IEEE C50.13, capacidade térmica de curto trifásico no
    terminal) é uma verificação separada, não faz parte desta mesma
    linha: ele define um limite pontual (corrente real de curto × tempo
    real de eliminação), não uma curva contínua que se conecte
    suavemente aos 4 pontos de sobrecarga do ETAP — tentar uni-los numa
    linha só produziria uma curva sem sentido físico (os dois teriam
    origens diferentes na norma).
    """
    if not gen:
        return [], [], None
    try:
        fla = float(gen["fla_a"])
    except (KeyError, TypeError, ValueError):
        return [], [], None
    pts = gen.get("stator_damage_points") or []
    points = []
    for sec, mult in pts:
        try:
            sec, mult = float(sec), float(mult)
            if sec > 0 and mult > 0 and y_min <= sec <= y_max:
                points.append((fla * mult, sec))
        except Exception:
            pass
    if not points:
        return [], [], None
    points.sort(key=lambda z: z[0])
    return [x for x, _ in points], [y for _, y in points], "ETAP Stator Damage Curve"


def _transformer_damage_traces(trafo: dict):
    x, y, source = _transformer_damage_trace(trafo)
    if not x:
        return []
    exact = source == "ETAP Points"
    return [{
        "name": f"{trafo['name']} — damage {'(fabricante)' if exact else source}",
        "x": x, "y": y, "mode": "lines", "kind": "transformer_damage_exact" if exact else "transformer_damage",
        "damage_source": source,
    }]


def _generator_damage_traces(gen: dict):
    x, y, source = _generator_damage_trace(gen)
    if not x:
        return []
    return [{
        "name": f"{gen['name']} — dano do estator", "x": x, "y": y, "mode": "lines",
        "kind": "generator_damage", "damage_source": source,
    }]


def _cable_damage_trace(cable, k_adiabatic, max_current, min_current=10.0):
    """Trecho de curto-tempo da curva térmica I²t do cabo.

    O STAR do ETAP não prolonga ``Cable-P`` até a região de operação
    contínua. A curva de dano térmico é exibida somente na janela de
    curto tempo; acima dela a referência pertinente é a ampacidade (reta
    vertical), quando a ampacidade do cabo estiver cadastrada.

    Quando o ETAP fornece K²S² diretamente, esse valor tem precedência:
        t = K²S² / I(kA)²

    A janela visual é parametrizável no cadastro do cabo e, para o caso
    atual, segue o STAR: 0,01 s <= t <= 10 s. Os extremos são calculados
    diretamente da equação, de modo que o traço começa e termina
    exatamente nesses tempos.
    """
    t_min = float(cable.get("thermal_plot_tmin_s") or 0.01)
    t_max = float(cable.get("thermal_plot_tmax_s") or 10.0)
    if t_max < t_min:
        t_min, t_max = t_max, t_min

    k2s2 = cable.get("thermal_k2s2_ka2s")
    if k2s2 not in (None, "", 0):
        c = float(k2s2)
        # I[A] = 1000*sqrt(K²S²[kA²s] / t[s])
        i_lo = 1000.0 * math.sqrt(c / t_max)
        i_hi = 1000.0 * math.sqrt(c / t_min)
        xs, ys = [], []
        for n in range(260):
            x = i_lo * (i_hi / i_lo) ** (n / 259)
            ika = x / 1000.0
            t = c / (ika * ika)
            xs.append(x); ys.append(t)
        return xs, ys

    if k_adiabatic in (None, "", 0):
        return [], []
    k = float(k_adiabatic)
    total_section = float(cable["size_mm2"]) * int(cable["parallel"])
    a = k * total_section  # A*sqrt(s)
    i_lo = a / math.sqrt(t_max)
    i_hi = a / math.sqrt(t_min)
    xs, ys = [], []
    for n in range(240):
        x = i_lo * (i_hi / i_lo) ** (n / 239)
        t = (a / x) ** 2
        xs.append(x); ys.append(t)
    return xs, ys


# ======================================================================
# ANÁLISE DE ZONA
# Confere faixa do relé, sensibilidade, dever de interrupção e dados
# ausentes. Devolve ok / warn / bad, nunca um veredito sem origem.
# ======================================================================

def _relay_validation(zone, settings, mode="phase"):
    p = _prefix(mode)
    if not settings.get(f"{p}_enabled", True if mode == "phase" else False):
        return [{"title": f"Proteção {mode}", "status": "info", "text": "Função desabilitada."}]
    lib = RELAY_LIBRARY[settings["relay_model"]]
    ct = float(settings.get("ct_primary_a") or 1.0)
    out = []
    for stage, key in [(1, "stage1"), (2, "stage2"), (3, "stage3")]:
        pickup = settings.get(f"{p}_{key}_pickup_a")
        if not pickup:
            out.append({"title": f"Estágio {stage}", "status": "warn", "text": "Pickup não parametrizado."})
            continue
        pu = float(pickup) / ct
        lo, hi = lib[f"stage{stage}_pickup_pu"]
        ok = lo <= pu <= hi
        out.append({"title": f"Faixa real estágio {stage}", "status": "ok" if ok else "bad", "text": f"{float(pickup):.1f} A = {pu:.3f} × In(TC); faixa {lo:g}…{hi:g} × In."})
    curve = settings.get(f"{p}_curve")
    ts = settings.get(f"{p}_time_setting")
    if curve in CURVES and ts:
        lo, hi = lib["time_setting_ranges"][curve]
        family = CURVES[curve]["family"]
        out.append({"title": "TMS / Time Dial", "status": "ok" if lo <= float(ts) <= hi else "bad", "text": f"{float(ts):.4g}; faixa {lo:g}…{hi:g} para {CURVES[curve]['label']} ({family})."})
    return out


def analyze_zone(zone_id: str, settings=None, mode="phase"):
    """Objetivo: lista de verificações da zona, para a tela de análise.

    Devolve itens ``{title, status, text}`` com status ``ok``, ``warn``
    ou ``info``. Cada item é uma afirmação verificável sobre o ajuste
    atual: sensibilidade, sobrealcance, dano do cabo, partida e stall
    térmico do motor, inrush do transformador.

    Dado que não veio na exportação do ETAP gera ``warn`` dizendo o
    que falta — **nunca** um valor plausível inventado. Um estudo de
    proteção com número inventado é pior que um estudo incompleto,
    porque o leitor não tem como saber qual dos dois está lendo.
    """
    _, zones, motors, cables, trafos, _, _, _ = _ctx()
    zone = zones[zone_id]
    settings = settings or settings_for_zone(zone_id)
    motor = motors.get(zone.get("motor"))
    cable = cables.get(zone.get("cable"))
    trafo = trafos.get(zone.get("transformer"))
    out = [{"title": "Relé selecionado", "status": "info", "text": RELAY_LIBRARY[settings["relay_model"]]["label"] + ". " + RELAY_LIBRARY[settings["relay_model"]]["notes"]}]
    out += _relay_validation(zone, settings, mode)

    if mode == "phase":
        if cable:
            if cable.get("ampacity_total_a") in (None, "", 0):
                out.append({"title": "Ampacidade do cabo", "status": "warn", "text": "Não exportada no conjunto atual; não é inventada."})
            if settings.get("cable_k_adiabatic") in (None, "", 0):
                out.append({"title": "I²t do cabo", "status": "warn", "text": "Informe k adiabático confirmado por norma/fabricante para liberar t=(k·n·S/I)²."})
            else:
                out.append({"title": "I²t do cabo", "status": "ok", "text": f"k={float(settings['cable_k_adiabatic']):.2f} A√s/mm²; assume divisão uniforme entre {int(cable['parallel'])} cabo(s) paralelo(s)."})
        if motor:
            fla = float(motor["amp"]); ilr = float(motor["locked_rotor_current_a"])
            st = motor.get("start_time_s"); hot = motor.get("stall_hot_s"); cold = motor.get("stall_cold_s")
            start_txt = "não informado" if st in (None, "") else f"{float(st):.2f} s @ {float(motor.get('start_time_reference_voltage_percent') or 100):.0f}% Vt"
            out.append({"title": "Partida / LRC", "status": "info", "text": f"In={fla:.2f} A; LRC={float(motor['lrc_pu']):.2f} pu; ILR={ilr:.1f} A; aceleração nominal={start_txt}."})
            if hot not in (None, "") or cold not in (None, ""):
                stall_txt = []
                if hot not in (None, ""): stall_txt.append(f"Hot={float(hot):.1f} s")
                if cold not in (None, ""): stall_txt.append(f"Cold={float(cold):.1f} s")
                out.append({"title": "Stall térmico", "status": "info", "text": "; ".join(stall_txt) + ". São pontos térmicos do fabricante, não a curva completa."})
            if not motor.get("thermal_points"):
                out.append({"title": "Curva térmica completa do motor", "status": "warn", "text": "Os tempos Hot/Cold Stall estão cadastrados, mas os pontos da curva Thermal Limit (Points...) ainda não foram fornecidos."})
            p1 = settings.get("phase_stage1_pickup_a")
            curve = settings.get("phase_curve")
            if p1 and curve:
                w = motor_time_setting_window(motor, float(p1), curve, float(settings.get("coordination_margin_s") or 0.30))
                if w.get("available"):
                    hi = "—" if w.get("max_time_setting_hot") is None else f"{w['max_time_setting_hot']:.3f}"
                    out.append({"title": "Janela de TMS no LRC", "status": "info", "text": f"TMS mínimo pela partida={w['min_time_setting_start']:.3f}; máximo pelo Hot Stall={hi}. Verificar também coordenação a montante e a curva térmica completa."})
        if trafo:
            out.append({"title": f"Inrush {trafo['name']}", "status": "info", "text": f"Ponto cadastrado: {float(trafo['inrush_pu']):.1f} pu, {float(trafo['inrush_time_s']):.2f} s, {float(trafo['inrush_primary_a']):.1f} A no primário."})

    # Para fase, a sensibilidade usa a MENOR falta de fase do caso MIN
    # (min entre 3F e LL), em vez de assumir 3F MIN. Para dever de
    # interrupção, usa-se a maior corrente de falta disponível no caso
    # MAX.
    if mode == "phase":
        try:
            sc_min_row = get_bus_short_circuit(zone["bus"], "min")
            sc_max_row = get_bus_short_circuit(zone["bus"], "max")
            phase_min = select_critical_phase_min(sc_min_row)
            max_duty = select_max_fault_duty(sc_max_row)
        except Exception:
            phase_min = {"available": False, "fault": None, "ka": None}
            max_duty = {"available": False, "fault": None, "ka": None}
        p = _prefix(mode)
        p1 = settings.get(f"{p}_stage1_pickup_a")
        if phase_min.get("available") and p1:
            _, _, _, _, _, _, buses, _ = _ctx()
            bus_kv = float(buses[zone["bus"]]["kv"])
            sc_min = float(phase_min["ka"]) * 1000.0 * bus_kv / float(zone["kv"])
            sensitivity = sc_min / float(p1)
            out.append({"title": "Sensibilidade (interno)", "status": "ok" if sensitivity >= 1.5 else "bad", "text": f"Caso crítico MIN={phase_min['fault']} ({phase_min['ka']:.3f} kA); Icc mín referida / pickup = {sensitivity:.2f}. A linha de curto não é desenhada no TCC."})
        # O dever de interrupção NÃO usa o curto total na barra terminal
        # da zona. Para disjuntores físicos calculamos a falta
        # imediatamente a jusante do dispositivo e removemos as fontes
        # que estão do lado da carga, pois elas não atravessam o próprio
        # disjuntor.
        duty = breaker_duty_for_zone(zone_id, settings)
        if duty.get("available"):
            status = "ok" if duty["status"] == "approved" else ("bad" if duty["status"] == "rejected" else "warn")
            rating_txt = "não informado" if duty.get("rating_ka") is None else f"{duty['rating_ka']:.2f} kA"
            out.append({
                "title": "Capacidade de interrupção", "status": status,
                "text": (f"Icc MAX que atravessa {duty['breaker']} = {duty['duty_ka']:.2f} kA "
                         f"({duty['governing_fault']}, falta em {duty['fault_bus']}); critério com 10% = "
                         f"{duty['design_required_ka']:.2f} kA; classe seguinte = {duty['recommended_class_ka']:g} kA; "
                         f"interrupção nominal informada = {rating_txt}.")
            })
        elif zone.get("breaker"):
            out.append({"title": "Capacidade de interrupção", "status": "warn", "text": duty.get("reason", "Dever de interrupção indisponível.")})
    else:
        sc_min = _sc_value(zone, "min", "lg")
        p = _prefix(mode)
        p1 = settings.get(f"{p}_stage1_pickup_a")
        if sc_min is not None and p1:
            sensitivity = sc_min / float(p1)
            out.append({"title": "Sensibilidade (interno)", "status": "ok" if sensitivity >= 1.5 else "bad", "text": f"Icc LG mín referida / pickup = {sensitivity:.2f}."})
    if settings.get("estimated", True):
        out.append({"title": "Estado do ajuste", "status": "warn", "text": "Parametrização inicial. Ainda não é ajuste final aprovado."})
    return out


def _local_physical_traces(zone, settings, max_current, mode="phase"):
    _, _, motors, cables, trafos, _, _, _ = _ctx()
    motor = motors.get(zone.get("motor")); cable = cables.get(zone.get("cable")); trafo = trafos.get(zone.get("transformer"))
    traces, missing = [], []
    if cable:
        ampacity = settings.get("cable_ampacity_a") if settings else None
        if ampacity in (None, "", 0):
            ampacity = cable.get("ampacity_total_a")
        if ampacity not in (None, "", 0):
            amp = float(ampacity)
            traces.append({"name": f"{cable['name']} — Ampacity", "x": [amp, amp], "y": [0.01, 1000], "mode": "lines", "kind": "ampacity"})
        k = settings.get("cable_k_adiabatic")
        cx, cy = _cable_damage_trace(cable, k, max_current, min_current=10.0)
        if cx:
            traces.append({"name": f"{cable['name']} — limite adiabático I²t", "x": cx, "y": cy, "mode": "lines", "kind": "cable"})
        else:
            missing.append(f"{cable['name']}: I²t aguardando k adiabático")
    if mode == "phase" and motor:
        traces.append({"name": f"{motor['name']} — In {float(motor['amp']):.1f} A", "x": [float(motor["amp"]), float(motor["amp"])], "y": [0.01, 1000], "mode": "lines", "kind": "motor_nominal"})
        # LRC é referência de corrente; partida/stall são pontos ETAP.
        ilr = float(motor["locked_rotor_current_a"])
        traces.append({"name": f"{motor['name']} — ILR {ilr:.1f} A", "x": [ilr, ilr], "y": [0.01, 1000], "mode": "lines", "kind": "motor_lrc"})
        if motor.get("start_time_s") not in (None, ""):
            traces.append({"name": f"{motor['name']} — partida 100% Vt · {float(motor['start_time_s']):g} s", "x": [ilr], "y": [float(motor["start_time_s"])], "mode": "markers", "kind": "motor_start"})
        if motor.get("stall_hot_s") not in (None, ""):
            traces.append({"name": f"{motor['name']} — Hot Stall · {float(motor['stall_hot_s']):g} s", "x": [ilr], "y": [float(motor["stall_hot_s"])], "mode": "markers", "kind": "motor_stall_hot"})
        if motor.get("stall_cold_s") not in (None, ""):
            traces.append({"name": f"{motor['name']} — Cold Stall · {float(motor['stall_cold_s']):g} s", "x": [ilr], "y": [float(motor["stall_cold_s"])], "mode": "markers", "kind": "motor_stall_cold"})
        thermal = _motor_capability_traces(motor)
        traces.extend(thermal)
        if not motor.get("thermal_points") and thermal:
            missing.append(f"{motor['name']}: Hot/Cold desenhadas por aproximação de capacidade ancorada nos Stall Times; Points... do ETAP ainda não fornecidos")
        elif not thermal:
            missing.append(f"{motor['name']}: curva térmica indisponível")
    if mode == "phase" and trafo:
        traces.append({"name": f"{trafo['name']} — inrush 8 pu / 0,1 s", "x": [float(trafo["inrush_primary_a"])], "y": [float(trafo["inrush_time_s"])], "mode": "markers", "kind": "inrush"})
    return traces, missing


# ======================================================================
# BLOCO 3 — COORDENOGRAMAS (TCC)
# Por zona, por caminho de coordenacao e geral. Reunem os tracos dos
# reles com as curvas fisicas, todos referidos a mesma tensao-base.
# ======================================================================

def build_tcc(zone_id: str, mode="phase") -> dict:
    """Objetivo: montar o coordenograma de uma zona só.

        ajustes  ->  curvas do relé  ->  curvas físicas (dano, partida,
        inrush)  ->  traços prontos para o Plotly

    O eixo de corrente vai até o dobro da maior referência da zona (LRC
    do motor, inrush do trafo, pickups), para que a região de interesse
    não encoste na borda do gráfico.

    ``mode="phase"`` ou ``"neutral"`` escolhe o conjunto 50/51 ou
    50N/51N. Devolve também a lista de dados faltantes, para a tela
    poder dizer por que uma curva esperada não apareceu.
    """
    model, zones, motors, cables, trafos, _, _, _ = _ctx()
    if zone_id not in zones:
        raise KeyError(zone_id)
    mode = "neutral" if mode == "neutral" else "phase"
    zone = zones[zone_id]
    settings = settings_for_zone(zone_id)
    cable = cables.get(zone.get("cable")); motor = motors.get(zone.get("motor")); trafo = trafos.get(zone.get("transformer"))
    candidates = [10000.0]
    if motor: candidates.append(float(motor["locked_rotor_current_a"]) * 2.0)
    if trafo: candidates.append(float(trafo["inrush_primary_a"]) * 2.0)
    p = _prefix(mode)
    for key in (f"{p}_stage1_pickup_a", f"{p}_stage2_pickup_a", f"{p}_stage3_pickup_a"):
        if settings.get(key): candidates.append(float(settings[key]) * 2.0)
    max_current = max(candidates)
    traces = relay_stage_traces(settings, max_current, mode, zone["relay"])
    physical, missing = _local_physical_traces(zone, settings, max_current, mode)
    traces.extend(physical)
    base_current = float(motor["amp"]) if motor and mode == "phase" else float(settings.get(f"{p}_stage1_pickup_a") or 100.0)
    return {
        "scope": "local", "mode": mode, "zone": zone, "settings": settings,
        "relay": RELAY_LIBRARY[settings["relay_model"]],
        "curve_label": CURVES[settings[f"{p}_curve"]]["label"],
        "traces": traces, "analyses": analyze_zone(zone_id, settings, mode), "provisional_items": missing,
        "physical": {"motor": motor, "cable": cable, "transformer": trafo},
        "breaker_duty": breaker_duty_for_zone(zone_id, settings) if mode == "phase" else None,
        "reference_kv": float(zone["kv"]),
        "x_range": [max(5.0, base_current * 0.35), max_current], "y_range": [0.01, 1000.0],
    }


def _shift_trace(trace: dict, factor: float, suffix: str) -> dict:
    t = dict(trace)
    t["x"] = [float(x) * factor for x in trace.get("x", [])]
    t["name"] = trace["name"] + suffix
    return t


def _coordination_pairs(path: dict, zones: dict) -> list[dict]:
    """Retorna os pares principal/retaguarda do caminho.

    Modelos antigos sem ``coordination_pairs`` continuam funcionando: o
    ponto de falta é derivado da barra terminal da zona jusante de cada
    par.
    """
    configured = path.get("coordination_pairs") or []
    if configured:
        return [dict(p) for p in configured]
    pairs = []
    for downstream, upstream in zip(path["zones"], path["zones"][1:]):
        dz = zones[downstream]
        pairs.append({
            "id": f"PAIR-{downstream}-{upstream}",
            "downstream_zone": downstream,
            "upstream_zone": upstream,
            "fault_bus": dz["bus"],
            "label": f"{dz['relay']} → {zones[upstream]['relay']}",
        })
    return pairs


# ======================================================================
# BLOCO 4 — SISTEMA ESPECIALISTA
# Sugestão de ajustes por regras clássicas de sobrecorrente. Cada regra
# registra id, texto e valores de entrada, para auditoria.
# ======================================================================

# Intervalo clássico de coordenação (CTI). Pode ser sobrescrito
# por ``coordination_margin_s`` no cadastro do caminho.
CTI_DEFAULT_S = 0.30


def _all_coordination_pairs(model: dict, zones: dict) -> list[dict]:
    pairs: list[dict] = []
    for path in model.get("coordination_paths", []):
        pairs.extend(_coordination_pairs(path, zones))
    return pairs


def suggest_phase_settings(zone_id: str) -> dict:
    """Sistema especialista de sugestão de ajustes 50/51 de FASE.

    Aplica regras clássicas de sobrecorrente sobre os mesmos dados
    físicos e elétricos já usados no resto do estudo (FLA,
    curto-circuito IEC 60909 já calculado pelo Pandapower, curva do
    relé, dados de fabricante) — não inventa cálculo novo, só decide um
    valor de ajuste a partir do que já existe. Cada regra fica
    registrada explicitamente (id, texto, números de entrada) para o
    engenheiro auditar e, se quiser, discordar.

    Escopo desta versão: somente a função de FASE (50/51). Neutro/terra
    fica de fora por decisão explícita do usuário nesta etapa.
    """
    model, zones, motors, cables, trafos, gens, buses, paths = _ctx()
    if zone_id not in zones:
        raise KeyError(zone_id)
    zone = zones[zone_id]
    settings = settings_for_zone(zone_id)
    curve = settings.get("phase_curve") or "IEC_EI"
    rules: list[dict] = []
    warnings: list[str] = []

    all_pairs = _all_coordination_pairs(model, zones)
    upstream_of = [p for p in all_pairs if p["upstream_zone"] == zone_id]

    # --- Regra 1: pickup 51 = margem sobre a corrente nominal protegida
    # ----
    fla = _protected_fla(zone, motors, trafos, gens)
    if zone.get("motor"):
        factor, rule_text = 1.15, "1,15 × FLA — margem de serviço/desbalanço usual para motor"
    elif zone.get("transformer"):
        factor, rule_text = 1.25, "1,25 × FLA — margem de sobrecarga admissível usual para transformador"
    elif zone.get("generator"):
        factor, rule_text = 1.10, "1,10 × FLA — margem reduzida (gerador já conta com outras proteções dedicadas)"
    else:
        factor, rule_text = 1.25, "1,25 × FLA — margem padrão"
    pickup51_suggested = round(factor * fla, 1)
    rules.append({
        "id": "R51-PICKUP", "title": "Pickup 51 (fase)", "rule": rule_text,
        "inputs": {"FLA_A": round(fla, 2)},
        "suggested": pickup51_suggested, "current": settings.get("phase_stage1_pickup_a"), "unit": "A",
    })

    # --- Regra 2: TMS 51 = margem de coordenação (CTI) com o relé de
    # jusante Quando há mais de um relé de jusante em paralelo (ex.:
    # Relé1 do gerador coordena com Relé10/T1 E com Relé3/M-B-6 ao mesmo
    # tempo), o ajuste tem que satisfazer os dois — usa-se sempre o mais
    # exigente (pior caso), nunca uma média. Todos os candidatos ficam
    # visíveis, não só o vencedor.
    tms_suggested = None
    if upstream_of:
        candidates_tms = []
        for pair in upstream_of:
            try:
                row_min = get_bus_short_circuit(pair["fault_bus"], "min")
                critical = select_critical_phase_min(row_min)
                if not critical.get("available"):
                    continue
                fault_i_a = float(critical["ka"]) * 1000.0
                fault_kv = float(buses[pair["fault_bus"]]["kv"])
                i_up = _shift_current(fault_i_a, fault_kv, float(zone["kv"]))
                down_zone = zones[pair["downstream_zone"]]
                down_settings = settings_for_zone(pair["downstream_zone"])
                i_down = _shift_current(fault_i_a, fault_kv, float(down_zone["kv"]))
                down_detail = relay_operation_detail(i_down, down_settings, "phase")
                t_down = down_detail.get("time_s")
                t_down_source = "tempo exato do ajuste"
                if t_down is None:
                    # Sem tempo exato conhecido (ex.: "50" instantâneo
                    # sem operating_time informado): usa o limite MÁXIMO
                    # do catálogo do fabricante de forma conservadora,
                    # em vez de descartar esse ramal da coordenação. Um
                    # ramal em paralelo não pode sumir do cálculo só
                    # porque falta um dado — isso mascararia justamente
                    # o caso mais restritivo.
                    t_down = down_detail.get("time_bound_max_s")
                    t_down_source = "limite máximo de catálogo (tempo exato não informado)"
                if t_down is None:
                    continue
                opening = down_settings.get("breaker_opening_time_s")
                t_down_clearing = t_down if opening in (None, "", 0) else t_down + float(opening)
                margin = float(down_settings.get("coordination_margin_s") or CTI_DEFAULT_S)
                target_t_up = t_down_clearing + margin
                m = i_up / pickup51_suggested
                cfg = CURVES[curve]
                if m <= 1.0:
                    continue
                denom = m ** cfg["alpha"] - 1.0
                if denom <= 0:
                    continue
                tms_needed = target_t_up / (cfg["k"] / denom + cfg["L"])
                candidates_tms.append({
                    "pair": pair["label"], "fault_bus": pair["fault_bus"], "i_up_a": i_up,
                    "t_down_s": t_down_clearing, "margin_s": margin, "target_t_up_s": target_t_up,
                    "tms_needed": tms_needed, "t_down_source": t_down_source,
                })
            except Exception as exc:
                warnings.append(f"Coordenação {pair['label']}: {exc}")
        worst = max(candidates_tms, key=lambda c: c["tms_needed"]) if candidates_tms else None
        if worst:
            lo, hi = RELAY_LIBRARY[zone["relay_model"]]["time_setting_ranges"][curve]
            tms_raw = worst["tms_needed"]
            tms_suggested = round(min(max(tms_raw, lo), hi), 3)
            parallel_note = (
                f" ({len(candidates_tms)} ramais em paralelo avaliados — usado o mais exigente)"
                if len(candidates_tms) > 1 else ""
            )
            rules.append({
                "id": "R51-TMS", "title": "TMS / Time Dial (fase)",
                "rule": f"Margem de coordenação (CTI) de {worst['margin_s']:.2f} s acima de {worst['pair']}, "
                        f"na falta de fase MIN em {worst['fault_bus']} ({worst['t_down_source']}){parallel_note}",
                "inputs": {
                    "candidatos": [
                        {"regra": f"{c['pair']} (falta em {c['fault_bus']})", "valor_a": round(c["tms_needed"], 4)}
                        for c in sorted(candidates_tms, key=lambda c: -c["tms_needed"])
                    ],
                    "I_montante_A": round(worst["i_up_a"], 1),
                    "t_jusante_s": round(worst["t_down_s"], 4),
                    "t_alvo_montante_s": round(worst["target_t_up_s"], 4),
                },
                "suggested": tms_suggested, "current": settings.get("phase_time_setting"), "unit": "",
                "clamped": round(tms_raw, 3) != tms_suggested,
            })
        else:
            rules.append({
                "id": "R51-TMS", "title": "TMS / Time Dial (fase)",
                "rule": "Há relé de jusante no caminho, mas a falta MIN de coordenação não está disponível "
                        "(recalcule o sistema elétrico).",
                "inputs": {}, "suggested": None, "current": settings.get("phase_time_setting"), "unit": "",
            })
    else:
        rules.append({
            "id": "R51-TMS", "title": "TMS / Time Dial (fase)",
            "rule": "Esta zona não tem relé de jusante no caminho de coordenação modelado — "
                    "TMS não é derivado automaticamente aqui (ajuste por critério próprio).",
            "inputs": {}, "suggested": None, "current": settings.get("phase_time_setting"), "unit": "",
        })

    # --- Regra 3: pickup 50 = seletividade com jusante / inrush /
    # partida --
    candidates_50 = []
    for pair in upstream_of:
        try:
            row_max = get_bus_short_circuit(pair["fault_bus"], "max")
            maximum = select_max_phase_fault(row_max)
            if not maximum.get("available"):
                continue
            fault_kv = float(buses[pair["fault_bus"]]["kv"])
            i_up = _shift_current(float(maximum["ka"]) * 1000.0, fault_kv, float(zone["kv"]))
            candidates_50.append({
                "label": f"seletividade com {pair['label']} (falta de fase MAX em {pair['fault_bus']})",
                "value": 1.25 * i_up,
            })
        except Exception as exc:
            warnings.append(f"Seletividade 50 {pair['label']}: {exc}")
    if zone.get("motor"):
        m = motors[zone["motor"]]
        ilr = float(m["locked_rotor_current_a"])
        asym = float(m.get("asym_locked_rotor_factor") or 1.6)
        candidates_50.append({
            "label": f"partida do motor {zone['motor']} (LRC × fator assimétrico)",
            "value": 1.7 * ilr * asym,
        })
    if zone.get("transformer") and zone.get("application") == "transformer_hv":
        t = trafos[zone["transformer"]]
        candidates_50.append({
            "label": f"inrush de energização de {zone['transformer']}",
            "value": 1.25 * float(t["inrush_primary_a"]),
        })
    pickup50_suggested = None
    if candidates_50:
        governing = max(candidates_50, key=lambda c: c["value"])
        pickup50_suggested = round(governing["value"], 1)
        rules.append({
            "id": "R50-PICKUP", "title": "Pickup 50 (instantâneo, fase)",
            "rule": f"Governado por: {governing['label']}",
            "inputs": {"candidatos": [{"regra": c["label"], "valor_a": round(c["value"], 1)} for c in candidates_50]},
            "suggested": pickup50_suggested, "current": settings.get("phase_stage3_pickup_a"), "unit": "A",
        })
    else:
        rules.append({
            "id": "R50-PICKUP", "title": "Pickup 50 (instantâneo, fase)",
            "rule": "Nenhuma regra clássica aplicável identificada para esta zona "
                    "(sem relé de jusante, motor ou transformador com inrush).",
            "inputs": {}, "suggested": None, "current": settings.get("phase_stage3_pickup_a"), "unit": "A",
        })

    return {
        "zone": zone_id, "relay": zone["relay"], "title": zone["title"], "curve": curve,
        "rules": rules, "warnings": warnings,
    }


def suggest_all_phase_settings() -> dict:
    """Objetivo: rodar o módulo especialista em todas as zonas.

    Erro em uma zona não derruba as outras: a zona que falhou volta com
    ``{"zone": ..., "error": ...}`` e a tela mostra o motivo no lugar da
    sugestão.
    """
    _, zones, _, _, _, _, _, _ = _ctx()
    items = []
    for zone_id in zones:
        try:
            items.append(suggest_phase_settings(zone_id))
        except Exception as exc:
            items.append({"zone": zone_id, "error": str(exc)})
    return {"zones": items}


# ======================================================================
# COORDENAÇÃO ENTRE PARES
# Avalia principal/retaguarda na falta do fim da zona de jusante.
# Margem insuficiente reprova; dado faltando devolve pendente.
# ======================================================================

def evaluate_coordination_pair(pair: dict, mode="phase") -> dict:
    """Objetivo: dizer se um par principal/retaguarda coordena.

        falta no fim da zona de jusante  ->  tempo do principal
        ->  tempo da retaguarda  ->  margem = t_retag − t_princ

    A falta é posta no **fim da zona de jusante**, que é o ponto onde a
    margem é mais apertada: ali a corrente é a menor que o principal
    ainda deve enxergar, e portanto o tempo dele é o maior.

    Margem abaixo do mínimo adotado reprova. Dado faltando devolve
    *pendente*, não aprovado — não saber não é o mesmo que estar certo.
    """
    model, zones, _, _, _, _, buses, _ = _ctx()
    mode = "neutral" if mode == "neutral" else "phase"
    down = zones[pair["downstream_zone"]]
    up = zones[pair["upstream_zone"]]
    fault_bus = pair["fault_bus"]
    bus = buses[fault_bus]
    result = {
        **pair,
        "downstream_relay": down["relay"],
        "upstream_relay": up["relay"],
        "fault_bus_kv": float(bus["kv"]),
        "status": "pending",
    }
    if mode != "phase":
        result.update({"reason": "Coordenação de neutro não é deslocada através dos transformadores Dyn."})
        return result
    try:
        row_min = get_bus_short_circuit(fault_bus, "min")
        row_max = get_bus_short_circuit(fault_bus, "max")
        critical = select_critical_phase_min(row_min)
        maximum = select_max_phase_fault(row_max)
    except Exception as exc:
        result.update({"reason": f"Curto-circuito indisponível em {fault_bus}: {exc}", "fault_min": {"available": False}, "fault_max": {"available": False}})
        return result
    result["fault_min"] = critical
    result["fault_max"] = maximum
    if not critical.get("available"):
        result["reason"] = f"Falta de fase MIN indisponível em {fault_bus}."
        return result

    fault_i_a = float(critical["ka"]) * 1000.0
    fault_kv = float(bus["kv"])
    i_down = _shift_current(fault_i_a, fault_kv, float(down["kv"]))
    i_up = _shift_current(fault_i_a, fault_kv, float(up["kv"]))
    s_down = settings_for_zone(down["id"])
    s_up = settings_for_zone(up["id"])
    down_op = relay_operation_detail(i_down, s_down, "phase")
    up_op = relay_operation_detail(i_up, s_up, "phase")
    t_down, stage_down = down_op.get("time_s"), down_op.get("stage")
    t_up, stage_up = up_op.get("time_s"), up_op.get("stage")
    margin = float(s_down.get("coordination_margin_s") or 0.30)

    if not down_op.get("acts") or not up_op.get("acts"):
        delta = None
        status = "pending"
        reason = "Um dos relés não sensibiliza para a falta MIN escolhida; Δt não pode ser calculado."
    elif not down_op.get("time_known") or not up_op.get("time_known"):
        # V18: um limite MÁXIMO de tempo do relé jusante pode aprovar o
        # par conservadoramente. Se t_jusante <= tmax, então Δt >=
        # t_montante-tmax. O mesmo limite no relé montante NÃO permite
        # aprovação, pois o tempo real pode ser menor e reduzir a
        # seletividade.
        dmax = down_op.get("time_bound_max_s") if not down_op.get("time_known") else None
        umax = up_op.get("time_bound_max_s") if not up_op.get("time_known") else None
        if dmax not in (None, "", 0) and up_op.get("time_known"):
            delta = float(t_up) - float(dmax)
            if delta >= margin:
                status = "approved"
                reason = (
                    f"Aprovação conservadora por limite de fabricante: {down['relay']} {stage_down} atua em <= {float(dmax):.3f} s; "
                    f"logo Δt >= {delta:.3f} s, acima da margem de {margin:.3f} s."
                )
            else:
                status = "pending"
                reason = (
                    f"Com o limite máximo de fabricante do relé jusante, só se garante Δt >= {delta:.3f} s, "
                    f"inferior à margem de {margin:.3f} s; é necessário tempo medido/exato para concluir."
                )
        elif up_op.get("time_known") is False and umax not in (None, "", 0) and down_op.get("time_known"):
            delta = float(umax) - float(t_down)
            if delta < margin:
                status = "rejected"
                reason = (
                    f"Mesmo usando o limite máximo do relé montante ({float(umax):.3f} s), Δt <= {delta:.3f} s, "
                    f"abaixo da margem de {margin:.3f} s."
                )
            else:
                status = "pending"
                reason = "O relé montante possui apenas limite máximo de tempo; isso não é suficiente para aprovar seletividade."
        else:
            delta = None
            status = "pending"
            missing = []
            if not down_op.get("time_known"):
                missing.append(f"{down['relay']} ({stage_down})")
            if not up_op.get("time_known"):
                missing.append(f"{up['relay']} ({stage_up})")
            reason = "Tempo físico do estágio instantâneo pendente em " + " e ".join(missing) + "; não há limite suficiente para concluir Δt."
    else:
        delta = float(t_up) - float(t_down)
        if delta >= margin:
            status = "approved"
            reason = f"Critério Δt={delta:.3f} s atende à margem de {margin:.3f} s. Isso aprova somente a seletividade temporal deste par."
        else:
            status = "rejected"
            reason = f"Critério Δt={delta:.3f} s é inferior à margem de {margin:.3f} s."
    result.update({
        "status": status,
        "approval_scope": "coordination_time_only",
        "reason": reason,
        "margin_s": margin,
        "downstream": {"zone": down["id"], "relay": down["relay"], "kv": float(down["kv"]), "current_a": i_down, "time_s": t_down, "stage": stage_down, "time_known": down_op.get("time_known"), "time_source": down_op.get("time_source"), "time_bound_max_s": down_op.get("time_bound_max_s"), "clearing_time_s": down_op.get("clearing_time_s")},
        "upstream": {"zone": up["id"], "relay": up["relay"], "kv": float(up["kv"]), "current_a": i_up, "time_s": t_up, "stage": stage_up, "time_known": up_op.get("time_known"), "time_source": up_op.get("time_source"), "time_bound_max_s": up_op.get("time_bound_max_s"), "clearing_time_s": up_op.get("clearing_time_s")},
        "delta_t_s": delta,
        "delta_t_relation": ">=" if (not down_op.get("time_known") and down_op.get("time_bound_max_s") not in (None, "", 0) and up_op.get("time_known")) else ("<=" if (not up_op.get("time_known") and up_op.get("time_bound_max_s") not in (None, "", 0) and down_op.get("time_known")) else "="),
    })
    return result


def evaluate_path_coordination(path_id: str, mode="phase") -> list[dict]:
    """Objetivo: avaliar todos os pares de um caminho de coordenação.

    Monta os pares consecutivos do caminho e chama
    ``evaluate_coordination_pair`` em cada um. Levanta ``KeyError`` se o
    caminho não existe.
    """
    model, zones, _, _, _, _, _, paths = _ctx()
    if path_id not in paths:
        raise KeyError(path_id)
    path = paths[path_id]
    return [evaluate_coordination_pair(pair, mode) for pair in _coordination_pairs(path, zones)]


def _pair_analysis_lines(path: dict, mode="phase") -> list[dict]:
    if mode != "phase":
        return [{"title": "Coordenação de neutro", "status": "warn", "text": "50N/51N deve ser verificada por zona aterrada; não se aplica curve shift de sequência zero através dos primário delta de T1."}]
    rows = evaluate_path_coordination(path["id"], mode)
    out = [{"title": "Critério V18", "status": "info", "text": "A seletividade é verificada par a par. Cada par usa a menor falta de fase MIN (min entre 3F e LL) no extremo da zona da proteção jusante."}]
    for row in rows:
        fault = row.get("fault_min") or {}
        if row["status"] == "pending":
            status = "warn"
        else:
            status = "ok" if row["status"] == "approved" else "bad"
        if not fault.get("available"):
            text = f"{row['fault_bus']}: falta MIN indisponível. {row.get('reason','')}"
        else:
            d = row.get("downstream") or {}; u = row.get("upstream") or {}
            td = (f"{d['time_s']:.3f}s ({d.get('stage')})" if d.get("time_s") is not None else
                  (f"≤{d['time_bound_max_s']:.3f}s ({d.get('stage')} · catálogo máx.)" if d.get("time_bound_max_s") is not None else "—"))
            tu = (f"{u['time_s']:.3f}s ({u.get('stage')})" if u.get("time_s") is not None else
                  (f"≤{u['time_bound_max_s']:.3f}s ({u.get('stage')} · catálogo máx.)" if u.get("time_bound_max_s") is not None else "—"))
            delta = "—" if row.get("delta_t_s") is None else f"{row.get('delta_t_relation','=' )}{row['delta_t_s']:.3f}s"
            text = (f"Falta {fault['fault']} MIN em {row['fault_bus']} = {fault['ka']:.3f} kA; "
                    f"{d.get('relay')} vê {d.get('current_a',0):.1f} A e atua em {td}; "
                    f"{u.get('relay')} vê {u.get('current_a',0):.1f} A e atua em {tu}; Δt={delta}. {row.get('reason','')}")
        out.append({"title": row.get("label") or f"{row['downstream_relay']} → {row['upstream_relay']}", "status": status, "text": text})
    return out


def _path_coordination(path: dict, mode="phase"):
    return _pair_analysis_lines(path, mode)


def build_path_tcc(path_id: str, mode="phase", reference_kv=None) -> dict:
    """Objetivo: um coordenograma com todos os relés do caminho juntos.

        cada relé na sua tensão  ->  ×(kV_relé / kV_ref)  ->  mesma base
        ->  um gráfico comparável

    Relés em tensões diferentes não podem ser comparados no mesmo
    eixo de corrente: 100 A em 13,8 kV não é a mesma falta que 100 A
    em 6,6 kV. O caminho escolhe uma tensão de referência e cada curva
    é deslocada pela relação de transformação. É o mesmo que o ETAP faz
    ao desenhar um Star view multi-tensão.

    Em modo neutro não há traço: o neutro não atravessa o Dyn do
    transformador, e desenhar as curvas juntas sugeriria uma coordenação
    que não existe fisicamente.
    """
    model, zones, motors, cables, trafos, _, buses, paths = _ctx()
    if path_id not in paths:
        raise KeyError(path_id)
    path = paths[path_id]
    mode = "neutral" if mode == "neutral" else "phase"
    ref_kv = float(reference_kv or path["reference_kv"])
    if mode == "neutral":
        return {"scope": "path", "mode": mode, "path": path, "reference_kv": ref_kv, "traces": [], "analyses": _path_coordination(path, mode), "coordination_pairs": evaluate_path_coordination(path_id, mode), "provisional_items": ["Neutro não é deslocado através dos transformadores Dyn"], "x_range": [10, 10000], "y_range": [0.01, 1000]}

    max_ref = 10000.0
    for zid in path["zones"]:
        s = settings_for_zone(zid); z = zones[zid]
        for key in ("phase_stage1_pickup_a", "phase_stage2_pickup_a", "phase_stage3_pickup_a"):
            if s.get(key): max_ref = max(max_ref, _shift_current(float(s[key]) * 2.0, float(z["kv"]), ref_kv))
    motor = motors.get(path.get("motor"))
    if motor: max_ref = max(max_ref, _shift_current(float(motor["locked_rotor_current_a"]) * 2, float(motor["kv"]), ref_kv))
    for tn in path.get("transformers", []):
        t = trafos[tn]; max_ref = max(max_ref, _shift_current(float(t["inrush_primary_a"]) * 2, float(t["vn_hv_kv"]), ref_kv))

    traces, missing = [], []
    # Relés do caminho, todos referidos à mesma base.
    for zid in path["zones"]:
        z = zones[zid]; s = settings_for_zone(zid)
        native_max = max_ref * ref_kv / float(z["kv"])
        factor = float(z["kv"]) / ref_kv
        for tr in relay_stage_traces(s, native_max, "phase", z["relay"]):
            shifted = _shift_trace(tr, factor, f" · ref. {ref_kv:g} kV")
            shifted["zone_id"] = zid
            shifted["group"] = "relay"
            traces.append(shifted)

    # Motor terminal: In e LRC como referências de corrente.
    if motor:
        factor = float(motor["kv"]) / ref_kv
        traces.append({"name": f"{motor['name']} — In", "x": [float(motor["amp"]) * factor] * 2, "y": [0.01, 1000], "mode": "lines", "kind": "motor_nominal"})
        ilr = float(motor["locked_rotor_current_a"]) * factor
        traces.append({"name": f"{motor['name']} — ILR", "x": [ilr, ilr], "y": [0.01, 1000], "mode": "lines", "kind": "motor_lrc"})
        if motor.get("start_time_s") not in (None, ""):
            traces.append({"name": f"{motor['name']} — partida 100% Vt", "x": [ilr], "y": [float(motor["start_time_s"])], "mode": "markers", "kind": "motor_start"})
        if motor.get("stall_hot_s") not in (None, ""):
            traces.append({"name": f"{motor['name']} — Hot Stall", "x": [ilr], "y": [float(motor["stall_hot_s"])], "mode": "markers", "kind": "motor_stall_hot"})
        if motor.get("stall_cold_s") not in (None, ""):
            traces.append({"name": f"{motor['name']} — Cold Stall", "x": [ilr], "y": [float(motor["stall_cold_s"])], "mode": "markers", "kind": "motor_stall_cold"})
        for thermal in _motor_capability_traces(motor):
            shifted = dict(thermal)
            shifted["x"] = [float(x) * factor for x in thermal.get("x", [])]
            shifted["group"] = "motor"
            traces.append(shifted)

    # Inrush e capacidade/dano dos transformadores. As curvas de dano
    # são geradas no lado AT e depois deslocadas para a base do
    # coordenograma.
    for tn in path.get("transformers", []):
        t = trafos[tn]
        x = _shift_current(float(t["inrush_primary_a"]), float(t["vn_hv_kv"]), ref_kv)
        traces.append({"name": f"{tn} — inrush 8 pu / 0,1 s · ref. {ref_kv:g} kV", "x": [x], "y": [float(t["inrush_time_s"])], "mode": "markers", "kind": "inrush"})
        factor = float(t["vn_hv_kv"]) / ref_kv
        for dmg in _transformer_damage_traces(t):
            shifted = dict(dmg)
            shifted["x"] = [float(xx) * factor for xx in dmg.get("x", [])]
            shifted["group"] = "transformer"
            shifted["transformer"] = tn
            traces.append(shifted)

    # I²t dos cabos do caminho. k vem do ajuste da zona proprietária do
    # cabo.
    cable_owner = {z.get("cable"): z["id"] for z in zones.values() if z.get("cable")}
    for cn in path.get("cables", []):
        c = cables[cn]; owner = cable_owner.get(cn); s = settings_for_zone(owner) if owner else {}
        k = s.get("cable_k_adiabatic")
        native_max = max_ref * ref_kv / float(buses[c["to_bus"]]["kv"])
        cx, cy = _cable_damage_trace(c, k, native_max, min_current=10.0)
        if cx:
            factor = float(buses[c["to_bus"]]["kv"]) / ref_kv
            traces.append({"name": f"{cn} — I²t · ref. {ref_kv:g} kV", "x": [x * factor for x in cx], "y": cy, "mode": "lines", "kind": "cable"})
        else:
            missing.append(f"{cn}: I²t aguardando k adiabático")

    analyses = _path_coordination(path, "phase")
    analyses.insert(0, {"title": "Curve shift", "status": "info", "text": f"Todas as correntes foram referidas a {ref_kv:g} kV por Iref=Ilocal·Vlocal/Vref. O deslocamento vale para magnitude de corrente de fase equilibrada."})
    return {"scope": "path", "mode": "phase", "path": path, "reference_kv": ref_kv, "traces": traces, "analyses": analyses, "coordination_pairs": evaluate_path_coordination(path_id, "phase"), "provisional_items": missing, "x_range": [10.0, max_ref], "y_range": [0.01, 1000.0]}


def build_master_tcc(mode="phase", reference_kv=6.6, include_faults=True) -> dict:
    """Coordenograma geral da planta reduzida.

    Todas as curvas são referidas à mesma tensão-base. Na função de fase
    a V18 pode ainda desenhar linhas verticais de Icc MIN/MAX nos pontos
    de falta usados pelos pares de coordenação. Essas linhas são
    referências visuais; o cálculo de Δt continua sendo realizado em
    cada par no seu nível nativo.
    """
    model, zones, motors, cables, trafos, _, buses, paths = _ctx()
    mode = "neutral" if mode == "neutral" else "phase"
    ref_kv = float(reference_kv or 6.6)
    traces, missing = [], []
    max_ref = 10000.0
    for zid, z in zones.items():
        s = settings_for_zone(zid)
        p = _prefix(mode)
        for key in (f"{p}_stage1_pickup_a", f"{p}_stage2_pickup_a", f"{p}_stage3_pickup_a"):
            if s.get(key):
                max_ref = max(max_ref, _shift_current(float(s[key]) * 2, float(z["kv"]), ref_kv))

    # Pré-calcula as referências de falta antes de gerar as curvas, para
    # que os três estágios dos relés se estendam até o maior Icc
    # mostrado.
    fault_refs = []
    if mode == "phase" and include_faults:
        seen_buses = set()
        for path in paths.values():
            for pair in _coordination_pairs(path, zones):
                fault_bus = pair["fault_bus"]
                if fault_bus in seen_buses:
                    continue
                seen_buses.add(fault_bus)
                try:
                    row_min = get_bus_short_circuit(fault_bus, "min")
                    row_max = get_bus_short_circuit(fault_bus, "max")
                    fmin = select_critical_phase_min(row_min)
                    fmax = select_max_phase_fault(row_max)
                except Exception:
                    fmin = {"available": False}; fmax = {"available": False}
                native_kv = float(buses[fault_bus]["kv"])
                if fmin.get("available"):
                    x = _shift_current(float(fmin["ka"]) * 1000.0, native_kv, ref_kv)
                    max_ref = max(max_ref, x * 1.15)
                    fault_refs.append({"name": f"Icc MIN {fault_bus} · {fmin['fault']}", "x": [x, x], "y": [0.01, 1000], "mode": "lines", "kind": "fault_min", "group": "fault", "fault_bus": fault_bus})
                if fmax.get("available"):
                    x = _shift_current(float(fmax["ka"]) * 1000.0, native_kv, ref_kv)
                    max_ref = max(max_ref, x * 1.15)
                    fault_refs.append({"name": f"Icc MAX {fault_bus} · {fmax['fault']}", "x": [x, x], "y": [0.01, 1000], "mode": "lines", "kind": "fault_max", "group": "fault", "fault_bus": fault_bus})

    # Curvas de todos os relés.
    for zid, z in zones.items():
        s = settings_for_zone(zid)
        factor = float(z["kv"]) / ref_kv
        native_max = max_ref / factor
        for tr in relay_stage_traces(s, native_max, mode, z["relay"]):
            shifted = _shift_trace(tr, factor, f" · {z['kv']:g}→{ref_kv:g} kV")
            shifted["zone_id"] = zid
            shifted["group"] = "relay"
            traces.append(shifted)

    if mode == "phase":
        # Grandezas físicas principais. V30: motor fora de serviço não
        # aparece no coordenograma geral — o desenho mostra a
        # configuração que está rodando. O coordenograma da zona do
        # próprio motor continua desenhando as curvas.
        for m in motors.values():
            if not bool(m.get("in_service", True)):
                continue
            factor = float(m["kv"]) / ref_kv
            traces.append({"name": f"{m['name']} — In", "x": [float(m["amp"]) * factor] * 2, "y": [0.01, 1000], "mode": "lines", "kind": "motor_nominal", "group": "motor"})
            ilr = float(m["locked_rotor_current_a"]) * factor
            traces.append({"name": f"{m['name']} — ILR", "x": [ilr, ilr], "y": [0.01, 1000], "mode": "lines", "kind": "motor_lrc", "group": "motor"})
            if m.get("start_time_s") not in (None, ""):
                traces.append({"name": f"{m['name']} — partida 100% Vt", "x": [ilr], "y": [float(m["start_time_s"])], "mode": "markers", "kind": "motor_start", "group": "motor"})
            if m.get("stall_hot_s") not in (None, ""):
                traces.append({"name": f"{m['name']} — Hot Stall", "x": [ilr], "y": [float(m["stall_hot_s"])], "mode": "markers", "kind": "motor_stall_hot", "group": "motor"})
            if m.get("stall_cold_s") not in (None, ""):
                traces.append({"name": f"{m['name']} — Cold Stall", "x": [ilr], "y": [float(m["stall_cold_s"])], "mode": "markers", "kind": "motor_stall_cold", "group": "motor"})
            for thermal in _motor_capability_traces(m):
                shifted = dict(thermal)
                shifted["x"] = [float(x) * factor for x in thermal.get("x", [])]
                shifted["group"] = "motor"
                traces.append(shifted)
        for t in trafos.values():
            traces.append({"name": f"{t['name']} — inrush 8 pu / 0,1 s", "x": [_shift_current(t["inrush_primary_a"], t["vn_hv_kv"], ref_kv)], "y": [t["inrush_time_s"]], "mode": "markers", "kind": "inrush", "group": "transformer"})

        # Icc MIN/MAX dos pontos realmente usados nos pares de
        # coordenação.
        traces.extend(fault_refs)

    # Cabos: somente quando k é conhecido.
    cable_owner = {z.get("cable"): z["id"] for z in zones.values() if z.get("cable")}
    for c in cables.values():
        owner = cable_owner.get(c["name"])
        s = settings_for_zone(owner) if owner else {}
        k = s.get("cable_k_adiabatic")
        native_kv = float(buses[c["to_bus"]]["kv"])
        native_max = max_ref * ref_kv / native_kv
        cx, cy = _cable_damage_trace(c, k, native_max)
        if cx:
            factor = native_kv / ref_kv
            traces.append({"name": f"{c['name']} — I²t", "x": [x * factor for x in cx], "y": cy, "mode": "lines", "kind": "cable", "group": "cable"})
        else:
            missing.append(f"{c['name']}: I²t sem k")

    pair_rows = []
    pair_keys = set()
    for path in paths.values():
        for row in evaluate_path_coordination(path["id"], mode):
            key = (row["downstream_zone"], row["upstream_zone"], row["fault_bus"])
            if key not in pair_keys:
                pair_keys.add(key)
                pair_rows.append(row)

    analyses = [
        {"title": "Coordenograma geral V18", "status": "info", "text": "Cada relé é mostrado pela característica efetiva. 3F/LL MIN de fase usam o solver radial IEC validado; Icc MAX permanece no Pandapower. O Δt é calculado par a par; limite máximo de fabricante no relé jusante pode liberar uma aprovação conservadora (Δt ≥ limite calculado)."},
        {"title": "Cabos Cu/XLPE — I²t", "status": "info", "text": "O modelo físico identifica os três cabos ativos como cobre/XLPE. A V18 preserva o estudo adiabático com k=143 A√s/mm², θi=90 °C e θf=250 °C. É uma hipótese padrão editável, não um dado de ampacidade nem substitui a verificação do tempo total de eliminação."},
    ]
    if mode == "neutral":
        analyses.append({"title": "Neutro", "status": "warn", "text": "Curvas de 50N/51N de níveis separados por delta não devem ser interpretadas como uma cadeia única de coordenação."})
    else:
        approved = sum(1 for r in pair_rows if r.get("status") == "approved")
        rejected = sum(1 for r in pair_rows if r.get("status") == "rejected")
        pending = sum(1 for r in pair_rows if r.get("status") == "pending")
        analyses.append({"title": "Pares de seletividade", "status": "bad" if rejected else ("warn" if pending else "ok"), "text": f"{approved} aprovado(s), {rejected} reprovado(s) e {pending} pendente(s). Consulte a tabela de pares abaixo do coordenograma geral."})

    return {
        "scope": "master", "mode": mode, "reference_kv": ref_kv,
        "traces": traces, "analyses": analyses, "coordination_pairs": pair_rows,
        "provisional_items": missing, "x_range": [10.0, max_ref], "y_range": [0.01, 1000.0],
    }



# ======================================================================
# BLOCO 5 — FOLHA ETAP STAR
# Reprodução da apresentação do relatório original: marcas curtas de
# ajuste no topo, setas de falta na base, moldura e carimbo.
# ======================================================================
#
# Marcas curtas do ETAP Star.
#
# O Star não desenha ampacidade, pickup e corrente de falta como retas
# de altura total. Ele usa marcas curtas: as de ajuste ficam encostadas
# no topo da folha e as de falta ficam encostadas na base, com ponta de
# seta. As frações abaixo foram medidas no STAR75 (folha 0,01 s .. 1000
# s): ampacidade do cabo -> 603 s .. 794 s   (10^-0,22 .. 10^-0,10 do
# topo) pickup do relé     -> 700 s .. 1000 s  (10^-0,155 .. topo)
# corrente de falta  -> 0,010 s .. 0,021 s (base .. 10^+0,32 da base)
_MARK_AMPACITY_SPAN = (-0.22, -0.10)
_MARK_PICKUP_SPAN = (-0.155, 0.0)
_FAULT_ARROW_DECADES = 0.32


def _top_mark(name: str, current_a: float, kind: str, span, y_max: float = 1000.0, **extra) -> dict | None:
    """Marca curta encostada no topo da folha, no estilo do Star."""
    try:
        i = float(current_a)
    except (TypeError, ValueError):
        return None
    if not (i > 0):
        return None
    lo, hi = span
    trace = {"name": name, "x": [i, i],
             "y": [float(y_max) * 10 ** lo, float(y_max) * 10 ** hi],
             "mode": "lines", "kind": kind, "value_a": i, "mark": "top"}
    trace.update(extra)
    return trace


def _fault_mark(name: str, current_a: float, kind: str, y_min: float = 0.01, **extra) -> dict | None:
    """Seta curta na base da folha marcando uma corrente de curto."""
    try:
        i = float(current_a)
    except (TypeError, ValueError):
        return None
    if not (i > 0):
        return None
    trace = {"name": name, "x": [i, i],
             "y": [float(y_min), float(y_min) * 10 ** _FAULT_ARROW_DECADES],
             "mode": "lines", "kind": kind, "value_a": i, "mark": "bottom", "arrow": True}
    trace.update(extra)
    return trace


def _fault_reference_trace(bus_name: str, reference_kv: float, case: str, fault_key: str, label: str, kind: str):
    """Linha vertical de curto, referida à base do TCC."""
    try:
        _, _, _, _, _, _, buses, _ = _ctx()
        row = get_bus_short_circuit(bus_name, case)
        key = {"3f": "3f_ka", "ll": "ll_ka", "lg": "lg_ka", "llg": "llg_ka"}[fault_key]
        ka = row.get(key)
        if ka in (None, ""):
            return None
        native_kv = float(buses[bus_name]["kv"])
        current = _shift_current(float(ka) * 1000.0, native_kv, float(reference_kv))
        return _fault_mark(label, current, kind,
                           source=row.get("phase_min_method") if case == "min" else "Pandapower IEC 60909",
                           bus=bus_name, ka=float(ka), case=case, fault=fault_key.upper())
    except Exception:
        return None


def _motor_view_fault_note(zone_id: str) -> str | None:
    """Objetivo: dizer, em palavras, o que a seta da folha de motor é.

        seta desenhada  =  falta total na barra do equipamento (MAX)
        corrente da coordenação  =  passante pelo relé, sem o motor

    A folha de um ramal de motor desenha **uma** seta: o curto na barra
    do próprio equipamento, com o motor dentro. É a que acompanha o
    estudo quando a placa do motor muda, e é a leitura que o aluno
    procura.

    Os números que a proteção usa são outros e continuam calculados: a
    corrente *passante* pelo relé exclui o motor protegido, porque ele
    não alimenta um curto atrás do próprio cabo, e é contra ela que o
    50/51 é verificado. Como ela saiu do desenho, vem escrita aqui,
    junto do mínimo de sensibilidade — nenhum número se perde.

    Devolve ``None`` quando a zona não tem motor ou falta dado.
    """
    try:
        _, zones, _, _, _, _, _, _ = _ctx()
        zone = zones[zone_id]
        motor = zone.get("motor")
        if not motor:
            return None
        total = get_bus_short_circuit(zone["bus"], "max").get("3f_ka")
        if total in (None, ""):
            return None
        partes = [f"{zone['bus']} - 3P = {_br(float(total), 3)} kA é a "
                  f"falta total na barra do {motor}, com o motor dentro: "
                  f"é ela que muda quando a placa do motor muda."]
        try:
            remoto = run_zone_remote_fault(zone_id, "max")
            passante = remoto.get("3f_ka")
        except Exception:
            passante = None
        if passante not in (None, ""):
            partes.append(
                f"A coordenação do {zone['relay']} continua usando a "
                f"corrente passante, {_br(float(passante), 3)} kA, que "
                f"exclui o próprio {motor} — ele não alimenta um curto "
                f"atrás do próprio cabo.")
        try:
            mn = run_zone_remote_fault(zone_id, "min")
            minimos = [v for v in (mn.get("3f_ka"), mn.get("ll_ka"))
                       if v not in (None, "")]
            if minimos:
                partes.append(
                    f"Sensibilidade: mínimo de "
                    f"{_br(min(float(v) for v in minimos), 3)} kA.")
        except Exception:
            pass
        return " ".join(partes)
    except Exception:
        return None


def _relay_trace_for_zone(zone_id: str, reference_kv: float, max_ref_a: float = 1e6):
    _, zones, _, _, _, _, _, _ = _ctx()
    zone = zones[zone_id]
    settings = settings_for_zone(zone_id)
    factor = float(zone["kv"]) / float(reference_kv)
    native_max = max(float(max_ref_a) / max(factor, 1e-12), float(settings.get("phase_stage3_pickup_a") or 0) * 2.0, 1e4)
    tr = relay_effective_trace(settings, native_max, "phase", zone["relay"])
    if not tr:
        return None
    t = _shift_trace(tr, factor, "")
    t["name"] = zone["relay"] + " - P OC1"
    t["zone_id"] = zone_id
    t["kind"] = "relay_effective"
    t["relay"] = zone["relay"]
    return t


def _relay_pickup_mark(zone_id: str, reference_kv: float, mode="phase") -> dict | None:
    """Marca curta do pickup 51 no topo da folha, como no Star."""
    _, zones, _, _, _, _, _, _ = _ctx()
    zone = zones[zone_id]
    settings = settings_for_zone(zone_id)
    pickup = settings.get(f"{_prefix(mode)}_stage1_pickup_a")
    if pickup in (None, "", 0):
        return None
    factor = float(zone["kv"]) / float(reference_kv)
    return _top_mark(f"{zone['relay']} · pickup 51", float(pickup) * factor,
                     "pickup_mark", _MARK_PICKUP_SPAN, relay=zone["relay"], zone_id=zone_id)


# Forma da curva de partida do ETAP Star, medida no STAR75 (Barra5 6,6
# kV) do caso M-B-0 (FLA = 154,4 A, LRC = 1003,6 A, Accel. Time = 1,0
# s). Os pontos vetoriais do PDF, depois de calibrados contra dois
# valores conhecidos do mesmo desenho (pickup 230 A e 50P 7760 A, erro <
# 0,15 %), dão:
#
# (154,4 A ; topo)  vertical na FLA (154,4 A ; 1,165 s) -> (179,5 A ;
# 1,002 s)   joelho arredondado (179,5 A ; 1,002 s) -> (758,2 A ; 1,002
# s)   patamar no tempo de aceleração (758,2 A ; 1,002 s) -> (1003,5 A ;
# 0,757 s)  queda até a LRC (1003,5 A ; 0,757 s) -> (1003,5 A ; 0,100 s)
# vertical na LRC (1003,5 A ; 0,100 s) -> (1605,2 A ; 0,010 s) cauda
# assimétrica (offset CC)
#
# Os multiplicadores abaixo são exatamente essas razões, de modo que
# qualquer motor com FLA/LRC/Accel. Time conhecidos produza a mesma
# geometria do Star.
_START_KNEE_X = 1.1626          # 179,5 / 154,4
_START_KNEE_Y = 1.1650          # 1,165 / 1,000
_START_PLATEAU_END_X = 0.7555   # 758,2 / 1003,5
_START_LRC_Y = 0.7570           # 0,757 / 1,000
# Cauda assimétrica: tempos absolutos (decaimento do offset CC),
# correntes em pu da LRC.
_START_TAIL = [(1.0000, 0.100), (1.0289, 0.0552), (1.1385, 0.0281), (1.3904, 0.0137), (1.5996, 0.010)]


def _motor_start_envelope(motor: dict, reference_kv: float, y_max: float = 1000.0) -> dict | None:
    """Curva de partida a 100 % Vt no formato do ETAP Star.

    Usa somente dados do modelo (FLA, LRC e tempo de aceleração). A
    geometria reproduz a do Star: vertical na FLA, joelho, patamar no
    tempo de aceleração, queda até a LRC, vertical na LRC e cauda
    assimétrica até o fundo da folha.
    """
    if motor.get("start_time_s") in (None, ""):
        return None
    factor = float(motor["kv"]) / float(reference_kv)
    fla = float(motor["amp"]) * factor
    ilr = float(motor["locked_rotor_current_a"]) * factor
    ta = float(motor["start_time_s"])
    if fla <= 0 or ilr <= fla or ta <= 0:
        return None

    x_knee = fla * _START_KNEE_X
    x_plateau_end = max(ilr * _START_PLATEAU_END_X, x_knee * 1.02)
    xs = [fla, fla]
    ys = [float(y_max), ta * _START_KNEE_Y]
    # Joelho arredondado entre a vertical da FLA e o patamar.
    for f in (0.35, 0.65, 0.85):
        xs.append(fla * (_START_KNEE_X ** f))
        ys.append(ta * (_START_KNEE_Y ** (1.0 - f)))
    xs += [x_knee, x_plateau_end]
    ys += [ta, ta]
    # Queda suave do patamar até a corrente de rotor bloqueado.
    for f in (0.4, 0.75):
        xs.append(x_plateau_end * ((ilr / x_plateau_end) ** f))
        ys.append(ta * (_START_LRC_Y ** (f * f)))
    xs.append(ilr)
    ys.append(ta * _START_LRC_Y)
    # Fim do corpo da partida. A verificação de piso usa só até aqui: a
    # cauda abaixo é o offset CC, tratado pelo pickup do 50, não por
    # tempo.
    body_points = len(xs)
    # Vertical na LRC + cauda assimétrica; a cauda só é desenhada abaixo
    # do patamar, para não cruzar a própria curva quando o tempo de
    # partida é curto.
    for mult, t in _START_TAIL:
        t = min(float(t), ta * _START_LRC_Y * 0.999)
        xs.append(ilr * mult)
        ys.append(t)
    return {"name": f"{motor['name']}-100%", "x": xs, "y": ys,
            "mode": "lines", "kind": "motor_start",
            "source": "FLA + LRC + Accel.Time 100% Vt (geometria ETAP Star)",
            "fla_a": fla, "lrc_a": ilr, "accel_time_s": ta, "body_points": body_points}



def _interp_loglog(xs, ys, x):
    """Interpola em log-log. Fora da faixa dos pontos devolve None."""
    if not xs or x < xs[0] or x > xs[-1]:
        return None
    for i in range(1, len(xs)):
        if x <= xs[i]:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            if x1 <= x0 or y0 <= 0 or y1 <= 0:
                return y1
            f = math.log(x / x0) / math.log(x1 / x0)
            return math.exp(math.log(y0) + f * (math.log(y1) - math.log(y0)))
    return ys[-1]


def _motor_band_trace(motor: dict, reference_kv: float, samples: int = 40) -> dict | None:
    """Faixa entre a partida (piso) e o dano térmico (teto) do motor.

    É a região onde a curva do relé precisa caber. Só é desenhada onde
    existe dado dos DOIS lados: acima do último ponto de dano exportado
    a faixa simplesmente termina, deixando visível que ali não há teto
    conhecido.
    """
    env = _motor_start_envelope(motor, reference_kv)
    dx, dy = _motor_thermal_trace(motor)
    if not env or not dx:
        return None
    factor = float(motor["kv"]) / float(reference_kv)
    ceil_x = [x * factor for x in dx]
    ceil_y = list(dy)
    body = env.get("body_points", len(env["x"]))
    floor_pts = [(x, y) for x, y in zip(env["x"][:body], env["y"][:body]) if y < 999]
    if len(floor_pts) < 2:
        return None
    floor_x = [p[0] for p in floor_pts]
    floor_y = [p[1] for p in floor_pts]
    lo = max(floor_x[0], ceil_x[0])
    hi = min(floor_x[-1], ceil_x[-1])
    if hi <= lo:
        return None
    xs = [lo * (hi / lo) ** (i / (samples - 1)) for i in range(samples)]
    bottom, top = [], []
    for x in xs:
        fy = _interp_loglog(floor_x, floor_y, x)
        cy = _interp_loglog(ceil_x, ceil_y, x)
        if fy is None or cy is None or cy <= fy:
            continue
        bottom.append((x, fy))
        top.append((x, cy))
    if len(bottom) < 2:
        return None
    poly_x = [p[0] for p in bottom] + [p[0] for p in reversed(top)]
    poly_y = [p[1] for p in bottom] + [p[1] for p in reversed(top)]
    return {
        "name": f"Banda de ajuste · {motor['name']}",
        "x": poly_x, "y": poly_y, "mode": "lines", "kind": "motor_band",
        "range_a": [lo, hi],
        "note": ("Faixa entre a partida e o dano do motor, desenhada só onde existe dado dos dois lados."),
    }


def _motor_view_traces(motor_name: str, relay_zone: str, reference_kv: float, cable_name: str):
    _, _, motors, cables, _, _, _, _ = _ctx()
    motor = motors[motor_name]; cable = cables[cable_name]
    settings = settings_for_zone(relay_zone)
    factor = float(motor["kv"]) / float(reference_kv)
    traces = []
    # V30: a banda sombreada entre partida e dano saiu da folha. O ETAP
    # não desenha essa região, e num coordenograma a área pintada
    # compete com as curvas — que são o que se lê. A função
    # _motor_band_trace() continua disponível para uso em material
    # didático, mas não entra na folha. Curva térmica/capacidade do
    # motor. Quando existem Points do ETAP, eles têm precedência
    # absoluta: não usamos aproximação nem stall time para fabricar a
    # curva.
    caps = _motor_capability_traces(motor)
    if caps:
        main = dict(caps[0]); main = _shift_trace(main, factor, "")
        if main.get("thermal_source") == "ETAP Points":
            main["name"] = motor_name
            main["kind"] = "motor_thermal_exact"
        else:
            main["name"] = f"{motor_name} · capacidade estimada"
            main["kind"] = "motor_thermal_hot"
        traces.append(main)
        if len(caps) > 1:
            cold = dict(caps[1]); cold = _shift_trace(cold, factor, "")
            cold["name"] = f"{motor_name} · Cold (referência)"
            cold["kind"] = "motor_thermal_cold"; cold["visible"] = "legendonly"; traces.append(cold)
    # V30: a curva de Hot Start passa a aparecer JUNTO com os Points do
    # ETAP, não no lugar deles. São coisas diferentes e o ajuste precisa
    # respeitar as duas: os Points são a curva de limite térmico
    # exportada do fabricante; a de Hot Start é a envoltória a partir do
    # tempo de stall com o motor já aquecido, que é a condição crítica
    # na prática. Só é desenhada se o ETAP estiver com Hot Start marcado
    # (stall_hot_enabled).
    if motor.get("stall_hot_enabled", False) and not any(
        tr.get("kind") == "motor_thermal_hot" for tr in traces
    ):
        hx, hy = _motor_capability_trace(motor, "hot")
        # V30: o limite térmico de rotor bloqueado vale entre a corrente
        # nominal e a de rotor bloqueado — acima disso o motor já está
        # fora do domínio da curva, e prolongá-la até a faixa de curto
        # desenhava um traço enorme atravessando a folha inteira, que o
        # ETAP não mostra. Quando há Points do fabricante, a curva
        # começa onde eles terminam, para as duas se completarem em vez
        # de se sobreporem.
        ilr_motor = float(motor.get("locked_rotor_current_a") or 0.0)
        pts = motor.get("thermal_points") or []
        i_ini = float(motor["amp"]) * max(p[0] for p in pts) if pts else 0.0
        if hx and ilr_motor > 0:
            par = [(x, y) for x, y in zip(hx, hy) if x <= ilr_motor * 1.001 and x >= i_ini]
            hx = [p[0] for p in par]; hy = [p[1] for p in par]
            if hx and abs(hx[-1] - ilr_motor) > 1e-6:
                hx.append(ilr_motor); hy.append(float(motor["stall_hot_s"]))
        if hx:
            hot = _shift_trace({
                "name": f"{motor_name} · Hot Start · {float(motor['stall_hot_s']):g} s",
                "x": hx, "y": hy, "mode": "lines", "kind": "motor_thermal_hot",
                "thermal_source": "stall-capacity approximation (Hot Start)",
            }, factor, "")
            traces.append(hot)
    ilr = float(motor["locked_rotor_current_a"]) * factor
    start_env = _motor_start_envelope(motor, reference_kv)
    if start_env:
        traces.append(start_env)
    # Cabo: ampacidade só aparece se houver valor informado; dano usa
    # equação adiabática Cu/XLPE.
    amp = settings.get("cable_ampacity_a")
    if amp in (None, "", 0):
        amp = cable.get("ampacity_total_a")
    if amp not in (None, "", 0):
        # A ampacidade é um dado do cabo, referido à tensão da barra de
        # onde ele sai. (Antes lia-se uma chave "from_kv" que nenhum
        # cabo possui: caía sempre no kV do motor e só funcionava
        # porque, nas duas vistas de motor, cabo e motor estão no mesmo
        # nível de tensão.)
        _, _, _, _, _, _, _buses, _ = _ctx()
        cable_kv = float(_buses.get(cable.get("from_bus"), {}).get("kv") or motor["kv"])
        a = float(amp) * cable_kv / float(reference_kv)
        mk = _top_mark(f"{cable_name} Ampacity", a, "ampacity", _MARK_AMPACITY_SPAN,
                       source=cable.get("ampacity_source") or "ajuste do usuário")
        if mk:
            traces.append(mk)
    max_native = max(1e5, ilr * 20.0)
    cx, cy = _cable_damage_trace(cable, settings.get("cable_k_adiabatic"), max_native, min_current=max(10.0, float(motor["amp"]) * 0.6))
    if cx:
        traces.append({"name": f"{cable_name} - P", "x": [x * factor for x in cx], "y": cy, "mode": "lines", "kind": "cable"})
    return traces


def protection_context(zone_id: str) -> dict:
    """Liga as correntes de curto aos ajustes reais do relé.

    A sequência é intencionalmente explícita: o solver calcula Icc; esta
    função apenas aplica os ajustes 50/51 salvos a essas correntes. Ela
    não recalcula nem inventa o curto-circuito.
    """
    model, zones, motors, cables, trafos, generators, buses, _ = _ctx()
    if zone_id not in zones:
        raise KeyError(zone_id)
    zone = zones[zone_id]
    settings = settings_for_zone(zone_id)
    relay_cfg = RELAY_LIBRARY[settings["relay_model"]]
    result = {
        "zone": zone,
        "settings": settings,
        "relay": relay_cfg,
        "protected_fla_a": _protected_fla(zone, motors, trafos, generators),
        "faults": {},
        "calculations": {},
    }

    # Conversões do ajuste primário para o secundário real do TC /
    # múltiplo In.
    ctp = settings.get("ct_primary_a")
    cts = settings.get("ct_secondary_a")
    ratio = None if not ctp or not cts else float(ctp) / float(cts)
    p51 = settings.get("phase_stage1_pickup_a")
    p50 = settings.get("phase_stage3_pickup_a")
    curve_key = settings.get("phase_curve", "IEC_EI")
    ts = settings.get("phase_time_setting")
    curve = CURVES.get(curve_key)
    setting_calc = {
        "ct_ratio": ratio,
        "pickup_51_secondary_a": None if ratio is None or not p51 else float(p51) / ratio,
        "pickup_50_secondary_a": None if ratio is None or not p50 else float(p50) / ratio,
        "pickup_51_multiple_ct": None if not ctp or not p51 else float(p51) / float(ctp),
        "pickup_50_multiple_ct": None if not ctp or not p50 else float(p50) / float(ctp),
        "curve": None if curve is None else {"key": curve_key, **curve},
        "time_setting": ts,
    }
    if curve:
        family = curve["family"]
        setting_calc["formula"] = (
            "t = TMS·K/(M^α−1)" if family == "IEC" else "t = TD·(K/(M^α−1)+L)"
        )
        setting_calc["constants"] = {"K": curve["k"], "alpha": curve["alpha"], "L": curve["L"]}
    # Verificação de faixa física do P241, sem alterar o ajuste.
    warnings = []
    if setting_calc["pickup_51_multiple_ct"] is not None:
        lo, hi = relay_cfg["stage1_pickup_pu"]
        if not (lo <= setting_calc["pickup_51_multiple_ct"] <= hi):
            warnings.append(f"51P fora da faixa do relé ({lo:g}…{hi:g} × In).")
    if setting_calc["pickup_50_multiple_ct"] is not None:
        lo, hi = relay_cfg["stage3_pickup_pu"]
        if not (lo <= setting_calc["pickup_50_multiple_ct"] <= hi):
            warnings.append(f"50P fora da faixa do relé ({lo:g}…{hi:g} × In).")
    if curve_key in relay_cfg.get("time_setting_ranges", {}) and ts not in (None, ""):
        lo, hi = relay_cfg["time_setting_ranges"][curve_key]
        if not (lo <= float(ts) <= hi):
            warnings.append(f"TMS/TD fora da faixa do relé para {curve_key} ({lo:g}…{hi:g}).")
    setting_calc["warnings"] = warnings
    result["calculations"]["setting"] = setting_calc

    try:
        if zone.get("motor"):
            try:
                mx = run_zone_remote_fault(zone_id, "max")
                mn = run_zone_remote_fault(zone_id, "min")
                if mx.get("3f_ka") is None or (mn.get("3f_ka") is None and mn.get("ll_ka") is None):
                    raise RuntimeError("corrente remota indisponível")
            except Exception:
                mx = get_bus_short_circuit(zone["bus"], "max")
                mn = get_bus_short_circuit(zone["bus"], "min")
        else:
            mx = get_bus_short_circuit(zone["bus"], "max")
            mn = get_bus_short_circuit(zone["bus"], "min")
        bus_kv = float(buses[zone["bus"]]["kv"])
        relay_kv = float(zone["kv"])
        f3max = None if mx.get("3f_ka") is None else float(mx["3f_ka"]) * 1000.0 * bus_kv / relay_kv
        candidates = [("3F", mn.get("3f_ka")), ("LL", mn.get("ll_ka"))]
        candidates = [(name, float(v)) for name, v in candidates if v not in (None, "")]
        crit_name, crit_ka = min(candidates, key=lambda x: x[1]) if candidates else (None, None)
        fmin = None if crit_ka is None else crit_ka * 1000.0 * bus_kv / relay_kv
        result["faults"] = {
            "3f_max_a": f3max,
            "phase_min_a": fmin,
            "phase_min_fault": crit_name,
            "fault_bus": zone["bus"],
            "bus_kv": bus_kv,
            "source_max": mx.get("method") or "Pandapower IEC 60909",
            "source_min": mn.get("phase_min_method") or mn.get("source") or "IEC MIN",
        }
        if p51 and fmin:
            result["calculations"]["sensitivity"] = fmin / float(p51)

        # Para cada corrente calculada, mostramos tanto a função 51
        # isolada quanto o estágio efetivamente governante (51 ou
        # high-set 50).
        for key, current in (("max", f3max), ("min", fmin)):
            if not current:
                continue
            t51 = relay_time(float(current), float(p51), float(ts), curve_key) if p51 and ts and curve_key in CURVES else None
            m = None if not p51 else float(current) / float(p51)
            t_eff, stage = relay_operating_time(float(current), settings, "phase")
            result["calculations"][key] = {
                "current_a": current,
                "multiple_51": m,
                "time_51_s": t51,
                "time_s": t_eff,
                "stage": stage,
            }
    except Exception as exc:
        result["fault_error"] = str(exc)

    motor = motors.get(zone.get("motor"))
    cable = cables.get(zone.get("cable"))
    trafo = trafos.get(zone.get("transformer"))
    result["physical"] = {"motor": motor, "cable": cable, "transformer": trafo}
    return result


def _view_single_line(view: str) -> dict:
    """Unifilar reduzido desenhado dentro da folha, como no Star.

    A lista vai do barramento (topo) para a carga (base). O front
    desenha cada tipo com o símbolo correspondente; aqui só descrevemos
    a topologia. V29: cabos e motores levam também ``sub``
    (especificação no padrão ETAP, ex. "3-3/C 25" ou "6000 kW"), lido do
    modelo físico atual (com eventuais edições de equipamento
    aplicadas), para bater com o STAR original.
    """
    _, zones, motors, cables, _, _, _, _ = _ctx()

    def cable_spec(name):
        c = cables.get(name)
        if not c:
            return None
        parallel = int(c.get("parallel") or 1)
        phase = int(c.get("phase") or 3)
        size = c.get("size_mm2")
        size_txt = f"{float(size):g}" if size not in (None, "") else "?"
        return f"{parallel}-{phase}/C {size_txt}"

    def motor_spec(name):
        m = motors.get(name)
        if not m or m.get("kw") in (None, ""):
            return None
        return f"{float(m['kw']):g} kW"

    def branch(zone_id):
        z = zones[zone_id]
        out = []
        if z.get("breaker"):
            out.append({"type": "breaker", "label": z["breaker"], "relay": z.get("relay")})
        elif z.get("relay"):
            out.append({"type": "relay_only", "label": z["relay"], "relay": z.get("relay")})
        if z.get("cable"):
            out.append({"type": "cable", "label": z["cable"], "sub": cable_spec(z["cable"])})
        if z.get("motor"):
            out.append({"type": "motor", "label": z["motor"], "sub": motor_spec(z["motor"])})
        return out
    if view == "mb0":
        return {"bus": "Barra5", "elements": branch("Z-R11")}
    if view == "mb6":
        return {"bus": "Barra3", "elements": branch("Z-R3")}
    if view == "t1":
        return {"bus": "Barra3", "elements": [
            {"type": "breaker", "label": "DJ2", "relay": "Relé10"},
            {"type": "transformer", "label": "T1", "sub": "13,8/6,6 kV"},
            {"type": "relay_only", "label": "Relé12", "relay": "Relé12"},
            {"type": "bus_end", "label": "Barra5"},
            {"type": "relay_only", "label": "Relé11", "relay": "Relé11", "dim": True}]}
    # Vista Geral: sem unifilar ao lado. Ela junta relés de ramais
    # diferentes, então um único fio vertical não representa o que está
    # no gráfico — o desenho só ocupava espaço. As outras três vistas
    # seguem com o painel.
    return {"bus": "Barra3", "elements": []}


def _sheet_block(view: str, fault_mode: str = "Phase") -> dict:
    """Carimbo do rodapé, no mesmo formato do Star."""
    import datetime as _dt
    from .data import CASE_ID, CASE_NAME
    return {
        "sheet": {"mb0": "TCC-01", "mb6": "TCC-02", "t1": "TCC-03", "general": "TCC-04"}.get(view, "TCC"),
        "left": [("Project", CASE_NAME), ("Location", ""), ("Contract", ""), ("Engineer", "")],
        "right": [("Date", _dt.date.today().strftime("%m-%d-%Y")), ("SN", CASE_ID),
                  ("Rev", "Base"), ("Fault", fault_mode)],
        "tool": "SEEP · Simulador Elétrico de Estudos de Proteção",
    }


# Relés que cada vista desenha, na ordem em que aparecem. Usado para
# montar o painel de ajuste ao lado do gráfico — o painel não adivinha a
# vista.
_VIEW_ZONES = {
    "mb0": ["Z-R11"],
    "mb6": ["Z-R3"],
    "t1": ["Z-R11", "Z-R12", "Z-R10"],
    "general": ["Z-R1", "Z-R10", "Z-R3"],
}
# Campos que mexem na curva de fase e por isso valem edição ao vivo.
TCC_LIVE_FIELDS = (
    "phase_curve",
    "phase_stage1_pickup_a",
    "phase_time_setting",
    "phase_stage3_pickup_a",
    "phase_stage3_delay_s",
)


def build_concise_tcc(view="mb0") -> dict:
    """Objetivo: as quatro folhas de coordenograma do estudo.

        fluxo  ->  IEC 60909  ->  corrente que atravessa o relé
        ->  curva 50/51 + referências físicas

    ``view`` escolhe a folha: ``mb0``, ``mb6``, ``t1`` ou
    ``general``. As três primeiras são ramais; ``general`` junta os
    relés de alimentação e por isso não desenha unifilar — um fio
    vertical único não representaria ramais diferentes.

    Lê os resultados elétricos do cache. Trocar pickup ou TMS e
    reabrir a folha não dispara Pandapower de novo: só a proteção
    mudou.
    """
    pf = run_power_flow()
    scmax = run_short_circuit("max")
    scmin = run_short_circuit("min")
    _, zones, motors, cables, trafos, gens, _, _ = _ctx()
    view = str(view or "mb0").lower()
    traces = []; notes = []
    if view == "mb0":
        ref = 6.6; title = "M-B-0 · 6,6 kV"; subtitle = "Relé11 · Cabo2 · M-B-0"
        tr = _relay_trace_for_zone("Z-R11", ref); traces += [tr] if tr else []
        traces.append(_relay_pickup_mark("Z-R11", ref))
        traces += _motor_view_traces("M-B-0", "Z-R11", ref, "Cabo2")
        # V30: uma seta só, o curto na barra do próprio equipamento. As
        # duas setas antigas eram a corrente passante pelo relé, que
        # exclui o motor protegido e por isso não se mexia quando a
        # placa do motor mudava. Os dois números seguem calculados e
        # aparecem na nota da folha (ver _motor_view_fault_note).
        ft = _fault_reference_trace("Barra6", ref, "max", "3f", "Barra6 - 3P", "fault_max")
        if ft: traces.append(ft)
        mnota = _motor_view_fault_note("Z-R11")
        if mnota: notes.append(mnota)
        c = cables["Cabo2"]; refc=c.get("etap_sc_reference",{}).get("3f_ka")
        if refc: notes.append(f"Validação ETAP Cabo2: 3F MAX = {refc:.3f} kA; a linha do TCC usa o valor calculado pelo estudo.")
        notes.append("Fluxo → IEC 60909 → corrente que atravessa Relé11/Cabo2 → curva 50/51.")
    elif view == "mb6":
        ref = 13.8; title = "M-B-6 · 13,8 kV"; subtitle = "Relé3 · Cabo8 · M-B-6"
        tr = _relay_trace_for_zone("Z-R3", ref); traces += [tr] if tr else []
        traces.append(_relay_pickup_mark("Z-R3", ref))
        traces += _motor_view_traces("M-B-6", "Z-R3", ref, "Cabo8")
        # Mesma escolha da folha do M-B-0: uma seta, o curto na Barra4.
        ft = _fault_reference_trace("Barra4", ref, "max", "3f", "Barra4 - 3P", "fault_max")
        if ft: traces.append(ft)
        mnota = _motor_view_fault_note("Z-R3")
        if mnota: notes.append(mnota)
        c = cables["Cabo8"]; refc=c.get("etap_sc_reference",{}).get("3f_ka")
        if refc: notes.append(f"Validação ETAP Cabo8: 3F MAX = {refc:.3f} kA; a linha do TCC usa o valor calculado pelo estudo.")
        notes.append("Fluxo → IEC 60909 → corrente que atravessa Relé3/Cabo8 → curva 50/51.")
    elif view == "t1":
        ref = 13.8; title = "T1 · 13,8/6,6 kV"; subtitle = "Relé11 · Relé12 · Relé10 · T1"
        for zid in ("Z-R11", "Z-R12", "Z-R10"):
            tr = _relay_trace_for_zone(zid, ref); traces += [tr] if tr else []
            traces.append(_relay_pickup_mark(zid, ref))
        t1 = trafos["T1"]
        traces.append({"name": "T1 Inrush", "x": [float(t1["inrush_primary_a"])], "y": [float(t1["inrush_time_s"])], "mode": "markers", "kind": "inrush"})
        dx, dy, source = _transformer_damage_trace(t1)
        if dx:
            exact = source == "ETAP Points"
            traces.append({"name": "T1 Withstand" + ("" if exact else f" · {source}"), "x": dx, "y": dy, "mode": "lines", "kind": "transformer_damage" if not exact else "transformer_damage_exact"})
        for args in (("Barra5", ref, "max", "3f", "Barra5 - 3P", "fault_max"), ("Barra5", ref, "min", "ll", "Barra5 - LL", "fault_min")):
            ft = _fault_reference_trace(*args); traces += [ft] if ft else []
        notes.append("Relé11/12 são deslocados de 6,6 para 13,8 kV por Iref = I·Vlocal/Vref.")
        if not t1.get("damage_points_pu"): notes.append(f"T1 Withstand calculada por ANSI/IEEE C57.109 (categoria {t1.get('damage_category','?')}), a partir do curto MAX já calculado pelo estudo — não copiada de dado externo.")
    elif view == "general":
        ref = 13.8; title = "Coordenação geral · 13,8 kV"; subtitle = "Relé1 · Relé10 · Relé3 · Cabo1 · Cabo8"
        for zid in ("Z-R1", "Z-R10", "Z-R3"):
            tr = _relay_trace_for_zone(zid, ref); traces += [tr] if tr else []
            traces.append(_relay_pickup_mark(zid, ref))
        # Cabos que aparecem no STAR geral.
        for zid, cname in (("Z-R1", "Cabo1"), ("Z-R3", "Cabo8")):
            st = settings_for_zone(zid); cable = cables[cname]
            factor = float((13.8 if cname in {"Cabo1", "Cabo8"} else 6.6)) / ref
            amp = st.get("cable_ampacity_a") or cable.get("ampacity_total_a")
            if amp not in (None, "", 0):
                mk = _top_mark(f"{cname} Ampacity", float(amp)*factor, "ampacity", _MARK_AMPACITY_SPAN,
                               source=cable.get("ampacity_source") or "ajuste do usuário")
                if mk: traces.append(mk)
            cx, cy = _cable_damage_trace(cable, st.get("cable_k_adiabatic"), 1e5)
            if cx: traces.append({"name": f"{cname} - P", "x": [x*factor for x in cx], "y": cy, "mode":"lines", "kind":"cable"})
        for args in (("Barra3", ref, "max", "3f", "Barra3 - 3P", "fault_max"), ("Barra4", ref, "max", "3f", "Barra4 - 3P", "fault_max")):
            ft = _fault_reference_trace(*args); traces += [ft] if ft else []
        gen = next(iter(gens.values()), None)
        if gen:
            gx, gy, gsource = _generator_damage_trace(gen)
            if gx:
                traces.append({"name": f"{gen['name']} — dano do estator", "x": gx, "y": gy, "mode": "lines", "kind": "generator_damage"})
                notes.append(f"Dano do estator do gerador: 4 pontos ETAP ({gsource}).")
            i2t = gen.get("short_circuit_i2t_pu")
            fla = gen.get("fla_a")
            if i2t and fla:
                try:
                    row = get_bus_short_circuit(gen.get("bus", "Barra1"), "max")
                    sel = select_max_phase_fault(row)
                    if sel.get("available"):
                        fault_a = float(sel["ka"]) * 1000.0
                        mult = fault_a / float(fla)
                        t_limit = float(i2t) / (mult * mult)
                        notes.append(
                            f"Capacidade térmica de curto trifásico no terminal (ANSI/IEEE C50.13, I²t≤{i2t:.0f}): "
                            f"com a falta MAX calculada no terminal ({mult:.2f}× FLA), o gerador resiste até "
                            f"{t_limit:.3f} s — confira contra o tempo real de eliminação da falta."
                        )
                except Exception:
                    pass
        notes.append("Vista geral em base 13,8 kV. Somente ajustes salvos + resultados do estudo elétrico.")
    else:
        raise KeyError(view)

    traces = [t for t in traces if t]

    # V22: escala travada para espelhar visualmente as janelas do ETAP e
    # permitir comparação direta curva-a-curva.
    etap_axis = {
        "mb0": {
            "title": "Amps X 10   Barra5 (Nom. kV=6,6, Plot Ref. kV=6,6)",
            "bus_label": "Barra5",
            "display_multiplier": 10.0,
            "x_range": [5.0, 1.0e5],
        },
        "mb6": {
            "title": "Amps X 100   Barra3 (Nom. kV=13,8, Plot Ref. kV=13,8)",
            "bus_label": "Barra3",
            "display_multiplier": 100.0,
            "x_range": [50.0, 1.0e6],
        },
        "t1": {
            "title": "Amps X 10   Barra3 (Nom. kV=13,8, Plot Ref. kV=13,8)",
            "bus_label": "Barra3",
            "display_multiplier": 10.0,
            "x_range": [5.0, 1.0e5],
        },
        "general": {
            "title": "Amps X 100   Barra3 (Nom. kV=13,8, Plot Ref. kV=13,8)",
            "bus_label": "Barra3",
            "display_multiplier": 100.0,
            "x_range": [50.0, 1.0e6],
        },
    }[view]
    y_ticks = [0.01, 0.03, 0.05, 0.1, 0.3, 0.5, 1, 3, 5, 10, 30, 50, 100, 300, 500, 1000]
    xmul = etap_axis["display_multiplier"]
    # Rótulos do eixo de corrente exatamente como o Star imprime (inclui
    # o 500).
    x_tick_text = ["0,5", "1", "3", "5", "10", "30", "50", "100", "300", "500", "1K", "3K", "5K", "10K"]
    x_tick_vals = [0.5*xmul, 1*xmul, 3*xmul, 5*xmul, 10*xmul, 30*xmul, 50*xmul, 100*xmul, 300*xmul, 500*xmul, 1e3*xmul, 3e3*xmul, 5e3*xmul, 1e4*xmul]
    y_tick_text = ["0,01", "0,03", "0,05", "0,1", "0,3", "0,5", "1", "3", "5", "10", "30", "50", "100", "300", "500", "1K"]
    notes.insert(0, f"Escala ETAP fixa: {etap_axis['title']}")
    return {"view": view, "title": title, "subtitle": subtitle, "reference_kv": ref,
            "traces": traces, "notes": notes, "x_range": etap_axis["x_range"], "y_range": [0.01, 1000.0],
            "etap_axis": {"title": etap_axis["title"], "bus_label": etap_axis["bus_label"], "display_multiplier": xmul,
                          "x_tick_vals": x_tick_vals, "x_tick_text": x_tick_text,
                          "y_tick_vals": y_ticks, "y_tick_text": y_tick_text},
            "single_line": _view_single_line(view),
            "live_zones": [
                {
                    "id": zid,
                    "relay": zones[zid]["relay"],
                    "title": zones[zid]["title"],
                    "kv": zones[zid]["kv"],
                    "settings": {k: settings_for_zone(zid).get(k) for k in TCC_LIVE_FIELDS},
                }
                for zid in _VIEW_ZONES.get(view, [])
            ],
            "curve_options": [{"key": k, "label": v["label"]} for k, v in CURVES.items()],
            "sheet": _sheet_block(view),
            "study_status": {"powerflow_ok": bool(pf.get("ok")), "sc_max_ok": bool(scmax.get("ok")), "sc_min_ok": bool(scmin.get("ok"))},
            "electrical_cache": solver_cache_status(),
            "study_chain": ["Modelo físico", "Fluxo de potência", "Curto-circuito IEC 60909", "Ajustes 50/51", "Coordenograma"]}

def manual_51(zone_id: str, current_a=None, mode="phase") -> dict:
    """Objetivo: mostrar o cálculo do estágio inverso, passo a passo.

        corrente primária  ->  ÷ relação do TC  ->  múltiplo M
        ->  t(I) pela curva  ->  comparação com as outras curvas

    Material de apoio para aula: o mesmo número aparece no primário e
    no secundário do TC, para separar o que é grandeza do sistema do
    que é o relé enxerga. Sem corrente informada usa o LRC do motor,
    ou 2 × pickup, e diz qual dos dois usou.
    """
    _, zones, motors, cables, _, _, _, _ = _ctx()
    if zone_id not in zones:
        raise KeyError(zone_id)
    mode = "neutral" if mode == "neutral" else "phase"
    zone = zones[zone_id]; settings = settings_for_zone(zone_id)
    motor = motors.get(zone.get("motor")); cable = cables.get(zone.get("cable")); p = _prefix(mode)
    pickup = settings.get(f"{p}_stage1_pickup_a")
    if not pickup:
        return {"zone": zone, "settings": settings, "mode": mode, "error": "Pickup do estágio inverso não parametrizado.", "checks": analyze_zone(zone_id, settings, mode)}
    pickup = float(pickup); time_setting = float(settings.get(f"{p}_time_setting") or 0); curve_key = settings.get(f"{p}_curve", "IEC_VI"); cfg = CURVES[curve_key]
    ctp = float(settings.get("ct_primary_a") or 1.0); cts = float(settings.get("ct_secondary_a") or 1.0); ct_ratio = ctp / cts
    if current_a in (None, ""):
        if motor and mode == "phase":
            current = float(motor["locked_rotor_current_a"]); current_source = "LRC do motor"
        else:
            current = 2.0 * pickup; current_source = "2 × pickup"
    else:
        current = float(current_a); current_source = "corrente informada"
    i_secondary = current / ct_ratio; pickup_secondary = pickup / ct_ratio; m_primary = current / pickup; m_secondary = i_secondary / pickup_secondary
    time_s = relay_time(current, pickup, time_setting, curve_key)
    comparison = []
    x_min = max(pickup * 1.015, 1.0); max_hint = max(current * 2.0, pickup * 20.0)
    for key, ccfg in CURVES.items():
        # Se o mesmo valor de ajuste não está na faixa do relé/curva,
        # ainda desenhamos a família para comparação matemática e
        # marcamos isso no texto.
        xs, ys = [], []
        for i in range(180):
            x = x_min * (max_hint / x_min) ** (i / 179)
            t = relay_time(x, pickup, time_setting, key)
            if t is not None and 0.01 <= t <= 1000:
                xs.append(x); ys.append(t)
        comparison.append({"curve": key, "label": ccfg["label"], "x": xs, "y": ys})
    family_symbol = "TMS" if cfg["family"] == "IEC" else "TD"
    symbolic = "t = TMS·K/(M^α−1)" if cfg["family"] == "IEC" else "t = TD·(K/(M^α−1)+L)"
    # Acima de 20 x Is a característica inversa não é mais definida pela
    # norma: o tempo fica congelado em t(M = 20), como o ETAP desenha.
    m_used = min(m_primary, CURVE_MULTIPLE_LIMIT)
    clamped = m_primary > CURVE_MULTIPLE_LIMIT
    substitution = f"t = {time_setting:.4g} · ({cfg['k']}/({m_used:.4g}^{cfg['alpha']} - 1) + {cfg['L']})"
    if clamped:
        substitution += f"   [M = {m_primary:.4g} limitado a {CURVE_MULTIPLE_LIMIT:.0f} × Is — IEC 60255-151]"
    return {"multiple_limit": CURVE_MULTIPLE_LIMIT, "multiple_clamped": clamped, "zone": zone, "settings": settings, "relay": RELAY_LIBRARY[settings["relay_model"]], "mode": mode, "motor": motor, "cable": cable, "current_a": current, "current_source": current_source, "ct_ratio": ct_ratio, "current_secondary_a": i_secondary, "pickup_secondary_a": pickup_secondary, "multiple_primary": m_primary, "multiple_secondary": m_secondary, "time_s": time_s, "curve": {"key": curve_key, **cfg}, "comparison": comparison, "equation": {"symbolic": symbolic, "substitution": substitution, "time_setting_symbol": family_symbol}, "checks": analyze_zone(zone_id, settings, mode)}


def zones_payload():
    """Objetivo: as zonas com tudo que a tela precisa, numa resposta.

    Cada zona sai com o equipamento associado já resolvido (motor, cabo,
    transformador, ficha do relé) e com os ajustes efetivos. O front-end
    não precisa cruzar nomes nem fazer uma segunda chamada por zona.
    """
    model, _, motors, cables, trafos, _, _, _ = _ctx()
    output = []
    for zone in model["zones"]:
        item = dict(zone)
        item["motor_data"] = motors.get(zone.get("motor")); item["cable_data"] = cables.get(zone.get("cable")); item["transformer_data"] = trafos.get(zone.get("transformer"))
        item["relay_data"] = RELAY_LIBRARY[zone["relay_model"]]
        item["settings"] = settings_for_zone(zone["id"])
        output.append(item)
    return output


def paths_payload():
    """Objetivo: os caminhos de coordenação cadastrados.
    """
    model, _, _, _, _, _, _, _ = _ctx()
    return model.get("coordination_paths", [])


def relay_library_payload():
    """Objetivo: curvas e modelos de relé disponíveis, para a tela.

    É a biblioteca de referência: as constantes ``k``, ``α`` e ``L``
    de cada curva normalizada e as faixas de ajuste de cada relé.
    """
    return {"curves": CURVES, "relays": RELAY_LIBRARY}


# ======================================================================
# BLOCO 6 — VERIFICAÇÃO DE COORDENAÇÃO EM CASCATA
# O especialista aqui VERIFICA, não ajusta.
# ======================================================================
# O especialista aqui VERIFICA, não ajusta. As curvas de referência —
# partida do motor, dano térmico do motor e inrush do transformador —
# são dado fixo: elas são as paredes entre as quais a curva do relé
# precisa caber, nunca objeto de ajuste.
#
# Um "caso" é um prefixo do caminho de coordenação, do motor para a
# fonte: caso 1 = os dois primeiros relés, caso 2 = três, caso 3 =
# quatro.
#
# Relés que comandam o MESMO disjuntor formam um estágio só. No T1 o
# Relé12 não tem disjuntor próprio: ele abre o DJ2, junto com o Relé10.
# Entre esses dois não existe seletividade a verificar (é o mesmo
# disjuntor), então a envoltória do estágio é o menor tempo dos dois em
# cada corrente, e o CTI é cobrado do estágio de jusante para o de
# montante.
#
# A banda tem dois lados com alcances diferentes: piso  (ficar ACIMA da
# partida/inrush) — vale para TODOS os relés do caso, porque todos
# enxergam a corrente de partida do motor; teto  (ficar ABAIXO do dano
# do motor) — vale só para a proteção principal e a retaguarda imediata.
# Relés mais a montante podem passar por cima: não é função deles
# proteger aquele motor.

BAND_MARGIN_S = 0.30   # folga mínima entre o relé e a partida
ASYM_LRC_FACTOR = 1.6  # assimétrica de partida (offset CC)


def _br(value, decimals=0) -> str:
    """Número no formato brasileiro (1.003,7), para o relatório.

    Sem isso o f-string do Python escreve 1,004 A, que em português se
    lê como 1,004 — justamente o contrário do valor.
    """
    txt = f"{float(value):,.{int(decimals)}f}"
    return txt.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")


def _effective_breaker(zone_id: str, ordered_ids: list, zones: dict) -> str | None:
    """Disjuntor que o relé realmente abre.

    Relé sem disjuntor próprio no modelo (caso do Relé12) abre o
    primeiro disjuntor que existir subindo o caminho.
    """
    try:
        start = ordered_ids.index(zone_id)
    except ValueError:
        return zones.get(zone_id, {}).get("breaker")
    for zid in ordered_ids[start:]:
        breaker = zones[zid].get("breaker")
        if breaker:
            return breaker
    return None


def _case_stages(case_ids: list, path_ids: list, zones: dict) -> list:
    """Agrupa as zonas por disjuntor, de jusante para montante."""
    stages = []
    for zid in case_ids:
        breaker = _effective_breaker(zid, path_ids, zones)
        if stages and breaker is not None and stages[-1]["breaker"] == breaker:
            stages[-1]["zones"].append(zid)
        else:
            stages.append({"breaker": breaker, "zones": [zid]})
    for stage in stages:
        stage["relays"] = [zones[z]["relay"] for z in stage["zones"]]
        stage["label"] = " + ".join(stage["relays"]) + (f" ({stage['breaker']})" if stage["breaker"] else "")
    return stages


def _stage_time(stage: dict, i_ref_a: float, ref_kv: float, zones: dict, cache: dict) -> dict:
    """Tempo da envoltória: o menor entre os relés do mesmo CB."""
    best = None
    for zid in stage["zones"]:
        settings = cache[zid]
        i_local = _shift_current(i_ref_a, ref_kv, float(zones[zid]["kv"]))
        time_s, stage_name = relay_operating_time(i_local, settings, "phase")
        if time_s is None:
            continue
        if best is None or float(time_s) < best["time_s"]:
            opening = settings.get("breaker_opening_time_s")
            best = {
                "time_s": float(time_s), "relay": zones[zid]["relay"], "zone": zid,
                "stage": stage_name, "i_local_a": i_local,
                "opening_s": 0.0 if opening in (None, "", 0) else float(opening),
            }
    return best or {"time_s": None, "relay": None, "zone": None, "stage": None}


def _relay_time_ref(zone_id: str, i_ref_a: float, ref_kv: float, zones: dict, cache: dict):
    """Tempo de um relé para uma corrente dada na base de referência."""
    i_local = _shift_current(i_ref_a, ref_kv, float(zones[zone_id]["kv"]))
    time_s, _stage = relay_operating_time(i_local, cache[zone_id], "phase")
    return None if time_s is None else float(time_s)


def _check_cti(stage_down: dict, stage_up: dict, ref_kv: float, zones: dict, cache: dict) -> list:
    """CTI entre dois estágios, avaliado na falta máxima e na mínima.

    A falta usada é a do barramento protegido pelo estágio de jusante —
    é o curto que ele tem que limpar e que o de montante só deve
    enxergar como retaguarda. Reprovar em qualquer um dos dois extremos
    já é reprovação.
    """
    _, _, _, _, _, _, buses, _ = _ctx()
    bus = zones[stage_down["zones"][0]]["bus"]
    bus_kv = float(buses[bus]["kv"])
    required = float(cache[stage_down["zones"][0]].get("coordination_margin_s") or CTI_DEFAULT_S)
    out = []
    for case, selector, label in (("max", select_max_phase_fault, "máxima"),
                                  ("min", select_critical_phase_min, "mínima")):
        base = {"id": f"CTI-{stage_down['breaker'] or stage_down['relays'][0]}-{case}",
                "scope": "cti", "title": f"CTI {stage_down['label']} → {stage_up['label']} · falta {label}"}
        try:
            row = get_bus_short_circuit(bus, case)
            sel = selector(row)
        except Exception:
            sel = {"available": False}
        if not sel.get("available"):
            out.append({**base, "status": "warn",
                        "text": f"Curto {case.upper()} em {bus} indisponível; par não verificado."})
            continue
        i_ref = _shift_current(float(sel["ka"]) * 1000.0, bus_kv, ref_kv)
        down = _stage_time(stage_down, i_ref, ref_kv, zones, cache)
        up = _stage_time(stage_up, i_ref, ref_kv, zones, cache)
        detail = f"Falta {sel['fault']} em {bus} = {_br(sel['ka'], 3)} kA ({_br(i_ref)} A na base {ref_kv:g} kV)."
        if down["time_s"] is None:
            out.append({**base, "status": "bad", "at_current_a": i_ref,
                        "text": f"{detail} O estágio de jusante não atua nessa corrente — a falta ficaria para a retaguarda."})
            continue
        if up["time_s"] is None:
            out.append({**base, "status": "ok", "at_current_a": i_ref, "margin_s": None,
                        "text": f"{detail} Jusante ({down['relay']}) abre em {_br(down['time_s'], 3)} s e o de montante não atua: seletivo."})
            continue
        clearing = down["time_s"] + down.get("opening_s", 0.0)
        margin = up["time_s"] - clearing
        opening_txt = "" if not down.get("opening_s") else f" + {_br(down['opening_s'], 3)} s de abertura"
        out.append({**base,
                    "status": "ok" if margin >= required else "bad",
                    "margin_s": margin, "required_s": required, "at_current_a": i_ref,
                    "text": (f"{detail} {down['relay']} em {_br(down['time_s'], 3)} s{opening_txt}, "
                             f"{up['relay']} em {_br(up['time_s'], 3)} s → folga {_br(margin, 3)} s "
                             f"(mínimo {_br(required, 2)} s).")})
    return out


def _check_start_floor(zone_id: str, motor: dict, ref_kv: float, zones: dict, cache: dict) -> dict:
    """Piso: a curva do relé tem que passar acima da partida do motor.

    Percorre o corpo da envoltória de partida (sem a cauda assimétrica,
    que é tratada pelo pickup do 50) e guarda a MENOR folga e a corrente
    em que ela acontece — que é o que o engenheiro precisa saber, não um
    "ok" genérico.
    """
    relay = zones[zone_id]["relay"]
    base = {"id": f"PISO-PARTIDA-{relay}", "scope": "piso",
            "title": f"{relay} acima da partida de {motor['name']}"}
    env = _motor_start_envelope(motor, ref_kv)
    if not env:
        return {**base, "status": "warn", "text": "Tempo de aceleração não informado; piso não verificado."}
    required = BAND_MARGIN_S
    body = env["x"][:env.get("body_points", len(env["x"]))]
    times = env["y"][:env.get("body_points", len(env["y"]))]
    worst = None
    for i_ref, t_start in zip(body, times):
        if t_start >= 999:   # vertical na FLA: tempo sem sentido
            continue
        t_relay = _relay_time_ref(zone_id, i_ref, ref_kv, zones, cache)
        if t_relay is None:  # não atua aqui: folga infinita
            continue
        margin = t_relay - float(t_start)
        if worst is None or margin < worst["margin_s"]:
            worst = {"margin_s": margin, "at_current_a": i_ref, "t_relay": t_relay, "t_start": float(t_start)}
    if worst is None:
        return {**base, "status": "ok", "text": f"{relay} não atua em nenhum ponto da partida."}
    return {**base,
            "status": "ok" if worst["margin_s"] >= required else "bad",
            "margin_s": worst["margin_s"], "required_s": required, "at_current_a": worst["at_current_a"],
            "text": (f"Menor folga em {_br(worst['at_current_a'])} A: relé {_br(worst['t_relay'], 3)} s contra "
                     f"partida {_br(worst['t_start'], 3)} s → {_br(worst['margin_s'], 3)} s (mínimo {_br(required, 2)} s).")}


def _check_asym_start(zone_id: str, motor: dict, zones: dict, cache: dict) -> dict:
    """O 50 não pode ver a assimétrica de partida (offset CC)."""
    relay = zones[zone_id]["relay"]
    base = {"id": f"PISO-ASSIM-{relay}", "scope": "piso",
            "title": f"{relay} · 50 acima da partida assimétrica"}
    pickup = cache[zone_id].get("phase_stage3_pickup_a")
    if pickup in (None, "", 0):
        return {**base, "status": "warn", "text": "Sem estágio 50 ajustado."}
    factor = float(motor.get("asym_locked_rotor_factor") or ASYM_LRC_FACTOR)
    i_asym_local = _shift_current(float(motor["locked_rotor_current_a"]) * factor,
                                  float(motor["kv"]), float(zones[zone_id]["kv"]))
    ratio = float(pickup) / i_asym_local
    return {**base,
            "status": "ok" if ratio >= 1.0 else "bad",
            "margin_s": None, "at_current_a": i_asym_local,
            "text": (f"Partida assimétrica = {_br(factor, 1)} × LRC = {_br(i_asym_local)} A na base do relé; "
                     f"pickup 50 = {_br(pickup)} A ({_br(ratio, 2)}× a assimétrica).")}


def _check_inrush_floor(zone_id: str, trafo: dict, zones: dict, cache: dict) -> dict:
    """Piso do inrush: o relé não pode desarmar na energização."""
    relay = zones[zone_id]["relay"]
    base = {"id": f"PISO-INRUSH-{relay}", "scope": "piso",
            "title": f"{relay} acima do inrush de {trafo['name']}"}
    i_hv = trafo.get("inrush_primary_a")
    t_in = trafo.get("inrush_time_s")
    if i_hv in (None, "", 0) or t_in in (None, ""):
        return {**base, "status": "warn", "text": "Ponto de inrush não cadastrado."}
    i_local = _shift_current(float(i_hv), float(trafo["vn_hv_kv"]), float(zones[zone_id]["kv"]))
    time_s, _stage = relay_operating_time(i_local, cache[zone_id], "phase")
    if time_s is None:
        return {**base, "status": "ok", "at_current_a": i_local,
                "text": f"Inrush {_br(i_hv)} A / {_br(t_in, 4)} s: o relé não atua nessa corrente."}
    margin = float(time_s) - float(t_in)
    return {**base,
            "status": "ok" if margin > 0 else "bad",
            "margin_s": margin, "at_current_a": i_local,
            "text": (f"Inrush {_br(i_hv)} A por {_br(t_in, 4)} s; relé atuaria em {_br(time_s, 4)} s "
                     f"→ folga {_br(margin, 4)} s.")}


def _check_damage_ceiling(zone_id: str, motor: dict, ref_kv: float, zones: dict, cache: dict, role: str) -> dict:
    """Teto: a curva do relé passa abaixo do dano térmico do motor.

    Só é cobrado da proteção principal e da retaguarda imediata. A
    verificação para onde o dado do fabricante para: a curva exportada
    do ETAP termina no último ponto (3,6 × FLA no caso atual) e a LRC
    fica bem acima disso. Acima do último ponto NÃO há teto conhecido, e
    isso é dito no relatório em vez de ser preenchido por extrapolação
    nossa.
    """
    relay = zones[zone_id]["relay"]
    base = {"id": f"TETO-DANO-{relay}", "scope": "teto",
            "title": f"{relay} abaixo do dano de {motor['name']} ({role})"}
    dx, dy = _motor_thermal_trace(motor)
    if not dx:
        return {**base, "status": "warn",
                "text": "Curva de dano do motor não exportada; teto não verificado."}
    factor = float(motor["kv"]) / float(ref_kv)
    pts = [(x * factor, y) for x, y in zip(dx, dy)]
    worst = None
    for i_ref, t_damage in pts:
        t_relay = _relay_time_ref(zone_id, i_ref, ref_kv, zones, cache)
        if t_relay is None:
            continue
        margin = float(t_damage) - t_relay
        if worst is None or margin < worst["margin_s"]:
            worst = {"margin_s": margin, "at_current_a": i_ref, "t_relay": t_relay, "t_damage": float(t_damage)}
    last_i, last_t = pts[-1]
    lrc_ref = float(motor["locked_rotor_current_a"]) * factor
    gap = (f" Acima de {_br(last_i)} A ({_br(last_t)} s) não há ponto de dano exportado — "
           f"a região até a LRC ({_br(lrc_ref)} A) fica fora desta verificação.")
    if worst is None:
        return {**base, "status": "warn", "at_current_a": last_i,
                "text": f"{relay} não atua em nenhuma corrente com dado de dano." + gap}
    return {**base,
            "status": "ok" if worst["margin_s"] > 0 else "bad",
            "margin_s": worst["margin_s"], "at_current_a": worst["at_current_a"],
            "text": (f"Menor folga em {_br(worst['at_current_a'])} A: relé {_br(worst['t_relay'], 3)} s contra "
                     f"dano {_br(worst['t_damage'], 1)} s → {_br(worst['margin_s'], 2)} s." + gap)}


def _case_status(checks: list) -> str:
    if any(c["status"] == "bad" for c in checks):
        return "rejected"
    if any(c["status"] == "warn" for c in checks):
        return "pending"
    return "approved"


def review_coordination(path_id: str) -> dict:
    """Verificação em cascata de um caminho: casos 1, 2, 3...

    Caso N = os N+1 primeiros relés do caminho, do motor para a fonte.
    Cada caso repete as checagens dos anteriores e acrescenta o par
    novo, de modo que dá para ver em que profundidade a coordenação
    quebra.
    """
    model, zones, motors, _, trafos, _, _, _ = _ctx()
    path = next((p for p in model.get("coordination_paths", []) if p["id"] == path_id), None)
    if not path:
        raise KeyError(path_id)
    path_ids = list(path["zones"])
    ref_kv = float(path["reference_kv"])
    motor = motors.get(path.get("motor"))
    trafo = trafos.get((path.get("transformers") or [None])[0])
    cache = {zid: settings_for_zone(zid) for zid in path_ids}

    cases = []
    for depth in range(2, len(path_ids) + 1):
        case_ids = path_ids[:depth]
        stages = _case_stages(case_ids, path_ids, zones)
        checks = []
        # 1) Seletividade entre estágios consecutivos (relés que abrem o
        # mesmo disjuntor já foram fundidos num estágio só).
        for down, up in zip(stages, stages[1:]):
            checks += _check_cti(down, up, ref_kv, zones, cache)
        if motor:
            # 2) Piso: todo relé do caso enxerga a partida do motor.
            for zid in case_ids:
                checks.append(_check_start_floor(zid, motor, ref_kv, zones, cache))
                checks.append(_check_asym_start(zid, motor, zones, cache))
            # 3) Teto: só principal e retaguarda imediata.
            for zid, role in zip(case_ids[:2], ("proteção principal", "retaguarda imediata")):
                checks.append(_check_damage_ceiling(zid, motor, ref_kv, zones, cache, role))
        # 4) Inrush: relés do lado de alta do transformador e acima.
        if trafo:
            for zid in case_ids:
                if abs(float(zones[zid]["kv"]) - float(trafo["vn_hv_kv"])) < 1e-6:
                    checks.append(_check_inrush_floor(zid, trafo, zones, cache))
        exempt = [zones[z]["relay"] for z in case_ids[2:]]
        cases.append({
            "id": f"caso{depth - 1}",
            "depth": depth,
            "title": " + ".join(zones[z]["relay"] for z in case_ids),
            "zones": case_ids,
            "relays": [zones[z]["relay"] for z in case_ids],
            "stages": stages,
            "checks": checks,
            "status": _case_status(checks),
            "ceiling_exempt": exempt,
        })
    return {
        "path": path_id, "title": path["title"], "reference_kv": ref_kv,
        "motor": path.get("motor"), "cases": cases,
        "notes": [
            "Curvas fixas (partida, dano do motor e inrush) são referência, não objeto de ajuste.",
            "Piso (acima da partida) vale para todos os relés do caso; teto (abaixo do dano) só para a "
            "proteção principal e a retaguarda imediata.",
            "Relés que comandam o mesmo disjuntor formam um estágio só — entre eles não há seletividade a verificar.",
        ],
    }


def review_all_paths() -> dict:
    """Objetivo: verificação em cascata de todos os caminhos.

    Erro em um caminho não derruba os outros — volta como
    ``{"path": ..., "error": ..., "cases": []}``.
    """
    model, _, _, _, _, _, _, _ = _ctx()
    out = []
    for path in model.get("coordination_paths", []):
        try:
            out.append(review_coordination(path["id"]))
        except Exception as exc:
            out.append({"path": path["id"], "title": path.get("title"), "error": str(exc), "cases": []})
    return {"paths": out}
