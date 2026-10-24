"""Persistência em SQLite: ajustes de relé e edições de equipamento.

Posição no pipeline do estudo:

    data.py  ->  **storage.py**  ->  network.py  ->  solver.py  ->
    protection.py  ->  app.py

Guarda duas coisas, em duas tabelas:

``settings``
    Os ajustes 50/51 de cada zona de proteção, como o usuário os salvou.
``equipment_overrides``
    As edições de parâmetro de equipamento feitas na tela "Modelo
    físico".

O caso de fábrica — o que veio do ETAP, em ``data.py`` — **nunca é
alterado em disco**. As edições ficam guardadas à parte e são
sobrepostas em memória a cada leitura de ``get_model()``. É por isso que
"Restaurar ETAP" sempre funciona: o original não foi perdido, foi apenas
coberto.

Essa é a ideia que vale explicar em aula: separar o *dado de referência*
do *estado editado pelo usuário* é o que torna um estudo reprodutível.
Quem sobrescreve o arquivo original não consegue mais responder "e se eu
não tivesse mexido?".

Ponto de entrada
----------------
``get_model()`` devolve o modelo efetivo — fábrica mais edições. Todo o
resto do programa lê por aqui, nunca direto de ``data.default_model()``.

Nota de empacotamento
---------------------
Sob PyInstaller, ``__file__`` aponta para dentro do bundle, que é
descartado a cada atualização. Nesse caso o banco é gravado ao lado do
executável, para o trabalho do usuário não desaparecer quando a versão
mudar.
"""
from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path
from .data import default_model

# Empacotado com PyInstaller, __file__ aponta pra dentro do bundle
# interno, não pra pasta do executável — o banco ficaria enterrado e
# "sumiria" a cada atualização. Nesse caso, guarda data/protection.db do
# lado do .exe mesmo.
if getattr(sys, "frozen", False):
    _PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    _PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = _PROJECT_ROOT / "data" / "protection.db"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settings("
        "zone_id TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS equipment_overrides("
        "category TEXT NOT NULL,name TEXT NOT NULL,payload TEXT NOT NULL,"
        "updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(category,name))"
    )
    conn.commit()
    return conn


def get_settings(zone_id: str):
    """Lê os ajustes salvos de uma zona, ou ``None`` se não houver.
    """
    with _connect() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE zone_id=?", (zone_id,)).fetchone()
        return None if row is None else json.loads(row["payload"])


def save_settings(zone_id: str, payload: dict):
    """Grava os ajustes de uma zona, substituindo o que havia.

    Guarda o payload inteiro como JSON numa linha só. O formato é
    versátil de propósito: campos novos de ajuste não exigem migração de
    esquema do banco.
    """
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings(zone_id,payload) VALUES(?,?) "
            "ON CONFLICT(zone_id) DO UPDATE SET payload=excluded.payload,updated_at=CURRENT_TIMESTAMP",
            (zone_id, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()


def delete_settings(zone_id: str):
    """Apaga os ajustes de uma zona, voltando ao provisório calculado.
    """
    with _connect() as conn:
        conn.execute("DELETE FROM settings WHERE zone_id=?", (zone_id,))
        conn.commit()


def export_all_settings() -> dict:
    """Devolve todos os ajustes salvos, para exportação do estudo.
    """
    with _connect() as conn:
        rows = conn.execute("SELECT zone_id,payload,updated_at FROM settings ORDER BY zone_id").fetchall()
        return {
            row["zone_id"]: {"settings": json.loads(row["payload"]), "updated_at": row["updated_at"]}
            for row in rows
        }


def get_equipment_override(category: str, name: str):
    """Lê a edição de um equipamento, ou ``None`` se não foi editado.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM equipment_overrides WHERE category=? AND name=?",
            (category, name),
        ).fetchone()
        return None if row is None else json.loads(row["payload"])


def save_equipment_override(category: str, name: str, payload: dict):
    """Grava a edição de parâmetros de um equipamento.

    Só o que o usuário mudou é gravado. O dado de fábrica permanece em
    ``data.py``, intocado — ver ``get_model``.
    """
    with _connect() as conn:
        conn.execute(
            "INSERT INTO equipment_overrides(category,name,payload) VALUES(?,?,?) "
            "ON CONFLICT(category,name) DO UPDATE SET payload=excluded.payload,updated_at=CURRENT_TIMESTAMP",
            (category, name, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()


def delete_equipment_override(category: str, name: str):
    """Descarta a edição de um equipamento, restaurando o dado do ETAP.
    """
    with _connect() as conn:
        conn.execute("DELETE FROM equipment_overrides WHERE category=? AND name=?", (category, name))
        conn.commit()


def list_equipment_overrides() -> dict:
    """Devolve todas as edições, agrupadas por categoria e nome.

    É o que ``get_model`` sobrepõe ao caso de fábrica, e é também o que
    a tela usa para marcar quais equipamentos foram alterados.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT category,name,payload,updated_at FROM equipment_overrides ORDER BY category,name"
        ).fetchall()
        out: dict = {}
        for row in rows:
            out.setdefault(row["category"], {})[row["name"]] = {
                "values": json.loads(row["payload"]),
                "updated_at": row["updated_at"],
            }
        return out


def get_model() -> dict:
    """O caso físico efetivo: dado de fábrica mais as edições.

    O caso de fábrica (``default_model``) nunca é alterado em disco; as
    edições ficam em ``equipment_overrides`` e são sobrepostas em
    memória a cada leitura, então "Restaurar ETAP" é sempre possível sem
    perder o dado original.
    """
    model = default_model()
    overrides = list_equipment_overrides()
    for category, by_name in overrides.items():
        items = model.get(category)
        if not items:
            continue
        for item in items:
            ov = by_name.get(item.get("name"))
            if ov:
                item.update(ov["values"])
    return model
