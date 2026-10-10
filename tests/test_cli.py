import yaml
from openapi_spec_validator import validate
from typer.testing import CliRunner

from apiscribe import cli
from apiscribe.cli import app
from tests.conftest import make_entry, make_har
from tests.test_redact import JWT

runner = CliRunner()
HOST = "api.example.com"
COOKIE_SECRET = "s3ss10nV4lu3xyz"
PASSWORD = "Hunter2Password!"


def sample_har():
    auth = {"Authorization": f"Bearer {JWT}", "Cookie": f"sessionid={COOKIE_SECRET}"}
    return make_har(
        make_entry(f"https://{HOST}/orders/42?expand=items", request_headers=auth,
                   response_json={"id": 42, "total": 19.5, "email": "bob@example.org", "note": None}),
        make_entry(f"https://{HOST}/orders/57", request_headers=auth,
                   response_json={"id": 57, "total": 5, "email": "amy@example.org"}),
        make_entry(f"https://{HOST}/login", method="POST",
                   request_json={"email": "bob@example.org", "password": PASSWORD},
                   response_json={"token": JWT}),
        make_entry("https://cdn.example.com/logo.png", response_mime="image/png", response_text="png"),
        make_entry(f"https://{HOST}/orders/42", method="OPTIONS", status=204, response_mime=""),
    )  # fmt: skip


def test_help_lists_gen_command():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "gen" in result.output


def test_gen_end_to_end(write_har, tmp_path):
    out = tmp_path / "openapi.yaml"
    result = runner.invoke(app, ["gen", str(write_har(sample_har())), "--host", HOST, "-o", str(out)])

    assert result.exit_code == 0, result.output
    assert "5 entries -> 3 JSON API calls -> 2 endpoints" in result.output

    text = out.read_text(encoding="utf-8")
    spec = yaml.safe_load(text)
    validate(spec)

    assert set(spec["paths"]) == {"/orders/{order_id}", "/login"}
    order = spec["paths"]["/orders/{order_id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert order["required"] == ["id", "total", "email"]
    assert order["properties"]["total"] == {"type": "number"}
    assert order["properties"]["note"] == {"nullable": True}
    assert set(spec["components"]["securitySchemes"]) == {"bearerAuth", "cookieSessionid"}


def test_gen_never_writes_secrets(write_har, tmp_path):
    out = tmp_path / "openapi.yaml"
    runner.invoke(app, ["gen", str(write_har(sample_har())), "--host", HOST, "-o", str(out)])
    text = out.read_text(encoding="utf-8")
    for secret in [JWT, COOKIE_SECRET, PASSWORD, "bob@example.org", "amy@example.org"]:
        assert secret not in text


def test_custom_title(write_har, tmp_path):
    out = tmp_path / "openapi.yaml"
    runner.invoke(app, ["gen", str(write_har(sample_har())), "--host", HOST, "-o", str(out), "--title", "Shop"])
    assert yaml.safe_load(out.read_text(encoding="utf-8"))["info"]["title"] == "Shop"


def test_leak_check_refuses_to_write(write_har, tmp_path, monkeypatch):
    out = tmp_path / "openapi.yaml"
    monkeypatch.setattr(cli.openapi, "to_yaml", lambda spec: f"oops: {COOKIE_SECRET}\n")
    result = runner.invoke(app, ["gen", str(write_har(sample_har())), "--host", HOST, "-o", str(out)])
    assert result.exit_code == 1
    assert "Nothing was written" in result.output
    assert COOKIE_SECRET not in result.output
    assert not out.exists()


def test_no_matching_calls(write_har, tmp_path):
    result = runner.invoke(app, ["gen", str(write_har(sample_har())), "--host", "other.com",
                                 "-o", str(tmp_path / "x.yaml")])  # fmt: skip
    assert result.exit_code == 1
    assert "No JSON API calls to other.com" in result.output


def test_invalid_har(tmp_path):
    bad = tmp_path / "bad.har"
    bad.write_text("not json", encoding="utf-8")
    result = runner.invoke(app, ["gen", str(bad), "--host", HOST])
    assert result.exit_code == 1
    assert "not valid JSON" in result.output
