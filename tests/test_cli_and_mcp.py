from __future__ import annotations

import asyncio
import json

from conftest import fixture

from fec_lint import FULL_PRE_AUDIT_URL
from fec_lint.cli import main
from fec_lint.mcp_server import lint_fec, mcp


def test_cli_ok_ends_with_pre_audit_line(capsys) -> None:
    assert main([str(fixture('valid'))]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].endswith('OK (encoding utf-8, separator pipe, lines 214)')
    assert lines[-1] == f'Structure OK. Full pre-audit (balance, numbering, risk signals): {FULL_PRE_AUDIT_URL}'


def test_cli_errors_exit_1(capsys) -> None:
    assert main([str(fixture('bad_dates'))]) == 1
    out = capsys.readouterr().out
    assert 'error date_invalid x3' in out
    assert out.strip().splitlines()[-1].startswith('Structure has errors. Full pre-audit')


def test_cli_quiet_hides_the_line(capsys) -> None:
    main([str(fixture('valid')), '--quiet'])
    assert FULL_PRE_AUDIT_URL not in capsys.readouterr().out


def test_cli_json(capsys) -> None:
    main([str(fixture('bad_headers')), '--json'])
    data = json.loads(capsys.readouterr().out)
    assert data['ok'] is False
    assert {'ok', 'file', 'errors', 'warnings', 'stats'} <= set(data)


def test_cli_several_files(capsys) -> None:
    assert main([str(fixture('valid')), str(fixture('bad_dates'))]) == 1
    assert capsys.readouterr().out.count('123456782FEC20251231.txt:') == 2


def test_cli_missing_file(capsys, tmp_path) -> None:
    assert main([str(tmp_path / 'nope.txt')]) == 2


def test_mcp_tool_is_registered_with_its_description() -> None:
    tools = asyncio.run(mcp.list_tools())
    assert [t.name for t in tools] == ['lint_fec']
    assert 'Structural check only' in tools[0].description
    assert tools[0].input_schema['required'] == ['path']
    assert tools[0].annotations.read_only_hint is True


def test_mcp_tool_returns_the_lint_result() -> None:
    assert lint_fec(str(fixture('valid')))['ok'] is True
    assert lint_fec(str(fixture('bad_dates')))['ok'] is False
