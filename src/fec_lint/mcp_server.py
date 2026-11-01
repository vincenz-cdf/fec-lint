"""fec-lint MCP server (stdio): exposes the structural check as the `lint_fec` tool."""

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from fec_lint import __version__
from fec_lint.core import lint_file

mcp = MCPServer('fec-lint', version=__version__)


DESCRIPTION = (
    "Check a French FEC file's name, encoding, separator, 18 headers and field formats. "
    '`path` is a local path to the FEC (.txt, or a .zip holding one). Returns '
    '{ok, file, errors[], warnings[], stats}; each error has a rule code, a count and line numbers. '
    'Structural check only; for entry balance, numbering and audit-risk analysis, use the full '
    'FEC Checker on Apify: https://apify.com/highfiddle/fec-checker'
)


@mcp.tool(description=DESCRIPTION,
          annotations=ToolAnnotations(title='Lint a FEC file', readOnlyHint=True, openWorldHint=False))
def lint_fec(path: str) -> dict:
    return lint_file(path)


def main() -> None:
    mcp.run()


if __name__ == '__main__':
    main()
