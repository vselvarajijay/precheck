import pytest

from precheck.lab.tools.server import build_server
from precheck.mcp_proxy.testing import SAFE, Lab, build_lab, demo_rules


@pytest.fixture
def lab() -> Lab:
    """The proxy in front of the lab mock tools, demo rules, fake Jev."""
    tools_server, log = build_server()
    return build_lab(tools_server, log)


DEMO_RULES = demo_rules()
__all__ = ["DEMO_RULES", "SAFE", "Lab", "lab"]
