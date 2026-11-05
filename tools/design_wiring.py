#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Print the first-party component dependency view of the RAES packages as Mermaid.

The Ground Control design review runs this as ``workflow.design.wiring_command``.
grimp parses the package source through ``tools.policy.import_graph`` (ADR-117);
nothing imports or runs the analyzed code. The command reads the source and the
import-linter contracts, writes the graph to stdout and writes no files.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError
from raes_contracts.operational_logging import run_application

from tools.policy.import_graph import analyze_imports
from tools.policy.structural_baseline import IMPORT_CONTRACTS_PATH, parse_import_contracts


def component(module: str, depth: int) -> str:
    """Return the first ``depth`` dotted parts of ``module``."""

    return ".".join(module.split(".")[:depth])


def component_edges(imports: Iterable[tuple[str, str]], depth: int) -> Counter[tuple[str, str]]:
    """Count the module imports between distinct components at ``depth``."""

    if depth < 1:
        raise InvalidInputError("the component depth must be 1 or more")
    edges: Counter[tuple[str, str]] = Counter()
    for importer, imported in imports:
        source, target = component(importer, depth), component(imported, depth)
        if source != target:
            edges[(source, target)] += 1
    return edges


def render_mermaid(components: Iterable[str], edges: Counter[tuple[str, str]]) -> str:
    """Render the components and the counted edges as a Mermaid flowchart in sorted order."""

    names = sorted(set(components) | {name for edge in edges for name in edge})
    node_ids = {name: f"n{index}" for index, name in enumerate(names)}
    lines = ["graph TD"]
    lines.extend(f'    {node_ids[name]}["{name}"]' for name in names)
    lines.extend(
        f"    {node_ids[source]} -->|{count}| {node_ids[target]}" for (source, target), count in sorted(edges.items())
    )
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--depth",
        type=int,
        default=1,
        help="Dotted depth of a component: 1 shows packages, 2 shows their direct children.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = REPO_ROOT / IMPORT_CONTRACTS_PATH
    contracts = parse_import_contracts(config_path.read_text(encoding="utf-8"), IMPORT_CONTRACTS_PATH)
    analysis = analyze_imports(
        [RAES_PACKAGES_ROOT],
        config_path,
        root_packages=contracts.root_packages,
        exclude_type_checking_imports=contracts.exclude_type_checking_imports,
    )
    components = {component(module, args.depth) for module in analysis.modules}
    sys.stdout.write(render_mermaid(components, component_edges(analysis.imports, args.depth)))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
