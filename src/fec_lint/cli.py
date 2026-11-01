"""fec-lint command line: lint one or more FEC files, print a summary or JSON."""

from __future__ import annotations

import argparse
import json
import sys

from fec_lint import FULL_PRE_AUDIT_URL, __version__
from fec_lint.core import lint_file


def _print_result(result: dict) -> None:
    status = 'OK' if result['ok'] else 'FAILED'
    stats = result['stats']
    details = ', '.join(f'{k} {v}' for k, v in (('encoding', stats['encoding']), ('separator', stats['separator']),
                                                ('lines', stats['lineCount'])) if v)
    print(f'{result["file"]}: {status}' + (f' ({details})' if details else ''))
    for label, groups in (('error', result['errors']), ('warning', result['warnings'])):
        for group in groups:
            first = group['occurrences'][0] if group['occurrences'] else {}
            lines = [str(o['line']) for o in group['occurrences'] if o.get('line')]
            where = f' - line(s) {", ".join(lines[:10])}{"..." if group["truncated"] or len(lines) > 10 else ""}' if lines else ''
            print(f'  {label} {group["rule"]} x{group["count"]}: {first.get("message", "")}{where}')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='fec-lint',
        description='Structural check of French FEC files: name, encoding, separator, 18 headers, field formats.',
    )
    parser.add_argument('files', nargs='+', help='FEC files (.txt, or a .zip holding one)')
    parser.add_argument('--json', action='store_true', help='print the full result as JSON')
    parser.add_argument('--name', help='file name to check against SIRENFECAAAAMMJJ.txt (one file only)')
    parser.add_argument('--quiet', action='store_true', help='hide the closing line about the full pre-audit')
    parser.add_argument('--version', action='version', version=f'fec-lint {__version__}')
    args = parser.parse_args(argv)
    if args.name and len(args.files) > 1:
        parser.error('--name works with a single file')

    results = []
    for path in args.files:
        try:
            results.append(lint_file(path, args.name))
        except OSError as e:
            print(f'{path}: cannot read ({e.strerror or e})', file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(results[0] if len(results) == 1 else results, ensure_ascii=False, indent=2))
    else:
        for result in results:
            _print_result(result)

    all_ok = all(r['ok'] for r in results)
    if not args.quiet and not args.json:
        verdict = 'Structure OK.' if all_ok else 'Structure has errors.'
        print(f'{verdict} Full pre-audit (balance, numbering, risk signals): {FULL_PRE_AUDIT_URL}')
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
