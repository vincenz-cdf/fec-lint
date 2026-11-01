from __future__ import annotations

import io
import zipfile

import pytest
from conftest import GOOD_NAME, entry, fixture, row

from fec_lint.core import EXPECTED_HEADERS, lint_file, luhn_valid


def rules(result: dict) -> dict[str, int]:
    return {g['rule']: g['count'] for g in result['errors'] + result['warnings']}


# ---------------------------------------------------------------- the 5 fixtures

def test_valid_fixture() -> None:
    result = lint_file(fixture('valid'))
    assert result['ok'] is True
    assert result['errors'] == [] and result['warnings'] == []
    assert result['stats'] == {'encoding': 'utf-8', 'separator': 'pipe', 'columns': 18, 'lineCount': 214}


def test_bad_headers_fixture() -> None:
    result = lint_file(fixture('bad_headers'))
    assert result['ok'] is False
    assert set(rules(result)) == {'header_count', 'header_missing', 'header_unknown', 'header_order'}
    missing = {o['field'] for g in result['errors'] if g['rule'] == 'header_missing' for o in g['occurrences']}
    assert missing == {'EcritureDate', 'Idevise'}


def test_bad_dates_fixture() -> None:
    result = lint_file(fixture('bad_dates'))
    assert result['ok'] is False
    assert rules(result) == {'date_invalid': 3, 'date_format': 3}


@pytest.mark.parametrize('case', ['unbalanced', 'numbering_gap'])
def test_balance_and_numbering_are_not_structural(case: str) -> None:
    # These defects need the full pre-audit: the structure itself is fine.
    assert lint_file(fixture(case))['ok'] is True


# ---------------------------------------------------------------- rules

def test_file_name(write_fec) -> None:
    assert 'file_name' in rules(lint_file(write_fec(entry(), name='export.txt')))
    assert 'siren_checksum' in rules(lint_file(write_fec(entry(), name='123456789FEC20251231.txt')))
    assert 'file_name_date' in rules(lint_file(write_fec(entry(), name='123456782FEC20251332.txt')))
    assert luhn_valid('123456782') and not luhn_valid('123456789')


def test_name_override(write_fec) -> None:
    path = write_fec(entry(), name='upload.txt')
    assert lint_file(path, GOOD_NAME)['ok'] is True


def test_separators(write_fec) -> None:
    assert lint_file(write_fec(entry(), sep='\t'))['stats']['separator'] == 'tab'
    assert rules(lint_file(write_fec(entry(), sep=';'))) == {'separator_semicolon': 1}
    assert rules(lint_file(write_fec(entry(), sep=','))) == {'separator': 1}


def test_encodings(write_fec) -> None:
    rows = entry()
    rows[0][10] = 'Facture réglée €'
    assert lint_file(write_fec(rows, encoding='iso-8859-15'))['stats']['encoding'] == 'iso-8859-15'
    result = lint_file(write_fec(entry(), sep='\t', encoding='utf-16'))
    assert result['ok'] is True
    assert rules(result) == {'encoding_utf16': 1}


def test_header_case_and_order(write_fec) -> None:
    header = list(EXPECTED_HEADERS)
    header[0] = 'journalcode'
    assert rules(lint_file(write_fec(entry(), header=header))) == {'header_case': 1}
    header = list(EXPECTED_HEADERS)
    header[11], header[12] = header[12], header[11]
    assert rules(lint_file(write_fec(entry(), header=header))) == {'header_order': 1}


def test_line_rules(write_fec) -> None:
    rows = entry()
    rows.append(row()[:10])                    # field_count
    rows[0][5] = ''                             # required_field CompteLib
    rows[1][6] = 'CLI001'                       # pair_incomplete CompAuxLib
    rows[1][9] = '10/03/2025'                   # date_format PieceDate
    rows.append(row(edate='20250230'))          # date_invalid x3, zero_line
    rows.append(row(debit='12.50'))             # decimal_point
    rows.append(row(debit='1 000,00'))          # amount_format
    rows.append(row(debit='5,00', credit='5,00'))   # debit_and_credit
    rows.append(row(debit='-5,00'))             # negative_amount
    found = rules(lint_file(write_fec(rows)))
    assert found == {
        'field_count': 1, 'required_field': 1, 'pair_incomplete': 1, 'date_format': 1, 'date_invalid': 3,
        'zero_line': 1, 'decimal_point': 1, 'amount_format': 1, 'debit_and_credit': 1, 'negative_amount': 1,
    }


def test_line_numbers_and_values(write_fec) -> None:
    rows = entry() + [row(edate='20250230')]
    group = next(g for g in lint_file(write_fec(rows))['errors'] if g['rule'] == 'date_invalid')
    assert group['occurrences'][0]['line'] == 4
    assert group['occurrences'][0]['value'] == '20250230'
    assert group['occurrences'][0]['field'] == 'EcritureDate'


def test_occurrences_are_capped(write_fec) -> None:
    rows = [row(str(n), debit='1,00', credit='1,00') for n in range(1, 41)]
    group = lint_file(write_fec(rows))['errors'][0]
    assert group['count'] == 40
    assert len(group['occurrences']) == 20
    assert group['truncated'] is True


# ---------------------------------------------------------------- not a FEC, zip

@pytest.mark.parametrize(('data', 'kind'), [
    (b'%PDF-1.7\n', 'PDF'),
    (b'\x89PNG\r\n\x1a\n', 'PNG'),
    (b'<?xml version="1.0"?>', 'XML'),
    (bytes(range(256)) * 4, 'binary'),
    (b'  \r\n', 'empty'),
])
def test_not_a_fec(tmp_path, data: bytes, kind: str) -> None:
    path = tmp_path / 'upload.bin'
    path.write_bytes(data)
    result = lint_file(path)
    assert result['ok'] is False
    assert kind in result['errors'][0]['occurrences'][0]['message']


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_zip_with_one_fec(tmp_path) -> None:
    path = tmp_path / 'fec.zip'
    path.write_bytes(zip_bytes({f'export/{GOOD_NAME}': fixture('valid').read_bytes()}))
    result = lint_file(path)
    assert result['ok'] is True
    assert result['file'] == GOOD_NAME


def test_zip_problems(tmp_path) -> None:
    for files, expected in (({'a.txt': b'x', 'b.txt': b'y'}, '2 .txt files'),
                            ({'[Content_Types].xml': b'<x/>'}, 'Excel or Word')):
        path = tmp_path / 'fec.zip'
        path.write_bytes(zip_bytes(files))
        assert expected in lint_file(path)['errors'][0]['occurrences'][0]['message']


def test_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        lint_file(tmp_path / 'nope.txt')
