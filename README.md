# fec-lint

**[English](#english) · [Français](#français)**

<!-- mcp-name: io.github.vincenz-cdf/fec-lint -->

> **Technical check, not tax advice.** fec-lint checks the structure of a file against the published FEC format. It does not certify a file or replace an accountant's review.
>
> **Contrôle technique, pas un conseil fiscal.** fec-lint vérifie la structure d'un fichier au regard du format FEC publié. Il ne certifie pas un fichier et ne remplace pas la revue d'un expert-comptable.

---

## English

**Free structural linter for French FEC files (*Fichier des Écritures Comptables*, art. A47 A-1 LPF), as a command line tool and an MCP server.**

### Install

```bash
pipx install fec-lint
```

### Command line

```bash
fec-lint 123456782FEC20251231.txt
```

```text
123456782FEC20251231.txt: FAILED (encoding utf-8, separator pipe, lines 214)
  error date_invalid x3: Non-existent date in EcritureDate. - line(s) 21, 22, 23
  error date_format x3: Wrong date format in EcritureDate (expected AAAAMMJJ). - line(s) 64, 65, 66
Structure has errors. Full pre-audit (balance, numbering, risk signals): https://apify.com/highfiddle/fec-checker
```

- `--json` prints the full result: `{ok, file, errors[], warnings[], stats}`.
- `--name 123456782FEC20251231.txt` sets the name checked against `SIRENFECAAAAMMJJ.txt`.
- `--quiet` hides the last line.
- Exit code: `0` when the structure is OK, `1` on errors, `2` when a file cannot be read. Several files can be given at once.
- A `.zip` holding exactly one `.txt` FEC is unpacked first.

### MCP server

Add it to your MCP client (Claude Desktop, Claude Code, Cursor…):

```json
{
    "mcpServers": {
        "fec-lint": {
            "command": "uvx",
            "args": ["--from", "fec-lint", "fec-lint-mcp"]
        }
    }
}
```

Without `uv`, install with `pipx install fec-lint` and use `"command": "fec-lint-mcp"`. The server exposes one tool, `lint_fec(path)`, which takes a local file path and returns the same JSON as `--json`.

### Free vs full pre-audit

| Check | fec-lint (free) | [FEC Checker on Apify](https://apify.com/highfiddle/fec-checker) |
|---|---|---|
| File name `SIRENFECAAAAMMJJ.txt`, SIREN key | ✅ | ✅ |
| Encoding, separator, 18 headers | ✅ | ✅ |
| Field formats: dates, amounts, mandatory fields, pairs | ✅ | ✅ |
| Balance per entry and for the whole file | — | ✅ |
| EcritureNum gaps and duplicates, ValidDate chronology | — | ✅ |
| Risk signals: weekends, holidays, round amounts, Benford, cash 53x, suspense 471, after year end | — | ✅ |
| Verdict, 0-100 score, AI-written fix list (FR/EN) | — | ✅ |
| Runs | locally, nothing leaves your machine | on Apify, pay per file |

---

## Français

**Linter structurel gratuit pour les FEC (*Fichier des Écritures Comptables*, art. A47 A-1 LPF), en ligne de commande et en serveur MCP.**

### Installation

```bash
pipx install fec-lint
```

### Ligne de commande

```bash
fec-lint 123456782FEC20251231.txt
```

- `--json` affiche le résultat complet : `{ok, file, errors[], warnings[], stats}`.
- `--name 123456782FEC20251231.txt` indique le nom à contrôler selon `SIRENFECAAAAMMJJ.txt`.
- `--quiet` masque la dernière ligne.
- Code de sortie : `0` si la structure est correcte, `1` en cas d'erreur, `2` si un fichier est illisible. Plusieurs fichiers peuvent être passés à la fois.
- Un `.zip` contenant un seul FEC `.txt` est décompressé d'abord.

Les messages sont en anglais ; les codes de règle (`date_invalid`, `header_missing`…) sont stables.

### Serveur MCP

Ajoutez-le à votre client MCP (Claude Desktop, Claude Code, Cursor…) avec la configuration ci-dessus. L'outil `lint_fec(path)` prend le chemin d'un fichier local et renvoie le même JSON que `--json`.

### Gratuit ou pré-audit complet

| Contrôle | fec-lint (gratuit) | [FEC Checker sur Apify](https://apify.com/highfiddle/fec-checker) |
|---|---|---|
| Nom `SIRENFECAAAAMMJJ.txt`, clé du SIREN | ✅ | ✅ |
| Encodage, séparateur, 18 colonnes | ✅ | ✅ |
| Formats : dates, montants, champs obligatoires, couples de champs | ✅ | ✅ |
| Équilibre par écriture et du fichier | — | ✅ |
| Ruptures et doublons d'EcritureNum, chronologie de ValidDate | — | ✅ |
| Signaux de risque : week-ends, jours fériés, montants ronds, Benford, caisse 53x, attente 471, après clôture | — | ✅ |
| Verdict, score 0-100, plan de correction rédigé par IA (FR/EN) | — | ✅ |
| Exécution | en local, rien ne quitte votre machine | sur Apify, paiement par fichier |

---

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[test]"   # Windows: .venv\Scripts\pip
pytest
```

The fixtures in `tests/fixtures/` are synthetic FEC files (fictitious SIREN 123456782). MIT license.
