import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SPNI_DEMO_SPEED", "0")


@pytest.fixture
def cases_dir(tmp_path):
    return tmp_path / "cases"
