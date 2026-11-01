"""Structural lint for French FEC files (art. A47 A-1 du Livre des procédures fiscales).

Checks what a file looks like, line by line: file name, encoding, separator, the 18 headers and the
format of each field. It does not check balance, entry numbering or audit-risk patterns; the full
FEC Checker on Apify does (https://apify.com/highfiddle/fec-checker).

The file is streamed, so memory stays flat whatever its size.
"""

from __future__ import annotations

import codecs
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

EXPECTED_HEADERS = (
    'JournalCode', 'JournalLib', 'EcritureNum', 'EcritureDate', 'CompteNum', 'CompteLib',
    'CompAuxNum', 'CompAuxLib', 'PieceRef', 'PieceDate', 'EcritureLib', 'Debit', 'Credit',
    'EcritureLet', 'DateLet', 'ValidDate', 'Montantdevise', 'Idevise',
)
REQUIRED_FIELDS = (
    'JournalCode', 'JournalLib', 'EcritureNum', 'EcritureDate', 'CompteNum', 'CompteLib',
    'PieceRef', 'PieceDate', 'EcritureLib', 'Debit', 'Credit', 'ValidDate',
)
DATE_FIELDS = ('EcritureDate', 'PieceDate', 'DateLet', 'ValidDate')
FIELD_PAIRS = (('CompAuxNum', 'CompAuxLib'), ('EcritureLet', 'DateLet'), ('Montantdevise', 'Idevise'))

FILE_NAME_RE = re.compile(r'^(\d{9})FEC(\d{8})\.txt$', re.IGNORECASE)
AMOUNT_RE = re.compile(r'^(-?)(\d+)(?:,(\d{1,2}))?$')
DOT_AMOUNT_RE = re.compile(r'^(-?)(\d+)\.(\d{1,2})$')

MAX_OCCURRENCES = 20
MAX_VALUE_CHARS = 60
SNIFF_BYTES = 64 * 1024

ERROR = 'error'
WARNING = 'warning'

MESSAGES = {
    'not_a_fec': (ERROR, 'The file is not a FEC text file: {kind}.'),
    'file_name': (ERROR, 'The file name must follow the SIRENFECAAAAMMJJ.txt pattern.'),
    'file_name_date': (ERROR, 'The closing date in the file name is not a valid date.'),
    'siren_checksum': (WARNING, 'The SIREN in the file name fails the Luhn checksum.'),
    'encoding_utf16': (WARNING, 'The file is UTF-16 encoded; only ASCII, ISO-8859-15 and UTF-8 are expected.'),
    'separator': (ERROR, 'No separator found: the header line must be tab- or pipe-separated.'),
    'separator_semicolon': (ERROR, 'The file is semicolon-separated; only tab or pipe (|) is allowed.'),
    'header_count': (ERROR, 'The header must contain exactly 18 columns.'),
    'header_missing': (ERROR, 'Mandatory column missing from the header: {field}.'),
    'header_unknown': (ERROR, 'Header column not defined by article A47 A-1.'),
    'header_order': (ERROR, 'The header columns are not in the required order.'),
    'header_case': (ERROR, 'Column name has the wrong letter case: {field}.'),
    'empty_line': (WARNING, 'Empty line.'),
    'field_count': (ERROR, 'The line does not have the same number of fields as the header.'),
    'required_field': (ERROR, 'Mandatory field is empty: {field}.'),
    'pair_incomplete': (ERROR, 'Fields {pair} must be filled together; {field} is empty.'),
    'date_format': (ERROR, 'Wrong date format in {field} (expected AAAAMMJJ).'),
    'date_invalid': (ERROR, 'Non-existent date in {field}.'),
    'amount_format': (ERROR, 'Unreadable amount in {field} (digits and a decimal comma only).'),
    'decimal_point': (ERROR, 'The amount in {field} uses a decimal point instead of a comma.'),
    'debit_and_credit': (ERROR, 'The line has both a debit and a credit amount.'),
    'zero_line': (WARNING, 'Line with zero debit and zero credit.'),
    'negative_amount': (WARNING, 'Negative amount in {field}.'),
}

BINARY_MAGIC = (
    (b'%PDF', 'a PDF document'),
    (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 'an old Excel or Word file'),
    (b'\x89PNG', 'a PNG image'),
    (b'\xff\xd8\xff', 'a JPEG image'),
    (b'\x1f\x8b', 'a gzip archive'),
    (b'<?xml', 'an XML file (only the flat-file FEC is supported)'),
)


@dataclass
class _Rule:
    count: int = 0
    occurrences: list[dict] = field(default_factory=list)


class _Issues:
    def __init__(self) -> None:
        self.rules: dict[str, _Rule] = {}

    def add(self, rule: str, line: int | None = None, field_name: str | None = None,
            value: str | None = None, **params: str) -> None:
        entry = self.rules.setdefault(rule, _Rule())
        entry.count += 1
        if len(entry.occurrences) < MAX_OCCURRENCES:
            occurrence = {'line': line, 'field': field_name}
            if value is not None:
                occurrence['value'] = value[:MAX_VALUE_CHARS]
            occurrence['message'] = MESSAGES[rule][1].format(field=field_name or '?', **params)
            entry.occurrences.append(occurrence)


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def parse_yyyymmdd(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def utf16_variant(head: bytes) -> str | None:
    if head.startswith((b'\xff\xfe', b'\xfe\xff')):
        return 'utf-16'
    sample = head[:4096]
    if len(sample) < 16:
        return None
    half = len(sample) / 2
    even_zeros, odd_zeros = sample[0::2].count(0), sample[1::2].count(0)
    if odd_zeros > 0.4 * half and even_zeros < 0.05 * half:
        return 'utf-16-le'
    if even_zeros > 0.4 * half and odd_zeros < 0.05 * half:
        return 'utf-16-be'
    return None


def _detect_encoding(path: Path) -> str:
    with path.open('rb') as f:
        utf16 = utf16_variant(f.read(4096))
    if utf16:
        return utf16
    decoder = codecs.getincrementaldecoder('utf-8')()
    try:
        with path.open('rb') as f:
            while chunk := f.read(1 << 20):
                decoder.decode(chunk)
            decoder.decode(b'', final=True)
    except UnicodeDecodeError:
        return 'iso-8859-15'
    return 'utf-8'


def _binary_kind(head: bytes) -> str | None:
    for magic, kind in BINARY_MAGIC:
        if head.startswith(magic):
            return kind
    if b'\x00' in head and utf16_variant(head) is None:
        return 'a binary file'
    return None


def _unzip(path: Path, workdir: Path) -> tuple[Path | None, str | None, str | None]:
    """(file, name inside the zip, problem). A zip must hold exactly one .txt FEC."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = [i for i in archive.infolist() if not i.is_dir()]
            if any(i.filename == '[Content_Types].xml' for i in infos):
                return None, None, 'an Excel or Word document (.xlsx/.docx)'
            fecs = [i for i in infos if i.filename.lower().endswith('.txt') and not Path(i.filename).name.startswith('.')]
            if len(fecs) != 1:
                return None, None, f'a zip archive with {len(fecs)} .txt files (exactly one is expected)'
            target = workdir / 'unzipped.fec'
            with archive.open(fecs[0]) as src, target.open('wb') as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            return target, Path(fecs[0].filename).name, None
    except (zipfile.BadZipFile, RuntimeError):
        return None, None, 'a zip archive that cannot be opened'


def _check_file_name(name: str, issues: _Issues) -> None:
    match = FILE_NAME_RE.match(name)
    if not match:
        issues.add('file_name', value=name)
        return
    siren, closing = match.groups()
    if not luhn_valid(siren):
        issues.add('siren_checksum', value=siren)
    if parse_yyyymmdd(closing) is None:
        issues.add('file_name_date', value=closing)


def _check_header(names: list[str], issues: _Issues) -> dict[str, int]:
    names = [n.strip() for n in names]
    if tuple(names) == EXPECTED_HEADERS:
        return {n: i for i, n in enumerate(names)}
    if len(names) != len(EXPECTED_HEADERS):
        issues.add('header_count', 1, value=str(len(names)))
    exact = {n: i for i, n in enumerate(names)}
    lowered = {n.lower(): i for i, n in enumerate(names)}
    columns: dict[str, int] = {}
    for expected in EXPECTED_HEADERS:
        if expected in exact:
            columns[expected] = exact[expected]
        elif expected.lower() in lowered:
            columns[expected] = lowered[expected.lower()]
            issues.add('header_case', 1, expected, names[columns[expected]])
        else:
            issues.add('header_missing', 1, expected)
    known = {e.lower() for e in EXPECTED_HEADERS}
    for name in names:
        if name.lower() not in known:
            issues.add('header_unknown', 1, value=name)
    order = [n for n, _ in sorted(columns.items(), key=lambda kv: kv[1])]
    if order != [n for n in EXPECTED_HEADERS if n in columns]:
        issues.add('header_order', 1, value=','.join(order))
    return columns


def _amount(value: str, field_name: str, line: int, issues: _Issues) -> int | None:
    match = AMOUNT_RE.match(value)
    if match is None:
        match = DOT_AMOUNT_RE.match(value)
        if match is None:
            issues.add('amount_format', line, field_name, value)
            return None
        issues.add('decimal_point', line, field_name, value)
    sign, units, decimals = match.groups()
    cents = int(units) * 100 + int((decimals or '0').ljust(2, '0'))
    return -cents if sign else cents


def _check_rows(f, separator: str, columns: dict[str, int], width: int, issues: _Issues) -> tuple[int, int]:
    add = issues.add
    required = [(n, columns[n]) for n in REQUIRED_FIELDS if n in columns]
    dates = [(n, columns[n]) for n in DATE_FIELDS if n in columns]
    pairs = [(a, b) for a, b in FIELD_PAIRS if a in columns and b in columns]
    i_debit, i_credit, i_fx = columns.get('Debit'), columns.get('Credit'), columns.get('Montantdevise')
    date_cache: dict[str, int] = {}  # 0 = ok, 1 = bad format, 2 = non-existent
    line_no, rows = 1, 0
    for raw in f:
        line_no += 1
        text = raw.rstrip('\r\n')
        if not text.strip():
            add('empty_line', line_no)
            continue
        rows += 1
        row = text.split(separator)
        if len(row) != width:
            add('field_count', line_no, value=str(len(row)))
            continue
        row = [v.strip() for v in row]
        for name, idx in required:
            if not row[idx]:
                add('required_field', line_no, name)
        for a, b in pairs:
            if bool(row[columns[a]]) != bool(row[columns[b]]):
                add('pair_incomplete', line_no, b if row[columns[a]] else a, pair=f'{a}/{b}')
        for name, idx in dates:
            value = row[idx]
            if not value:
                continue
            status = date_cache.get(value)
            if status is None:
                status = 1 if len(value) != 8 or not value.isdigit() else (0 if parse_yyyymmdd(value) else 2)
                if len(date_cache) < 100_000:
                    date_cache[value] = status
            if status == 1:
                add('date_format', line_no, name, value)
            elif status == 2:
                add('date_invalid', line_no, name, value)
        if i_debit is not None and i_credit is not None:
            debit = _amount(row[i_debit], 'Debit', line_no, issues) if row[i_debit] else None
            credit = _amount(row[i_credit], 'Credit', line_no, issues) if row[i_credit] else None
            if debit is not None and credit is not None:
                if debit < 0 or credit < 0:
                    add('negative_amount', line_no, 'Debit' if debit < 0 else 'Credit')
                if debit and credit:
                    add('debit_and_credit', line_no)
                elif not debit and not credit:
                    add('zero_line', line_no)
        if i_fx is not None and row[i_fx] and not (AMOUNT_RE.match(row[i_fx]) or DOT_AMOUNT_RE.match(row[i_fx])):
            add('amount_format', line_no, 'Montantdevise', row[i_fx])
    return line_no, rows


def _result(name: str, issues: _Issues, stats: dict) -> dict:
    groups: dict[str, list[dict]] = {ERROR: [], WARNING: []}
    for rule, entry in issues.rules.items():
        severity = MESSAGES[rule][0]
        groups[severity].append({
            'rule': rule,
            'count': entry.count,
            'truncated': entry.count > len(entry.occurrences),
            'occurrences': entry.occurrences,
        })
    return {
        'ok': not groups[ERROR],
        'file': name,
        'errors': groups[ERROR],
        'warnings': groups[WARNING],
        'stats': stats,
    }


def lint_file(path: str | Path, file_name: str | None = None) -> dict:
    """Lint one FEC file. Returns {ok, file, errors[], warnings[], stats}.

    `ok` is True when no structural error was found. `file_name` overrides the name used for the
    SIRENFECAAAAMMJJ.txt rule. A .zip holding exactly one .txt FEC is unpacked first.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'No such file: {path}')
    issues = _Issues()
    name = file_name or path.name
    stats: dict = {'encoding': None, 'separator': None, 'columns': None, 'lineCount': 0}

    with tempfile.TemporaryDirectory(prefix='fec-lint-') as workdir:
        with path.open('rb') as f:
            head = f.read(SNIFF_BYTES)
        if head.startswith(b'PK\x03\x04'):
            inner, inner_name, problem = _unzip(path, Path(workdir))
            if problem:
                issues.add('not_a_fec', kind=problem)
                return _result(name, issues, stats)
            path, name = inner, file_name or inner_name
            with path.open('rb') as f:
                head = f.read(SNIFF_BYTES)
        if not head.strip():
            issues.add('not_a_fec', kind='an empty file')
            return _result(name, issues, stats)
        kind = _binary_kind(head)
        if kind:
            issues.add('not_a_fec', kind=kind)
            return _result(name, issues, stats)

        _check_file_name(name, issues)
        encoding = _detect_encoding(path)
        stats['encoding'] = encoding
        if encoding.startswith('utf-16'):
            issues.add('encoding_utf16', value=encoding)

        with path.open('r', encoding=encoding, newline='') as f:
            header = f.readline().lstrip('﻿').rstrip('\r\n')
            if '\t' in header:
                separator = '\t'
            elif '|' in header:
                separator = '|'
            elif header.count(';') >= len(EXPECTED_HEADERS) // 2:
                issues.add('separator_semicolon', 1)
                return _result(name, issues, stats)
            else:
                issues.add('separator', 1)
                return _result(name, issues, stats)
            stats['separator'] = 'tab' if separator == '\t' else 'pipe'
            names = header.split(separator)
            stats['columns'] = len(names)
            columns = _check_header(names, issues)
            if columns:
                _, rows = _check_rows(f, separator, columns, len(names), issues)
                stats['lineCount'] = rows
    return _result(name, issues, stats)
