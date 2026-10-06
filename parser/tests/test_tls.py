from connectors.tls import resolve_verify


def test_default_is_full_verification(monkeypatch):
    monkeypatch.delenv("CUSTOM_CA_BUNDLE", raising=False)
    assert resolve_verify(None) is True
    assert resolve_verify({}) is True


def test_source_ca_bundle_wins_over_everything(monkeypatch, tmp_path):
    env_bundle = tmp_path / "env.pem"
    env_bundle.write_text("x")
    monkeypatch.setenv("CUSTOM_CA_BUNDLE", str(env_bundle))
    assert resolve_verify({"ca_bundle": "/certs/kunde.pem", "verify_ssl": False}) == "/certs/kunde.pem"


def test_explicit_opt_out_disables_verification(monkeypatch):
    monkeypatch.delenv("CUSTOM_CA_BUNDLE", raising=False)
    assert resolve_verify({"verify_ssl": False}) is False
    assert resolve_verify({"verify_ssl": True}) is True


def test_worker_wide_ca_bundle_is_used_when_the_file_exists(monkeypatch, tmp_path):
    bundle = tmp_path / "ca.pem"
    bundle.write_text("x")
    monkeypatch.setenv("CUSTOM_CA_BUNDLE", str(bundle))
    assert resolve_verify({}) == str(bundle)
    monkeypatch.setenv("CUSTOM_CA_BUNDLE", str(tmp_path / "missing.pem"))
    assert resolve_verify({}) is True
