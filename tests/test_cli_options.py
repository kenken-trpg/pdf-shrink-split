"""CLIの引数検証と、依存の自動インストールのテスト"""
import os
import subprocess
import sys

import pytest

from conftest import CLI_PATH, ROOT
from pdf_fixtures import build_pdf


def run_cli(*args):
    return subprocess.run([sys.executable, CLI_PATH, *args],
                          capture_output=True, text=True, timeout=60)


def outputs_of(src):
    """入力PDFの横に作られた出力ファイルの一覧を返す"""
    stem = os.path.splitext(os.path.basename(src))[0]
    return sorted(name for name in os.listdir(os.path.dirname(src))
                  if name.startswith(f"{stem}_"))


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5"])
def test_invalid_char_limit_is_rejected(tmp_path, value):
    src = build_pdf(tmp_path / "limit.pdf", pages=2)

    result = run_cli(src, "--char-limit", value)

    assert result.returncode == 1
    assert "1以上の整数" in result.stdout
    assert outputs_of(src) == []


def test_missing_char_limit_value_is_rejected(tmp_path):
    src = build_pdf(tmp_path / "limit.pdf", pages=2)

    result = run_cli(src, "--char-limit")

    assert result.returncode == 1
    assert outputs_of(src) == []


def test_smallest_char_limit_is_accepted(tmp_path):
    src = build_pdf(tmp_path / "limit.pdf", pages=2)

    result = run_cli(src, "--char-limit", "1")

    assert result.returncode == 0, result.stdout + result.stderr
    assert outputs_of(src) == ["limit_part1.pdf", "limit_part2.pdf"]


def test_auto_install_pins_match_requirements(cli):
    """自動インストールの版が requirements.txt とずれていない"""
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        lines = [line.split("#")[0].strip() for line in f]
    pinned = {line.split("==")[0].lower(): line for line in lines if line}

    assert cli.REQUIRED_PACKAGES, "自動インストールの対象がありません"
    for pip_spec in cli.REQUIRED_PACKAGES.values():
        name = pip_spec.split("==")[0].lower()
        assert pinned.get(name) == pip_spec, (
            f"{pip_spec} が requirements.txt の {pinned.get(name)} と"
            "一致していません")


def test_install_failure_explains_what_to_check(cli, monkeypatch, capsys):
    """pipの失敗時はトレースバックではなく確認事項を案内して終了する"""
    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(cli, "REQUIRED_PACKAGES",
                        {"no_such_module_for_test": "no-such-package==1.0"})
    monkeypatch.setattr(cli.subprocess, "check_call", fail)

    with pytest.raises(SystemExit) as exit_info:
        cli.install_packages()

    assert exit_info.value.code == 1
    output = capsys.readouterr().out
    assert "no-such-package==1.0" in output
    assert "Python 3.11以上" in output
