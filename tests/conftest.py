from __future__ import annotations

from pathlib import Path

import pytest

from fec_lint.core import EXPECTED_HEADERS

FIXTURES = Path(__file__).parent / 'fixtures'
GOOD_NAME = '123456782FEC20251231.txt'


def fixture(case: str) -> Path:
    return FIXTURES / case / GOOD_NAME


def row(num: str = '1', edate: str = '20250310', account: str = '411000', debit: str = '0,00',
        credit: str = '0,00') -> list[str]:
    return ['VE', 'Ventes', num, edate, account, 'Clients', '', '', 'F1', edate, 'Facture', debit, credit,
            '', '', edate, '', '']


def entry(num: str = '1', amount: str = '100,00') -> list[list[str]]:
    return [row(num, debit=amount), row(num, account='706000', credit=amount)]


@pytest.fixture
def write_fec(tmp_path: Path):
    """Write a FEC from rows: write_fec(rows, header=..., sep='|', name=GOOD_NAME, encoding='utf-8')."""
    def _write(rows: list[list[str]], *, header: list[str] | None = None, sep: str = '|',
               name: str = GOOD_NAME, encoding: str = 'utf-8') -> Path:
        lines = [sep.join(header or EXPECTED_HEADERS)] + [sep.join(r) for r in rows]
        path = tmp_path / name
        path.write_bytes(('\r\n'.join(lines) + '\r\n').encode(encoding))
        return path
    return _write
