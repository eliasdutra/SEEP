"""Critérios de seleção de falta usados no estudo de proteção.

Módulo pequeno e deliberadamente isolado. Cada função responde a uma
pergunta do tipo "entre as faltas calculadas nesta barra, qual é a que
importa para *esta* verificação?".

Por que isso não está dentro de ``protection.py``: a escolha da falta
governante é um **critério**, não um cálculo. Isolá-la aqui deixa
explícito que são três perguntas diferentes, com três respostas
diferentes, e torna cada uma testável sozinha.

As três perguntas
-----------------
``select_critical_phase_min(sc_row)``
    *Sensibilidade.* A menor falta de fase do caso mínimo — a que o relé
    tem mais dificuldade de enxergar. Toma o menor valor entre 3F e LL,
    em vez de assumir que a 3F mínima é sempre a crítica.
``select_max_phase_fault(sc_row)``
    *Seletividade e alcance.* A maior falta de fase do caso máximo,
    usada para ajustar a função 50 e verificar sobrealcance.
``select_max_fault_duty(sc_row)``
    *Dever de interrupção.* A maior corrente entre todos os tipos de
    falta, inclusive as que envolvem a terra — o disjuntor precisa
    interromper a pior, não a mais comum.

Todas devolvem ``{"available": bool, "fault": str, "ka": float}``.
Quando o dado não existe, devolvem ``available=False`` em vez de zero:
ausência de informação não é corrente nula.
"""
from __future__ import annotations
from typing import Any


def select_critical_phase_min(sc_row: dict | None) -> dict[str, Any]:
    """Menor falta de fase do caso mínimo: a sensibilidade.

    Toma o **menor** valor entre a trifásica e a bifásica, em vez de
    assumir que a 3F mínima é sempre a crítica. Dependendo da barra e do
    aterramento, a bifásica pode ser menor, e é ela que o relé terá mais
    dificuldade de enxergar.

    É contra esta corrente que se verifica se a proteção enxerga a
    falta: ``Icc mínima / pickup`` deve ficar acima do fator de
    sensibilidade adotado.
    """
    if not sc_row:
        return {"available": False, "fault": None, "ka": None}
    candidates = [(float(sc_row[k]), label) for k, label in (("3f_ka","3F"),("ll_ka","LL")) if sc_row.get(k) is not None]
    if not candidates:
        return {"available": False, "fault": None, "ka": None}
    value, label = min(candidates, key=lambda item:item[0])
    out={"available":True,"fault":label,"ka":value}
    if sc_row.get("phase_min_method"): out["method"]=sc_row["phase_min_method"]
    if sc_row.get("source"): out["source"]=sc_row["source"]
    return out


def select_max_phase_fault(sc_row: dict | None) -> dict[str, Any]:
    """Maior falta de fase do caso máximo — referência de seletividade.

    Usada para ajustar a função 50 e verificar sobrealcance: o
    instantâneo não pode enxergar falta além da zona que ele protege.
    """
    if not sc_row:
        return {"available": False, "fault": None, "ka": None}
    candidates = [(float(sc_row[k]), label) for k, label in (("3f_ka","3F"),("ll_ka","LL")) if sc_row.get(k) is not None]
    if not candidates:
        return {"available": False, "fault": None, "ka": None}
    value, label = max(candidates, key=lambda item:item[0])
    out={"available":True,"fault":label,"ka":value}
    if sc_row.get("phase_min_method"): out["method"]=sc_row["phase_min_method"]
    if sc_row.get("source"): out["source"]=sc_row["source"]
    return out


def select_max_fault_duty(sc_row: dict | None) -> dict[str, Any]:
    """Maior corrente entre todas as faltas: dever de interrupção.

    Diferente das outras duas, esta considera também as faltas que
    envolvem a terra. O disjuntor precisa conseguir interromper a
    **pior** corrente que pode aparecer nele, não a mais provável nem a
    mais comum nos estudos de coordenação.
    """
    if not sc_row:
        return {"available": False, "fault": None, "ka": None}
    candidates=[(float(sc_row[k]),label) for k,label in (("3f_ka","3F"),("ll_ka","LL"),("lg_ka","LG"),("llg_ka","LLG")) if sc_row.get(k) is not None]
    if not candidates:
        return {"available": False, "fault": None, "ka": None}
    value,label=max(candidates,key=lambda item:item[0])
    out={"available":True,"fault":label,"ka":value}
    if sc_row.get("phase_min_method"): out["method"]=sc_row["phase_min_method"]
    if sc_row.get("source"): out["source"]=sc_row["source"]
    return out
