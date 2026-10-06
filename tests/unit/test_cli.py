from sqlide.cli import main


def test_doctor_runs(capsys):
    assert main(["doctor"]) == 0
    assert "doctor" in capsys.readouterr().out
