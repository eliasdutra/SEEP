from pathlib import Path
import pytest
import core.storage as storage

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", Path(tmp_path) / "protection_test.db")
