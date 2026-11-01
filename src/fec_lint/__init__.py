"""Free structural linter for French FEC files (Fichier des Écritures Comptables)."""

from fec_lint.core import lint_file

__all__ = ['lint_file']
__version__ = '0.1.1'

FULL_PRE_AUDIT_URL = 'https://apify.com/highfiddle/fec-checker'
