import math
from core.data import enrich_model, default_model
from core import protection


def test_cable2_uses_etap_k2s2():
    m=enrich_model(default_model()); c=next(x for x in m["cables"] if x["name"]=="Cabo2")
    xs,ys=protection._cable_damage_trace(c,143.0,30000.0,100.0)
    # Em 1 kA, t deve ser aproximadamente 5,23 s.
    i=min(range(len(xs)), key=lambda j: abs(xs[j]-1000.0))
    assert math.isclose(ys[i], 5.23, rel_tol=0.08)

def test_cable8_uses_etap_k2s2():
    m=enrich_model(default_model()); c=next(x for x in m["cables"] if x["name"]=="Cabo8")
    xs,ys=protection._cable_damage_trace(c,143.0,150000.0,1000.0)
    # Em 10 kA, t deve ser aproximadamente 1,1503 s.
    i=min(range(len(xs)), key=lambda j: abs(xs[j]-10000.0))
    assert math.isclose(ys[i], 1.1503, rel_tol=0.08)

def test_motor_start_envelope_is_anchored_to_acceleration():
    m=enrich_model(default_model()); mot=next(x for x in m["motors"] if x["name"]=="M-B-0")
    tr=protection._motor_start_envelope(mot,6.6)
    assert tr["name"]=="M-B-0-100%"
    assert min(tr["y"])==0.01
    assert any(abs(y-mot["start_time_s"])<1e-9 for y in tr["y"])

def test_etap_cable_references_are_validation_only():
    m=default_model(); refs={c["name"]:c.get("etap_sc_reference") for c in m["cables"]}
    assert refs["Cabo2"]["3f_ka"]==10.33
    assert refs["Cabo8"]["3f_ka"]==14.99
