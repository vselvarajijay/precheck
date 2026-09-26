from pathlib import Path

import pytest

from precheck.core.settings import EXAMPLES_DIR
from precheck.core.testing import noul_rule

EXAMPLES = EXAMPLES_DIR


@pytest.fixture
def examples() -> Path:
    return EXAMPLES


__all__ = ["EXAMPLES", "noul_rule"]
