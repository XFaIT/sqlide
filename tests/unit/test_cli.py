from sqlide.cli import main


def test_doctor_runs(capsys):
    main(["doctor"])  # exit code depends on the machine; output must list checks
    out = capsys.readouterr().out
    assert "java" in out and "drivers" in out


def test_driver_list(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("SQLIDE_CONFIG_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("SQLIDE_DATA_DIR", str(tmp_path / "d"))
    assert main(["driver", "list"]) == 0
    assert "postgres" in capsys.readouterr().out
