from precheck.core.schema.validate import main, validate_file

from .conftest import EXAMPLES


def test_refund_example_validates() -> None:
    ok, msg = validate_file(EXAMPLES / "refund.yaml")
    assert ok and msg == "OK, 2 rules"


def test_refund_example_not_publishable_until_pinned() -> None:
    ok, msg = validate_file(EXAMPLES / "refund.yaml", live=True)
    assert not ok and "must pin a Jev version" in msg


def test_all_example_requests_validate() -> None:
    files = sorted((EXAMPLES / "requests").glob("*.json"))
    assert len(files) == 4
    assert main([str(f) for f in files]) == 0


def test_validate_cli_reports_invalid(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"gate": "tool_call"}')
    assert main([str(bad)]) == 1
