"""Modelo físico de referência: o caso 13,8/6,6 kV descrito como dado.

SEEP — Simulador Elétrico de Estudos de Proteção.

Posição no pipeline do estudo:

    **data.py**  ->  storage.py  ->  network.py  ->  solver.py  ->
    protection.py  ->  app.py

É a base de tudo, e é só dado: listas de dicionários com barras,
geradores, transformador, cabos, motores, disjuntores, TCs e zonas de
proteção. Nenhum cálculo elétrico acontece aqui. Quem quiser entender o
sistema estudado lê este arquivo e mais nenhum.

O que o módulo oferece
----------------------
``DEFAULT_MODEL`` / ``default_model()``
    O caso de fábrica, como veio do ETAP. Cópia profunda a cada chamada,
    para ninguém alterar a referência sem querer.
``enrich_model(model)``
    Acrescenta as grandezas derivadas — impedâncias em ohm, FLA,
    corrente de rotor bloqueado, resistor de aterramento. Deriva, nunca
    copia: editar a potência de um motor propaga para a corrente nominal
    e para o TCC.
``EQUIPMENT_FIELD_SCHEMA`` / ``validate_equipment_payload()``
    Quais parâmetros o front-end pode editar, com faixa e tipo. É a
    lista que gera os formulários e também a que valida o que volta
    deles.

Procedência dos dados
---------------------
* ``Dados.xlsx``, exportação do ETAP de 30/08/2026 — barras, cabos,
  máquinas, T1, TCs e relés;
* telas do ETAP (OCR dos relés, inrush do T1, pontos térmicos dos
  motores) para os ajustes e curvas;
* folhas STAR apenas como referência visual de apresentação.

**As correntes de curto mostradas nos coordenogramas são calculadas pelo
motor de estudo, nunca copiadas das folhas STAR.** É essa escolha que
torna o resultado verificável: um número copiado não pode ser conferido,
um número calculado pode.

Rastreabilidade
---------------
Barras, cabos e relés foram renomeados para português e em sequência
(``Barra1``, ``Cabo1``, ``Relé1``). O nome original da exportação
continua registrado em ``etap_name`` e ``relay_etap_name``, para não se
perder o vínculo com a planilha e com as folhas Star — há teste que
trava esse mapeamento.

Equipamento fora de serviço
---------------------------
Geradores e motores têm o campo ``in_service``. Desligado, o equipamento
não entra na rede: é assim que a aula demonstra o efeito de uma fonte a
mais sobre o nível de curto-circuito.
"""
from __future__ import annotations

import copy
import math

FREQUENCY_HZ = 60.0
CASE_ID = "SEEP-V01"
CASE_NAME = "Caso: 13,8/6,6kV"

# Identificação do build, mostrada no rodapé da barra lateral. Serve
# para saber de olho qual pasta está rodando: com duas cópias do projeto
# na máquina, a tela é idêntica e não dá para distinguir uma correção
# aplicada de uma pasta antiga. Bumpar a cada entrega.
BUILD_TAG = "build 30.5 · 05/10/2026"

_BUSES = [
    # V30: barras renumeradas em sequência (1 a 6). O nome usado na
    # exportação do ETAP fica registrado em "etap_name" para não se
    # perder a rastreabilidade com o Dados.xlsx e com as folhas Star.
    {"name": "Barra1", "kv": 13.8, "role": "terminal do gerador GE1", "etap_name": 'Bus01'},
    {"name": "Barra2", "kv": 13.8, "role": "terminal do gerador GE2", "etap_name": None},
    {"name": "Barra3", "kv": 13.8, "role": "barra principal 13,8 kV", "etap_name": 'Bus1'},
    {"name": "Barra4", "kv": 13.8, "role": "terminal M-B-6", "etap_name": 'Bus10'},
    {"name": "Barra5", "kv": 6.6, "role": "barra principal 6,6 kV", "etap_name": 'Bus2'},
    {"name": "Barra6", "kv": 6.6, "role": "terminal M-B-0", "etap_name": 'Bus4'},
    # V30: dois terminais novos de 6,6 kV para os motores espelhados do
    # M-B-0. Não existem no ETAP; servem para demonstrar em aula o
    # efeito de entrar carga girante na barra de 6,6 kV sobre o nível de
    # curto-circuito MAX.
    {"name": "Barra7", "kv": 6.6, "role": "terminal M-B-1", "etap_name": None},
    {"name": "Barra8", "kv": 6.6, "role": "terminal M-B-2", "etap_name": None},
]

_GENERATORS = [
    {
        "name": "GE1", "bus": "Barra1", "type": "Steam Turbo", "in_service": True,
        "p_rated_mw": 33.0, "sn_mva": 41.25, "kv": 13.8, "rpm": 1800,
        "pf": 0.80, "efficiency_percent": 95.0, "poles": 4,
        "xdss_pu": 0.15, "x_over_r": 15.0,
        "x0_pu": 0.07, "x0_over_r0": 7.0,
        "x2_pu": 0.18, "x2_over_r2": 9.0,
        "model_type": "Subtransient", "connection": "Y",
        "neutral_current_a": 4000.0,
        # Curva de dano do estator (ETAP: Protection > Thermal
        # Capability > Stator Damage Curve, "Multiples of FLA",
        # 31/08/2026) + capacidade térmica de curto trifásico no
        # terminal ANSI/IEEE C50.13 (I²t ≤ 30, em pu²·s de FLA — valor
        # padrão da norma para geradores síncronos).
        "stator_damage_points": [(120.0, 1.15), (60.0, 1.27), (30.0, 1.5), (10.0, 2.18)],
        "stator_damage_points_source": "ETAP Stator Damage Curve Points 31/08/2026",
        "short_circuit_i2t_pu": 30.0, "short_circuit_i2t_source": "ANSI/IEEE C50.13 · ETAP Thermal Capability Plot I²t",
        "source": "Dados.xlsx · Synchronous Generator",
    },
    {
        # V30: segundo gerador, espelho do GE1. Serve para demonstrar em
        # aula o efeito de uma fonte a mais sobre o nível de
        # curto-circuito: com os dois em serviço a contribuição para a
        # falta soma, e o ajuste dos relés precisa ser verificado nas
        # duas condições.
        "name": "GE2", "bus": "Barra2", "type": "Steam Turbo", "in_service": True,
        "p_rated_mw": 33.0, "sn_mva": 41.25, "kv": 13.8, "rpm": 1800,
        "pf": 0.80, "efficiency_percent": 95.0, "poles": 4,
        "xdss_pu": 0.15, "x_over_r": 15.0,
        "x0_pu": 0.07, "x0_over_r0": 7.0,
        "x2_pu": 0.18, "x2_over_r2": 9.0,
        "model_type": "Subtransient", "connection": "Y",
        "neutral_current_a": 4000.0,
        "stator_damage_points": [(120.0, 1.15), (60.0, 1.27), (30.0, 1.5), (10.0, 2.18)],
        "stator_damage_points_source": "espelhado do GE1",
        "short_circuit_i2t_pu": 30.0, "short_circuit_i2t_source": "ANSI/IEEE C50.13",
        "source": "V30 · máquina espelhada do GE1, sem correspondente no ETAP",
    },
]

_TRANSFORMERS = [
    {
        "name": "T1", "hv_bus": "Barra3", "lv_bus": "Barra5",
        "sn_mva": 11.0, "vn_hv_kv": 13.8, "vn_lv_kv": 6.6,
        "vk_percent": 8.0, "x_over_r": 18.6,
        "vk0_percent": 8.0, "x0_over_r0": 18.6,
        "vector_group": "Dyn", "shift_degree": 30.0,
        "hv_connection": "D", "lv_connection": "Y", "lv_grounding": "Solid",
        "temp_rise_c": 65.0,
        "fault_frequency": "Both", "curve_shift": True,
        # ETAP: Magnetizing Inrush = Equation, multiplier 8, one cycle =
        # 0.0167 s.
        "inrush_pu": 8.0, "inrush_time_s": 0.0167, "inrush_cycles": 1,
        "inrush_primary_a": 3681.7, "inrush_rms_a": 2603.3,
        # Pontos reais de T1 Withstand ainda não foram exportados. T1 é
        # Categoria III da ANSI/IEEE C57.109 (5.001–30.000 kVA
        # trifásico; 11 MVA = 11.000 kVA). A curva de dano (duas partes:
        # mecânica + térmica) é calculada em core/protection.py a partir
        # do curto-circuito MAX já calculado pelo próprio estudo
        # (Barra3/Barra5), não copiada do ETAP — mesmo princípio já
        # usado no resto do app (ver README).
        "damage_category": "III", "damage_i2t_thermal": 1250.0,
        "damage_points_pu": [], "damage_short_time_s": 2.0,
        "etap_thermal_i2t": 1250.0, "etap_thermal_i2t_units": "não confirmadas",
        "source": "Dados.xlsx + ETAP Transformer Editor > Protection",
    },
]

_CABLES = [
    {
        "name": "Cabo1", "etap_name": 'Cable1', "from_bus": "Barra1", "to_bus": "Barra3",
        "parallel": 7, "phase": 3, "conductor": "Copper", "insulation": "XLPE",
        "library": "Heesung", "size_mm2": 400.0, "length_m": 150.0,
        "r1_pf_ohm_per_km": 0.064, "x1_pf_ohm_per_km": 0.102,
        "r0_pf_ohm_per_km": 0.103, "x0_pf_ohm_per_km": 0.259,
        "r1_sc20_ohm_per_1000ft": 0.0154187, "x1_sc_ohm_per_1000ft": 0.0310896,
        "r0_sc20_ohm_per_1000ft": 0.0245145, "x0_sc_ohm_per_1000ft": 0.0789676,
        "ampacity_total_a": None, "k_adiabatic": 143.0,
        "thermal_plot_tmin_s": 0.01, "thermal_plot_tmax_s": 10.0,
        "source": "Dados.xlsx · Cable",
    },
    {
        "name": "Cabo3", "etap_name": None, "from_bus": "Barra2", "to_bus": "Barra3",
        "parallel": 7, "phase": 3, "conductor": "Copper", "insulation": "XLPE",
        "library": "Heesung", "size_mm2": 400.0, "length_m": 150.0,
        "r1_pf_ohm_per_km": 0.064, "x1_pf_ohm_per_km": 0.102,
        "r0_pf_ohm_per_km": 0.103, "x0_pf_ohm_per_km": 0.259,
        "r1_sc20_ohm_per_1000ft": 0.0154187, "x1_sc_ohm_per_1000ft": 0.0310896,
        "r0_sc20_ohm_per_1000ft": 0.0245145, "x0_sc_ohm_per_1000ft": 0.0789676,
        "ampacity_total_a": None, "k_adiabatic": 143.0,
        "thermal_plot_tmin_s": 0.01, "thermal_plot_tmax_s": 10.0,
        "source": "V30 · espelho do Cabo1 para o ramal do GE2",
    },
    {
        "name": "Cabo8", "etap_name": 'Cable8', "from_bus": "Barra3", "to_bus": "Barra4",
        "parallel": 3, "phase": 3, "conductor": "Copper", "insulation": "XLPE",
        "library": "Heesung", "size_mm2": 25.0, "length_m": 150.0,
        "r1_pf_ohm_per_km": 0.927, "x1_pf_ohm_per_km": 0.141,
        "r0_pf_ohm_per_km": 1.474, "x0_pf_ohm_per_km": 0.358,
        "r1_sc20_ohm_per_1000ft": 0.2215990, "x1_sc_ohm_per_1000ft": 0.0429768,
        "r0_sc20_ohm_per_1000ft": 0.3523352, "x0_sc_ohm_per_1000ft": 0.1091611,
        "ampacity_total_a": None, "k_adiabatic": 143.0,
        "thermal_k2s2_ka2s": 115.03, "thermal_theta_initial_c": 90.0, "thermal_theta_final_c": 250.0,
        "thermal_plot_parallel": 3, "thermal_standard": "ICEA P-32-382",
        "thermal_plot_tmin_s": 0.01, "thermal_plot_tmax_s": 10.0,
        "etap_sc_reference": {"3f_ka": 14.99, "lg_ka": 4.144, "ll_ka": 11.99, "llg_ka": 2.325},
        "source": "Dados.xlsx + ETAP Cabo8 Protection 30/08/2026",
    },
    {
        "name": "Cabo2", "etap_name": 'Cable2', "from_bus": "Barra5", "to_bus": "Barra6",
        "parallel": 1, "phase": 3, "conductor": "Copper", "insulation": "XLPE",
        "library": "Heesung", "size_mm2": 16.0, "length_m": 50.0,
        "r1_pf_ohm_per_km": 1.470, "x1_pf_ohm_per_km": 0.151,
        "r0_pf_ohm_per_km": 2.337, "x0_pf_ohm_per_km": 0.384,
        "r1_sc20_ohm_per_1000ft": 0.3514029, "x1_sc_ohm_per_1000ft": 0.0460248,
        "r0_sc20_ohm_per_1000ft": 0.5587307, "x0_sc_ohm_per_1000ft": 0.1169030,
        # Ampacidade lida do STAR75 (marca "Cabo2 Ampacity"): o traço
        # vertical do ETAP fica em 81,3 A na base 6,6 kV. A calibração
        # do eixo foi conferida contra dois pontos conhecidos do mesmo
        # desenho (pickup 230 A e 50P 7760 A), com erro < 0,15 %.
        # Substituir pelo valor da biblioteca quando exportado.
        "ampacity_total_a": 81.3, "ampacity_source": "STAR75 · marca Cabo2 Ampacity (08-31-2026)",
        "k_adiabatic": 143.0,
        "thermal_k2s2_ka2s": 5.23, "thermal_theta_initial_c": 90.0, "thermal_theta_final_c": 250.0,
        "thermal_plot_parallel": 1, "thermal_standard": "ICEA P-32-382",
        "thermal_plot_tmin_s": 0.01, "thermal_plot_tmax_s": 10.0,
        "etap_sc_reference": {"3f_ka": 10.33, "lg_ka": 10.96, "ll_ka": 8.737, "llg_ka": 12.28},
        "source": "Dados.xlsx + ETAP Cabo2 Protection 30/08/2026",
    },
    # V30: alimentadores dos motores novos da barra de 6,6 kV. Geometria
    # e impedâncias copiadas do Cabo2 — são ramais idênticos ao do
    # M-B-0. Sem "etap_sc_reference": não há folha ETAP correspondente
    # para comparar.
    {
        "name": "Cabo4", "etap_name": None, "from_bus": "Barra5", "to_bus": "Barra7",
        "parallel": 1, "phase": 3, "conductor": "Copper", "insulation": "XLPE",
        "library": "Heesung", "size_mm2": 16.0, "length_m": 50.0,
        "r1_pf_ohm_per_km": 1.470, "x1_pf_ohm_per_km": 0.151,
        "r0_pf_ohm_per_km": 2.337, "x0_pf_ohm_per_km": 0.384,
        "r1_sc20_ohm_per_1000ft": 0.3514029, "x1_sc_ohm_per_1000ft": 0.0460248,
        "r0_sc20_ohm_per_1000ft": 0.5587307, "x0_sc_ohm_per_1000ft": 0.1169030,
        "ampacity_total_a": 81.3, "ampacity_source": "espelhado do Cabo2 (mesma bitola e arranjo)",
        "k_adiabatic": 143.0,
        "thermal_k2s2_ka2s": 5.23, "thermal_theta_initial_c": 90.0, "thermal_theta_final_c": 250.0,
        "thermal_plot_parallel": 1, "thermal_standard": "ICEA P-32-382",
        "thermal_plot_tmin_s": 0.01, "thermal_plot_tmax_s": 10.0,
        "source": "V30 · espelho do Cabo2 para o ramal do M-B-1",
    },
    {
        "name": "Cabo5", "etap_name": None, "from_bus": "Barra5", "to_bus": "Barra8",
        "parallel": 1, "phase": 3, "conductor": "Copper", "insulation": "XLPE",
        "library": "Heesung", "size_mm2": 16.0, "length_m": 50.0,
        "r1_pf_ohm_per_km": 1.470, "x1_pf_ohm_per_km": 0.151,
        "r0_pf_ohm_per_km": 2.337, "x0_pf_ohm_per_km": 0.384,
        "r1_sc20_ohm_per_1000ft": 0.3514029, "x1_sc_ohm_per_1000ft": 0.0460248,
        "r0_sc20_ohm_per_1000ft": 0.5587307, "x0_sc_ohm_per_1000ft": 0.1169030,
        "ampacity_total_a": 81.3, "ampacity_source": "espelhado do Cabo2 (mesma bitola e arranjo)",
        "k_adiabatic": 143.0,
        "thermal_k2s2_ka2s": 5.23, "thermal_theta_initial_c": 90.0, "thermal_theta_final_c": 250.0,
        "thermal_plot_parallel": 1, "thermal_standard": "ICEA P-32-382",
        "thermal_plot_tmin_s": 0.01, "thermal_plot_tmax_s": 10.0,
        "source": "V30 · espelho do Cabo2 para o ramal do M-B-2",
    },
]

_MOTORS = [
    {
        "name": "M-B-6", "bus": "Barra4", "in_service": True, "kw": 6000.0, "kv": 13.8,
        "kva": 6798.75, "amp": 284.44, "pf": 0.9323,
        "efficiency_percent": 94.7, "study_loading_percent": 90.0,
        "r_percent": 1.35, "x_percent": 15.33, "rx": 0.09,
        "lrc_percent": 650.0, "start_pf_percent": 8.7,
        "x0_percent": 15.38, "x0_over_r0": 31.428,
        "x2_percent": 15.38, "x2_over_r2": 31.428,
        "connection": "Y", "grounding": "Open",
        "start_time_s": 2.0, "start_time_reference_voltage_percent": 100.0,
        "stall_hot_s": 12.0, "stall_cold_s": 40.0,
        # Hot Start habilitado (mesmo tratamento do M-B-0).
        "stall_hot_enabled": True, "stall_cold_enabled": False,
        "thermal_curve_enabled": True,
        # ETAP Thermal Curve Points > Stator-Hot (Multiples of FLA),
        # 31/08/2026. Formato interno: (múltiplo da FLA, tempo [s]).
        # Stator-Cold está vazio/0 no ETAP.
        "thermal_points": [(1.55, 1000.0), (1.70, 500.0), (1.90, 300.0),
                           (2.40, 150.0), (3.00, 87.0), (3.60, 60.0)],
        "thermal_points_source": "ETAP Stator-Hot Points 31/08/2026",
        "asym_locked_rotor_factor": 1.6,
        "source": "Dados.xlsx + telas ETAP + Thermal Curve Points 31/08/2026",
    },
    {
        "name": "M-B-0", "bus": "Barra6", "in_service": True, "kw": 1600.0, "kv": 6.6,
        "kva": 1765.03, "amp": 154.40, "pf": 0.9268,
        "efficiency_percent": 97.8, "study_loading_percent": 90.0,
        "r_percent": 1.94, "x_percent": 15.26, "rx": 0.13,
        "lrc_percent": 650.0, "start_pf_percent": 12.6,
        "x0_percent": 15.38, "x0_over_r0": 31.428,
        "x2_percent": 15.38, "x2_over_r2": 31.428,
        "connection": "Y", "grounding": "Open",
        # Tela ETAP mais recente: 100% Vt = 1 s. Os campos Hot/Cold
        # estão desmarcados.
        "start_time_s": 1.0, "start_time_reference_voltage_percent": 100.0,
        "stall_hot_s": 10.0, "stall_cold_s": 30.0,
        # ETAP > M-B-0 > Protection: Hot Start marcado (10 s); Cold
        # Start desmarcado.
        "stall_hot_enabled": True, "stall_cold_enabled": False,
        "thermal_curve_enabled": True,
        # ETAP Thermal Curve Points > Stator-Hot (Multiples of FLA),
        # 31/08/2026. Formato interno: (múltiplo da FLA, tempo [s]).
        # Stator-Cold está vazio/0 no ETAP.
        "thermal_points": [(1.55, 1000.0), (1.70, 500.0), (1.90, 300.0),
                           (2.40, 150.0), (3.00, 87.0), (3.60, 60.0)],
        "thermal_points_source": "ETAP Stator-Hot Points 31/08/2026",
        "asym_locked_rotor_factor": 1.6,
        "source": "Dados.xlsx + ETAP Induction Machine Editor > Protection + Thermal Curve Points 31/08/2026",
    },
    # V30: M-B-1 e M-B-2 são cópias integrais do M-B-0 (mesma placa,
    # mesma impedância, mesmos pontos térmicos e mesmo Hot Start), cada
    # um no seu próprio terminal de 6,6 kV. Entram FORA DE SERVIÇO: o
    # aluno liga na tela "Modelo físico" e mede o que muda. No caso MAX
    # da IEC 60909 cada motor entra como fonte de contribuição; no caso
    # MIN nenhum entra, então o efeito esperado é subir o curto MAX na
    # Barra5 e não mexer no MIN.
    {
        "name": "M-B-1", "bus": "Barra7", "in_service": False, "kw": 1600.0, "kv": 6.6,
        "kva": 1765.03, "amp": 154.40, "pf": 0.9268,
        "efficiency_percent": 97.8, "study_loading_percent": 90.0,
        "r_percent": 1.94, "x_percent": 15.26, "rx": 0.13,
        "lrc_percent": 650.0, "start_pf_percent": 12.6,
        "x0_percent": 15.38, "x0_over_r0": 31.428,
        "x2_percent": 15.38, "x2_over_r2": 31.428,
        "connection": "Y", "grounding": "Open",
        "start_time_s": 1.0, "start_time_reference_voltage_percent": 100.0,
        "stall_hot_s": 10.0, "stall_cold_s": 30.0,
        "stall_hot_enabled": True, "stall_cold_enabled": False,
        "thermal_curve_enabled": True,
        "thermal_points": [(1.55, 1000.0), (1.70, 500.0), (1.90, 300.0),
                           (2.40, 150.0), (3.00, 87.0), (3.60, 60.0)],
        "thermal_points_source": "espelhado do M-B-0",
        "asym_locked_rotor_factor": 1.6,
        "source": "V30 · máquina espelhada do M-B-0, sem correspondente no ETAP",
    },
    {
        "name": "M-B-2", "bus": "Barra8", "in_service": False, "kw": 1600.0, "kv": 6.6,
        "kva": 1765.03, "amp": 154.40, "pf": 0.9268,
        "efficiency_percent": 97.8, "study_loading_percent": 90.0,
        "r_percent": 1.94, "x_percent": 15.26, "rx": 0.13,
        "lrc_percent": 650.0, "start_pf_percent": 12.6,
        "x0_percent": 15.38, "x0_over_r0": 31.428,
        "x2_percent": 15.38, "x2_over_r2": 31.428,
        "connection": "Y", "grounding": "Open",
        "start_time_s": 1.0, "start_time_reference_voltage_percent": 100.0,
        "stall_hot_s": 10.0, "stall_cold_s": 30.0,
        "stall_hot_enabled": True, "stall_cold_enabled": False,
        "thermal_curve_enabled": True,
        "thermal_points": [(1.55, 1000.0), (1.70, 500.0), (1.90, 300.0),
                           (2.40, 150.0), (3.00, 87.0), (3.60, 60.0)],
        "thermal_points_source": "espelhado do M-B-0",
        "asym_locked_rotor_factor": 1.6,
        "source": "V30 · máquina espelhada do M-B-0, sem correspondente no ETAP",
    },
]

_SWITCHGEAR = [
    {"breaker": "DJ1", "relay": "Relé1", "from_bus": "Barra1", "to_bus": "Barra3", "device": "Cabo1"},
    {"breaker": "DJ5", "relay": "Relé2", "from_bus": "Barra2", "to_bus": "Barra3", "device": "Cabo3"},
    {"breaker": "DJ2", "relay": "Relé10", "from_bus": "Barra3", "to_bus": None, "device": "T1"},
    {"breaker": "DJ3", "relay": "Relé3", "from_bus": "Barra3", "to_bus": "Barra4", "device": "Cabo8"},
    {"breaker": "DJ4", "relay": "Relé11", "from_bus": "Barra5", "to_bus": "Barra6", "device": "Cabo2"},
    {"breaker": "DJ6", "relay": "Relé4", "from_bus": "Barra5", "to_bus": "Barra7", "device": "Cabo4"},
    {"breaker": "DJ7", "relay": "Relé5", "from_bus": "Barra5", "to_bus": "Barra8", "device": "Cabo5"},
]

# Ajustes atuais transcritos das telas ETAP OCR/OC1 (30/08/2026).
# ``pickup_51_a`` e ``pickup_50_a`` são os valores primários exibidos
# pelo ETAP. TCs (transformadores de corrente) como equipamento próprio
# — igual ao ETAP ("Current Transformer (CT) Editor | CT21", tela
# separada do relé). Cada zona só REFERENCIA um TC pelo nome; o valor de
# verdade mora aqui. Isso permite, no futuro, dois relés dividirem o
# mesmo TC físico sem duplicar dado (e sem risco de os dois ficarem
# dessincronizados).
_CTS = [
    {"name": "TC-Relé1", "primary_a": 1200.0, "secondary_a": 5.0, "location": "DJ1 · Gerador"},
    {"name": "TC-Relé2", "primary_a": 1200.0, "secondary_a": 5.0, "location": "DJ5 · Gerador GE2"},
    {"name": "TC-Relé10", "primary_a": 1500.0, "secondary_a": 5.0, "location": "DJ2 · T1 lado 13,8 kV"},
    {"name": "TC-Relé12", "primary_a": 1000.0, "secondary_a": 5.0, "location": "T1 lado 6,6 kV"},
    {"name": "TC-Relé11", "primary_a": 1000.0, "secondary_a": 5.0, "location": "DJ4 · M-B-0"},
    {"name": "TC-Relé3", "primary_a": 1500.0, "secondary_a": 5.0, "location": "DJ3 · M-B-6"},
    {"name": "TC-Relé4", "primary_a": 1000.0, "secondary_a": 5.0, "location": "DJ6 · M-B-1"},
    {"name": "TC-Relé5", "primary_a": 1000.0, "secondary_a": 5.0, "location": "DJ7 · M-B-2"},
]

_RELAY_ZONES = [
    {
        "id": "Z-R1", "title": "Relé1 · Gerador / DJ1", "relay": "Relé1", "relay_etap_name": 'Relay1',
        "breaker": "DJ1", "cable": "Cabo1", "bus": "Barra3", "motor": None,
        "transformer": None, "generator": "GE1", "kv": 13.8,
        "application": "generator", "relay_model": "MICOM_P241", "ct": "TC-Relé1",
        "etap_settings": {"curve": "IEC_EI", "pickup_51_a": 372.0, "time_setting": 1.175, "pickup_50_a": 14712.0, "delay_50_s": 0.01},
    },
    {
        "id": "Z-R2", "title": "Relé2 · Gerador GE2 / DJ5", "relay": "Relé2", "relay_etap_name": None,
        "breaker": "DJ5", "cable": "Cabo3", "bus": "Barra3", "motor": None,
        "transformer": None, "generator": "GE2", "kv": 13.8,
        "application": "generator", "relay_model": "MICOM_P241", "ct": "TC-Relé2",
        # V30: ajuste inicial copiado do Relé1 — o GE2 é máquina
        # espelhada e não tem folha ETAP própria. Deve ser reavaliado
        # com os dois em serviço.
        "etap_settings": {"curve": "IEC_EI", "pickup_51_a": 372.0, "time_setting": 1.175, "pickup_50_a": 14712.0, "delay_50_s": 0.01},
    },
    {
        "id": "Z-R10", "title": "Relé10 · T1 lado 13,8 kV", "relay": "Relé10", "relay_etap_name": 'Relay10',
        "breaker": "DJ2", "cable": None, "bus": "Barra5", "motor": None,
        "transformer": "T1", "generator": None, "kv": 13.8,
        "application": "transformer_hv", "relay_model": "MICOM_P241", "ct": "TC-Relé10",
        "etap_settings": {"curve": "IEC_EI", "pickup_51_a": 320.0, "time_setting": 1.0, "pickup_50_a": 14000.0, "delay_50_s": 0.0},
    },
    {
        "id": "Z-R12", "title": "Relé12 · T1 / Barra5 lado 6,6 kV", "relay": "Relé12", "relay_etap_name": 'Relay12',
        "breaker": None, "cable": None, "bus": "Barra5", "motor": None,
        "transformer": "T1", "generator": None, "kv": 6.6,
        "application": "transformer_lv", "relay_model": "MICOM_P241", "ct": "TC-Relé12",
        "etap_settings": {"curve": "IEC_EI", "pickup_51_a": 340.0, "time_setting": 0.575, "pickup_50_a": 9800.0, "delay_50_s": 0.0},
    },
    {
        "id": "Z-R11", "title": "Relé11 · DJ4 / M-B-0", "relay": "Relé11", "relay_etap_name": 'Relay11',
        "breaker": "DJ4", "cable": "Cabo2", "bus": "Barra6", "motor": "M-B-0",
        "transformer": None, "generator": None, "kv": 6.6,
        "application": "motor", "relay_model": "MICOM_P241", "ct": "TC-Relé11",
        "etap_settings": {"curve": "IEC_EI", "pickup_51_a": 230.0, "time_setting": 0.325, "pickup_50_a": 7760.0, "delay_50_s": 0.0},
    },
    {
        "id": "Z-R3", "title": "Relé3 · DJ3 / M-B-6", "relay": "Relé3", "relay_etap_name": 'Relay3',
        "breaker": "DJ3", "cable": "Cabo8", "bus": "Barra4", "motor": "M-B-6",
        "transformer": None, "generator": None, "kv": 13.8,
        "application": "motor", "relay_model": "MICOM_P241", "ct": "TC-Relé3",
        "etap_settings": {"curve": "IEC_EI", "pickup_51_a": 315.0, "time_setting": 0.8, "pickup_50_a": 6990.0, "delay_50_s": 0.0},
    },
    {
        "id": "Z-R4", "title": "Relé4 · DJ6 / M-B-1", "relay": "Relé4", "relay_etap_name": None,
        "breaker": "DJ6", "cable": "Cabo4", "bus": "Barra7", "motor": "M-B-1",
        "transformer": None, "generator": None, "kv": 6.6,
        "application": "motor", "relay_model": "MICOM_P241", "ct": "TC-Relé4",
        # V30: ajuste inicial copiado do Relé11 — o M-B-1 é o mesmo
        # motor do M-B-0 no mesmo nível de tensão. Deve ser reavaliado
        # com o motor ligado.
        "etap_settings": {"curve": "IEC_EI", "pickup_51_a": 230.0, "time_setting": 0.325, "pickup_50_a": 7760.0, "delay_50_s": 0.0},
    },
    {
        "id": "Z-R5", "title": "Relé5 · DJ7 / M-B-2", "relay": "Relé5", "relay_etap_name": None,
        "breaker": "DJ7", "cable": "Cabo5", "bus": "Barra8", "motor": "M-B-2",
        "transformer": None, "generator": None, "kv": 6.6,
        "application": "motor", "relay_model": "MICOM_P241", "ct": "TC-Relé5",
        # V30: mesmo ajuste inicial do Relé11, pelo mesmo motivo do
        # Relé4.
        "etap_settings": {"curve": "IEC_EI", "pickup_51_a": 230.0, "time_setting": 0.325, "pickup_50_a": 7760.0, "delay_50_s": 0.0},
    },
]

_COORDINATION_PATHS = [
    {
        "id": "PATH-MB0", "title": "M-B-0 → T1 → Gerador", "terminal_bus": "Barra6",
        "reference_kv": 6.6, "zones": ["Z-R11", "Z-R12", "Z-R10", "Z-R1"],
        "cables": ["Cabo2", "Cabo1"], "transformers": ["T1"], "motor": "M-B-0",
    },
    {
        "id": "PATH-MB6", "title": "M-B-6 → Gerador", "terminal_bus": "Barra4",
        "reference_kv": 13.8, "zones": ["Z-R3", "Z-R1"],
        "cables": ["Cabo8", "Cabo1"], "transformers": [], "motor": "M-B-6",
    },
]

DEFAULT_MODEL = {
    "case_id": CASE_ID, "case_name": CASE_NAME, "frequency_hz": FREQUENCY_HZ,
    "buses": _BUSES, "generators": _GENERATORS, "transformers": _TRANSFORMERS,
    "cables": _CABLES, "motors": _MOTORS, "switchgear": _SWITCHGEAR, "cts": _CTS,
    "zones": _RELAY_ZONES, "coordination_paths": _COORDINATION_PATHS,
}


def default_model() -> dict:
    """Devolve uma cópia nova do caso de fábrica.

    A cópia é profunda e feita a cada chamada, de propósito.
    ``DEFAULT_MODEL`` é a referência do estudo: se alguém alterasse o
    dicionário devolvido, estaria alterando o caso original para todo o
    resto do programa. Esse é um dos bugs mais difíceis de achar,
    porque o dado some em silêncio e só reaparece errado em outro
    cálculo, muito depois.
    """
    return copy.deepcopy(DEFAULT_MODEL)


def enrich_model(model: dict) -> dict:
    """Acrescenta ao modelo as grandezas derivadas dos dados de placa.

    Deriva, nunca copia. Corrente nominal, kVA, corrente de rotor
    bloqueado e impedâncias em ohm são **calculadas** a partir de kW,
    kV, fator de potência e rendimento — não lidas de um campo fixo da
    planilha.

    A razão é propagação: editar a potência de um motor na tela
    "Modelo físico" tem de mudar a corrente nominal, que muda o pickup
    de referência, que muda o coordenograma. Se a corrente fosse um
    valor copiado, a edição mudaria um número e deixaria os outros
    desatualizados, sem avisar ninguém.

    Não altera o dicionário recebido: trabalha sobre uma cópia.
    """
    model = copy.deepcopy(model)
    for g in model.get("generators", []):
        zbase = float(g["kv"]) ** 2 / float(g["sn_mva"])
        x1 = float(g["xdss_pu"]) * zbase; r1 = x1 / float(g["x_over_r"])
        x0 = float(g["x0_pu"]) * zbase; r0 = x0 / float(g["x0_over_r0"])
        x2 = float(g["x2_pu"]) * zbase; r2 = x2 / float(g["x2_over_r2"])
        vphase = float(g["kv"]) * 1000.0 / math.sqrt(3.0)
        rn = vphase / float(g["neutral_current_a"])
        g.update({"zbase_ohm": zbase, "rdss_ohm": r1, "xdss_ohm": x1,
                  "r0_ohm": r0, "x0_ohm": x0, "r2_ohm": r2, "x2_ohm": x2,
                  "neutral_resistor_ohm": rn, "z0_grounded_r_ohm": r0 + 3.0 * rn,
                  "z0_grounded_x_ohm": x0,
                  "fla_a": float(g["sn_mva"]) * 1e6 / (math.sqrt(3.0) * float(g["kv"]) * 1e3)})
    for t in model.get("transformers", []):
        xr = float(t["x_over_r"]); xr0 = float(t["x0_over_r0"])
        t["vkr_percent"] = float(t["vk_percent"]) / math.sqrt(1.0 + xr * xr)
        t["vkr0_percent"] = float(t["vk0_percent"]) / math.sqrt(1.0 + xr0 * xr0)
        t["fla_hv_a"] = float(t["sn_mva"]) * 1e6 / (math.sqrt(3.0) * float(t["vn_hv_kv"]) * 1e3)
        t["fla_lv_a"] = float(t["sn_mva"]) * 1e6 / (math.sqrt(3.0) * float(t["vn_lv_kv"]) * 1e3)
    for c in model.get("cables", []):
        c["length_km"] = float(c["length_m"]) / 1000.0
        n = max(1, int(c["parallel"]))
        c["r1_pf_eq_ohm"] = float(c["r1_pf_ohm_per_km"]) * c["length_km"] / n
        c["x1_pf_eq_ohm"] = float(c["x1_pf_ohm_per_km"]) * c["length_km"] / n
    for m in model.get("motors", []):
        # amp/kva são sempre derivados de kw/kv/pf/efficiency_percent —
        # nunca um valor fixo copiado do Dados.xlsx. Isso garante que
        # editar o motor em "Modelo físico" (kw, pf, etc.) propague pra
        # corrente nominal/LRC usada em TODO o módulo de proteção (TCC,
        # pickup, multiplos), não só pro fluxo de potência e
        # curto-circuito do Pandapower.
        kw = float(m["kw"]); kv = float(m["kv"]); pf = float(m["pf"]); eff = float(m["efficiency_percent"])
        p_elec_kw = kw / (eff / 100.0)
        m["amp"] = p_elec_kw * 1000.0 / (math.sqrt(3.0) * kv * 1000.0 * pf)
        m["kva"] = p_elec_kw / pf
        m["lrc_pu"] = float(m["lrc_percent"]) / 100.0
        m["locked_rotor_current_a"] = float(m["amp"]) * m["lrc_pu"]
        m["lrc_from_rx_pu"] = 100.0 / math.hypot(float(m["r_percent"]), float(m["x_percent"]))
        m["p_electrical_mw"] = p_elec_kw / 1000.0
        phi = math.acos(pf); m["q_electrical_mvar"] = m["p_electrical_mw"] * math.tan(phi)
    return model


# ----------------------------------------------------------------------
# V29 — edição de equipamentos (parâmetros de maior impacto elétrico).
#
# Cada entrada descreve um campo que o front-end pode expor como
# editável. Ficaram de fora, por ora, os campos que hoje não entram em
# nenhum cálculo do Pandapower/curto-circuito/TCC (ex.: rpm, poles,
# temp_rise_c) e os pontos de curva (thermal_points, damage_points_pu,
# inrush), que exigem um editor de tabela e não um campo único.
# ----------------------------------------------------------------------

EQUIPMENT_FIELD_SCHEMA: dict[str, list[dict]] = {
    "cts": [
        {"key": "primary_a", "label": "TC primário", "unit": "A", "type": "float", "min": 1.0},
        {"key": "secondary_a", "label": "TC secundário", "unit": "A", "type": "float", "min": 0.1},
    ],
    "generators": [
        {"key": "in_service", "label": "Em serviço", "unit": "", "type": "bool"},
        {"key": "sn_mva", "label": "Potência aparente", "unit": "MVA", "type": "float", "min": 0.01},
        {"key": "kv", "label": "Tensão nominal", "unit": "kV", "type": "float", "min": 0.01},
        {"key": "pf", "label": "Fator de potência", "unit": "", "type": "float", "min": 0.01, "max": 1.0},
        {"key": "efficiency_percent", "label": "Rendimento", "unit": "%", "type": "float", "min": 1.0, "max": 100.0},
        {"key": "xdss_pu", "label": "Xd\" subtransitório", "unit": "pu", "type": "float", "min": 0.0001},
        {"key": "x_over_r", "label": "X/R (sequência positiva)", "unit": "", "type": "float", "min": 0.01},
        {"key": "x0_pu", "label": "X0", "unit": "pu", "type": "float", "min": 0.0001},
        {"key": "x0_over_r0", "label": "X0/R0", "unit": "", "type": "float", "min": 0.01},
        {"key": "x2_pu", "label": "X2", "unit": "pu", "type": "float", "min": 0.0001},
        {"key": "x2_over_r2", "label": "X2/R2", "unit": "", "type": "float", "min": 0.01},
        {"key": "neutral_current_a", "label": "Corrente de neutro (aterramento)", "unit": "A", "type": "float", "min": 0.01},
    ],
    "transformers": [
        {"key": "sn_mva", "label": "Potência nominal", "unit": "MVA", "type": "float", "min": 0.01},
        {"key": "vn_hv_kv", "label": "Tensão AT", "unit": "kV", "type": "float", "min": 0.01},
        {"key": "vn_lv_kv", "label": "Tensão BT", "unit": "kV", "type": "float", "min": 0.01},
        {"key": "vk_percent", "label": "Impedância Z", "unit": "%", "type": "float", "min": 0.01},
        {"key": "x_over_r", "label": "X/R (sequência positiva)", "unit": "", "type": "float", "min": 0.01},
        {"key": "vk0_percent", "label": "Impedância Z0", "unit": "%", "type": "float", "min": 0.01},
        {"key": "x0_over_r0", "label": "X0/R0", "unit": "", "type": "float", "min": 0.01},
        {"key": "vector_group", "label": "Grupo vetorial", "unit": "", "type": "select",
         "options": ["Dyn", "Dyn1", "Dyn5", "Dyn11", "Yyn", "YNyn", "Ynd1", "Ynd11"]},
        {"key": "shift_degree", "label": "Defasagem angular", "unit": "graus", "type": "float", "min": 0.0, "max": 360.0},
        {"key": "hv_connection", "label": "Ligação AT", "unit": "", "type": "select", "options": ["D", "Y", "Yn"]},
        {"key": "lv_connection", "label": "Ligação BT", "unit": "", "type": "select", "options": ["D", "Y", "Yn"]},
        {"key": "lv_grounding", "label": "Aterramento BT", "unit": "", "type": "select", "options": ["Solid", "Resistance", "Open"]},
    ],
    "cables": [
        {"key": "size_mm2", "label": "Seção", "unit": "mm²", "type": "float", "min": 0.01},
        {"key": "length_m", "label": "Comprimento", "unit": "m", "type": "float", "min": 0.01},
        {"key": "parallel", "label": "Cabos em paralelo", "unit": "", "type": "int", "min": 1},
        {"key": "r1_pf_ohm_per_km", "label": "R1 operação", "unit": "Ω/km", "type": "float", "min": 0.0},
        {"key": "x1_pf_ohm_per_km", "label": "X1 operação", "unit": "Ω/km", "type": "float", "min": 0.0},
        {"key": "r0_pf_ohm_per_km", "label": "R0 operação", "unit": "Ω/km", "type": "float", "min": 0.0},
        {"key": "x0_pf_ohm_per_km", "label": "X0 operação", "unit": "Ω/km", "type": "float", "min": 0.0},
        {"key": "r1_sc20_ohm_per_1000ft", "label": "R1 a 20°C (curto)", "unit": "Ω/1000ft", "type": "float", "min": 0.0},
        {"key": "x1_sc_ohm_per_1000ft", "label": "X1 (curto)", "unit": "Ω/1000ft", "type": "float", "min": 0.0},
        {"key": "r0_sc20_ohm_per_1000ft", "label": "R0 a 20°C (curto)", "unit": "Ω/1000ft", "type": "float", "min": 0.0},
        {"key": "x0_sc_ohm_per_1000ft", "label": "X0 (curto)", "unit": "Ω/1000ft", "type": "float", "min": 0.0},
        {"key": "k_adiabatic", "label": "k adiabático", "unit": "A√s/mm²", "type": "float", "min": 0.01},
    ],
    "motors": [
        {"key": "in_service", "label": "Em serviço", "unit": "", "type": "bool"},
        {"key": "kw", "label": "Potência", "unit": "kW", "type": "float", "min": 0.01},
        {"key": "kv", "label": "Tensão nominal", "unit": "kV", "type": "float", "min": 0.01},
        {"key": "pf", "label": "Fator de potência", "unit": "", "type": "float", "min": 0.01, "max": 1.0},
        {"key": "efficiency_percent", "label": "Rendimento", "unit": "%", "type": "float", "min": 1.0, "max": 100.0},
        {"key": "r_percent", "label": "%R", "unit": "%", "type": "float", "min": 0.01},
        {"key": "x_percent", "label": "%X", "unit": "%", "type": "float", "min": 0.01},
        {"key": "rx", "label": "R/X de partida", "unit": "", "type": "float", "min": 0.0},
        {"key": "x0_percent", "label": "%X0", "unit": "%", "type": "float", "min": 0.01},
        {"key": "x2_percent", "label": "%X2", "unit": "%", "type": "float", "min": 0.01},
        {"key": "lrc_percent", "label": "LRC (corrente de partida)", "unit": "%", "type": "float", "min": 1.0},
    ],
}


def find_equipment(model: dict, category: str, name: str) -> dict | None:
    """Localiza um equipamento pelo nome dentro de uma categoria.

    Devolve ``None`` quando não existe, em vez de levantar exceção: quem
    chama normalmente quer saber se existe, não tratar erro.
    """
    for item in model.get(category, []):
        if item.get("name") == name:
            return item
    return None


def validate_equipment_payload(category: str, payload: dict) -> dict:
    """Valida e normaliza um payload de edição de equipamento.

    Levanta ValueError com uma mensagem em português, pronta para
    retornar ao usuário, caso algum campo não seja editável ou esteja
    fora da faixa.
    """
    schema = EQUIPMENT_FIELD_SCHEMA.get(category)
    if schema is None:
        raise ValueError(f"Categoria '{category}' não é editável")
    fields_by_key = {f["key"]: f for f in schema}
    if not payload:
        raise ValueError("Nenhum campo enviado")
    clean: dict = {}
    for key, raw_value in payload.items():
        field = fields_by_key.get(key)
        if field is None:
            raise ValueError(f"Campo '{key}' não é editável para {category}")
        if field["type"] in ("float", "int"):
            try:
                num = float(raw_value)
            except (TypeError, ValueError):
                raise ValueError(f"{field['label']}: informe um número válido")
            if not math.isfinite(num):
                raise ValueError(f"{field['label']}: valor inválido")
            if "min" in field and num < field["min"]:
                raise ValueError(f"{field['label']}: mínimo permitido é {field['min']}")
            if "max" in field and num > field["max"]:
                raise ValueError(f"{field['label']}: máximo permitido é {field['max']}")
            clean[key] = int(round(num)) if field["type"] == "int" else num
        elif field["type"] == "bool":
            if isinstance(raw_value, str):
                clean[key] = raw_value.strip().lower() in ("1", "true", "sim", "on")
            else:
                clean[key] = bool(raw_value)
        elif field["type"] == "select":
            sval = str(raw_value)
            options = field.get("options") or []
            if options and sval not in options:
                raise ValueError(f"{field['label']}: valor deve ser um de {', '.join(options)}")
            clean[key] = sval
        else:
            clean[key] = raw_value
    return clean
