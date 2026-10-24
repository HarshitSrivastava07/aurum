"""Keep import-time application setup away from the running app's databases."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory


def pytest_configure(config):
    # Fixtures run after collection, but importing backend.main creates its app.
    # Establish isolated paths before any test module can import that boundary.
    runtime = TemporaryDirectory(prefix="aurum-pytest-", ignore_cleanup_errors=True)
    previous = {name: os.environ.get(name) for name in ("AURUM_DATA_DIR", "AURUM_EVIDENCE_DIR")}
    config._aurum_test_environment = (runtime, previous)
    os.environ["AURUM_DATA_DIR"] = str(Path(runtime.name) / "data")
    os.environ["AURUM_EVIDENCE_DIR"] = str(Path(runtime.name) / "evidence")


def pytest_unconfigure(config):
    isolated = getattr(config, "_aurum_test_environment", None)
    if isolated is None:
        return
    runtime, previous = isolated
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    runtime.cleanup()
    del config._aurum_test_environment
