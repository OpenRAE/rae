#!/usr/bin/env python3
"""Validate the curated public documentation source and generated inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from defusedxml import ElementTree

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.policy.common import PolicyFailure, failures_to_json, safe_repo_path  # noqa: E402

PUBLIC_DOCS_ROOT = Path("docs/public")
MAX_SOURCE_BYTES = 1_000_000
MAX_INDEX_BYTES = 5_000_000
MAX_REDIRECT_BYTES = 100_000
REQUIRED_PUBLIC_PAGES = (
    "index.md",
    "quickstart.md",
    "concepts.md",
    "tutorials/first-scenario.md",
    "sdl/index.md",
    "guides/python.md",
    "guides/cli.md",
    "backends.md",
    "research.md",
    "limitations.md",
    "contributing.md",
    "support.md",
    "citation.md",
)
REQUIRED_PUBLIC_REDIRECTS = {
    "explain/getting-started": "../quickstart.html",
    "explain/reference/backend-conformance": "../../backends.html",
    "explain/reference/canonical-reference-map": "../../concepts.html",
    "explain/reference/documentation-style-guide": "../../contributing.html",
    "explain/reference/glossary": "../../concepts.html",
    "explain/sdl/index": "../../sdl/index.html",
    "explain/sdl/limitations": "../../limitations.html",
    "explain/sdl/lineage": "../../research.html",
    "explain/sdl/related-work-comparison": "../../research.html",
    "explain/sdl/runtime-architecture": "../../backends.html",
    "explain/sdl/scientific-scenario-completeness": "../../research.html",
    "specs/formal": "../research.html",
}
SOURCE_SUFFIXES = frozenset({".md", ".rst"})
GENERATED_HTML_ROUTES = frozenset(
    {
        "genindex.html",
        "py-modindex.html",
        "search.html",
    }
)
LOCAL_DIRECTIVE_PATTERNS = (
    re.compile(
        r"^\s*(?:```\{|\.\.\s+)(?:include|literalinclude|download)(?:\}|::)\s+([^\s]+)",
        re.MULTILINE | re.IGNORECASE,
    ),
    re.compile(r"\{download\}`(?:[^`<]*<)?([^>`]+)>?`", re.IGNORECASE),
)
# Directory names and file names that only ever hold internal records.
INTERNAL_RECORD_DIRECTORIES = frozenset({"adrs", "decisions", "development"})
ADR_FILENAME = re.compile(r"adr-\d{3,}-", re.IGNORECASE)
# Markdown inline links and images, then reference-style link definitions.
MARKDOWN_LINK_PATTERNS = (
    re.compile(r"\]\(\s*<?([^)\s>]+)"),
    re.compile(r"^[ \t]*\[(?!\^)[^\]\n]+\]:[ \t]*<?([^\s>]+)", re.MULTILINE),
)
# Sphinx copies download and image targets here, even from outside the source root.
PUBLISHED_ASSET_DIRECTORIES = ("_downloads", "_images")


def _public_path(repo_root: Path) -> Path | None:
    return safe_repo_path(repo_root, PUBLIC_DOCS_ROOT.as_posix())


def _relative(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _source_paths(public_root: Path) -> list[Path]:
    return sorted(
        path
        for path in public_root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.suffix.casefold() in SOURCE_SUFFIXES
    )


def _redirects_path(public_root: Path) -> Path:
    return public_root / "redirects.json"


def _load_redirects(public_root: Path) -> dict[str, str]:
    path = _redirects_path(public_root)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_REDIRECT_BYTES:
        raise ValueError("redirect map is missing, unsafe, or exceeds the inspection limit")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(
        isinstance(source, str) and isinstance(target, str) for source, target in payload.items()
    ):
        raise ValueError("redirect map must contain string source and target pairs")
    return payload


def _route_for_source(public_root: Path, source: Path) -> str:
    relative = source.relative_to(public_root)
    return relative.with_suffix(".html").as_posix()


def _docname_for_source(public_root: Path, source: Path) -> str:
    return source.relative_to(public_root).with_suffix("").as_posix()


def _directive_targets(text: str) -> list[str]:
    return [
        match.group(1).strip().strip("\"'") for pattern in LOCAL_DIRECTIVE_PATTERNS for match in pattern.finditer(text)
    ]


def _target_is_contained(public_root: Path, source: Path, target: str) -> bool:
    if "://" in target or target.startswith(("mailto:", "#")):
        return True
    clean_target = target.split("#", 1)[0]
    if not clean_target:
        return True
    candidate = Path(clean_target)
    if candidate.is_absolute():
        return False
    try:
        resolved = (source.parent / candidate).resolve()
        resolved.relative_to(public_root.resolve())
    except (OSError, ValueError):
        return False
    return True


def evaluate_public_sources(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    """Return publication-boundary failures for checked-in public sources."""

    failures: list[PolicyFailure] = []
    public_root = _public_path(repo_root)
    if public_root is None or not public_root.is_dir():
        return [
            PolicyFailure(
                "public-docs-root",
                "the curated public documentation root is missing or unsafe",
                PUBLIC_DOCS_ROOT.as_posix(),
            )
        ]

    for relative_path in REQUIRED_PUBLIC_PAGES:
        path = public_root / relative_path
        if not path.is_file() or path.is_symlink():
            failures.append(
                PolicyFailure(
                    "public-docs-information-architecture",
                    "required public page is missing",
                    (PUBLIC_DOCS_ROOT / relative_path).as_posix(),
                )
            )

    redirects_path = _redirects_path(public_root)
    try:
        redirects = _load_redirects(public_root)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        failures.append(
            PolicyFailure(
                "public-docs-redirect-map",
                str(exc),
                _relative(repo_root, redirects_path),
            )
        )
    else:
        if redirects != REQUIRED_PUBLIC_REDIRECTS:
            failures.append(
                PolicyFailure(
                    "public-docs-redirect-map",
                    "redirect map must preserve the complete established public-route contract",
                    _relative(repo_root, redirects_path),
                )
            )

    for current, directories, files in os.walk(public_root, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            path = current_path / name
            if path.is_symlink():
                failures.append(
                    PolicyFailure(
                        "public-docs-symlink",
                        "public documentation must not contain symlinks",
                        _relative(repo_root, path),
                    )
                )

    for source in _source_paths(public_root):
        relative_path = _relative(repo_root, source)
        try:
            if source.stat().st_size > MAX_SOURCE_BYTES:
                failures.append(
                    PolicyFailure(
                        "public-docs-source-size",
                        f"public source exceeds the {MAX_SOURCE_BYTES}-byte inspection limit",
                        relative_path,
                    )
                )
                continue
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            failures.append(
                PolicyFailure(
                    "public-docs-source-readable",
                    "public source must be readable UTF-8 text",
                    relative_path,
                )
            )
            continue
        if any(not _target_is_contained(public_root, source, target) for target in _directive_targets(text)):
            failures.append(
                PolicyFailure(
                    "public-docs-source-escape",
                    "include, literalinclude, and download targets must stay inside docs/public",
                    relative_path,
                )
            )

    return sorted(failures, key=lambda failure: (failure.path or "", failure.rule_id))


def _is_internal_record(relative: Path) -> bool:
    if INTERNAL_RECORD_DIRECTORIES.intersection(relative.parts[:-1]):
        return True
    return relative.suffix.casefold() in SOURCE_SUFFIXES and ADR_FILENAME.match(relative.name) is not None


def _bounded_text(source: Path) -> str:
    # evaluate_public_sources reports oversized or unreadable sources.
    try:
        if source.stat().st_size > MAX_SOURCE_BYTES:
            return ""
        return source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _escaping_link_targets(public_root: Path, source: Path) -> list[str]:
    text = _bounded_text(source)
    return [
        match.group(1)
        for pattern in MARKDOWN_LINK_PATTERNS
        for match in pattern.finditer(text)
        if not _target_is_contained(public_root, source, match.group(1))
    ]


def evaluate_public_boundary(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    """Return failures for internal records under docs/public and Markdown links that escape it.

    A Markdown link to a file outside the source root that is not a page passes
    the warning-strict build: Sphinx copies the file into ``_downloads/`` and
    publishes it. evaluate_public_sources reports a missing root.
    """

    public_root = _public_path(repo_root)
    if public_root is None or not public_root.is_dir():
        return []
    failures = [
        PolicyFailure(
            "public-docs-internal-record",
            "decision records and development notes must stay outside docs/public",
            _relative(repo_root, path),
        )
        for path in sorted(public_root.rglob("*"))
        if path.is_file() and _is_internal_record(path.relative_to(public_root))
    ]
    failures.extend(
        PolicyFailure(
            "public-docs-link-escape",
            f"link target {target!r} resolves outside docs/public; link repository files by absolute URL",
            _relative(repo_root, source),
        )
        for source in _source_paths(public_root)
        if source.suffix.casefold() == ".md"
        for target in _escaping_link_targets(public_root, source)
    )
    return failures


def _search_docnames(search_index_path: Path) -> set[str]:
    if not search_index_path.is_file() or search_index_path.stat().st_size > MAX_INDEX_BYTES:
        raise ValueError("searchindex.js is missing or exceeds the inspection limit")
    text = search_index_path.read_text(encoding="utf-8")
    match = re.fullmatch(r"\s*Search\.setIndex\((.*)\)\s*;?\s*", text, re.DOTALL)
    if match is None:
        raise ValueError("searchindex.js does not contain a recognized Sphinx index")
    payload = json.loads(match.group(1))
    docnames = payload.get("docnames")
    if not isinstance(docnames, list) or not all(isinstance(item, str) for item in docnames):
        raise ValueError("searchindex.js has no string docnames inventory")
    return set(docnames)


def _sitemap_routes(sitemap_path: Path) -> set[str]:
    tree = ElementTree.parse(sitemap_path)
    routes: set[str] = set()
    for location in tree.findall(".//{*}loc"):
        if location.text:
            routes.add(urlparse(location.text).path.strip("/") or "index.html")
    return routes


def evaluate_public_output(repo_root: Path, output_root: Path) -> list[PolicyFailure]:
    """Return failures when generated routes exceed the curated source inventory."""

    public_root = _public_path(repo_root)
    if public_root is None or not public_root.is_dir():
        return evaluate_public_sources(repo_root)
    try:
        output_root.resolve().relative_to(repo_root.resolve())
    except (OSError, ValueError):
        return [
            PolicyFailure(
                "public-docs-output-root",
                "generated documentation output must stay inside the repository",
                output_root.as_posix(),
            )
        ]

    expected_routes = {_route_for_source(public_root, source) for source in _source_paths(public_root)}
    redirect_routes = {f"{source}.html" for source in REQUIRED_PUBLIC_REDIRECTS}
    expected_docnames = {_docname_for_source(public_root, source) for source in _source_paths(public_root)}
    failures: list[PolicyFailure] = []
    actual_routes = {
        path.relative_to(output_root).as_posix()
        for path in output_root.rglob("*.html")
        if "_static" not in path.relative_to(output_root).parts
    }
    for route in sorted(actual_routes - expected_routes - redirect_routes - GENERATED_HTML_ROUTES):
        failures.append(
            PolicyFailure(
                "public-docs-output-route",
                "generated HTML route has no source beneath docs/public",
                route,
            )
        )

    for source, target in REQUIRED_PUBLIC_REDIRECTS.items():
        route = f"{source}.html"
        redirect_path = output_root / route
        try:
            if not redirect_path.is_file() or redirect_path.stat().st_size > MAX_REDIRECT_BYTES:
                raise ValueError("redirect page is missing or exceeds the inspection limit")
            redirect_html = redirect_path.read_text(encoding="utf-8")
            normalized_html = re.sub(r"\s+", " ", redirect_html.casefold())
            if 'http-equiv="refresh"' not in normalized_html or f"url={target.casefold()}" not in normalized_html:
                raise ValueError("redirect page does not point to its curated public target")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            failures.append(
                PolicyFailure(
                    "public-docs-redirect-output",
                    str(exc),
                    route,
                )
            )

    try:
        search_docnames = _search_docnames(output_root / "searchindex.js")
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        failures.append(
            PolicyFailure(
                "public-docs-search-index",
                str(exc),
                (output_root / "searchindex.js").as_posix(),
            )
        )
    else:
        for docname in sorted(search_docnames - expected_docnames):
            failures.append(
                PolicyFailure(
                    "public-docs-search-route",
                    "search document has no source beneath docs/public",
                    docname,
                )
            )

    sitemap_path = output_root / "sitemap.xml"
    if sitemap_path.is_file():
        try:
            sitemap_routes = _sitemap_routes(sitemap_path)
        except (OSError, ElementTree.ParseError) as exc:
            failures.append(
                PolicyFailure(
                    "public-docs-sitemap",
                    f"invalid sitemap: {exc}",
                    sitemap_path.as_posix(),
                )
            )
        else:
            allowed_routes = expected_routes | redirect_routes | GENERATED_HTML_ROUTES
            mappings: list[tuple[str, str, str]] = []
            unexpected_routes: set[str] = set()
            for route in sitemap_routes:
                matches = [allowed for allowed in allowed_routes if route == allowed or route.endswith(f"/{allowed}")]
                if not matches:
                    unexpected_routes.add(route)
                    continue
                matched = max(matches, key=len)
                mappings.append((route, matched, route[: -len(matched)]))
            expected_prefixes = {prefix for _route, matched, prefix in mappings if matched in expected_routes}
            if len(expected_prefixes) > 1:
                common_prefix = max(
                    expected_prefixes,
                    key=lambda prefix: sum(item_prefix == prefix for _, _, item_prefix in mappings),
                )
                unexpected_routes.update(
                    route
                    for route, matched, prefix in mappings
                    if matched in expected_routes and prefix != common_prefix
                )
            represented = {matched for _, matched, _ in mappings if matched in expected_routes}
            if expected_routes - represented:
                unexpected_routes.add("missing public source routes")
            for route in sorted(unexpected_routes):
                failures.append(
                    PolicyFailure(
                        "public-docs-sitemap-route",
                        "sitemap route has no source beneath docs/public",
                        route,
                    )
                )
    return failures


def _file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def evaluate_published_assets(repo_root: Path, output_root: Path) -> list[PolicyFailure]:
    """Return failures when a published download or image is not a copy of a docs/public file."""

    public_root = _public_path(repo_root)
    if public_root is None or not public_root.is_dir():
        return []
    resolved_output = output_root.resolve()
    public_digests = {
        _file_digest(path)
        for path in public_root.rglob("*")
        if path.is_file() and not path.is_symlink() and resolved_output not in path.resolve().parents
    }
    return [
        PolicyFailure(
            "public-docs-output-asset",
            "published download or image has no byte-identical source beneath docs/public",
            asset.relative_to(output_root).as_posix(),
        )
        for directory in PUBLISHED_ASSET_DIRECTORIES
        for asset in sorted((output_root / directory).rglob("*"))
        if asset.is_file() and _file_digest(asset) not in public_digests
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Also validate a generated Sphinx HTML directory.")
    parser.add_argument("--json", action="store_true", help="Emit failures as JSON.")
    args = parser.parse_args()

    failures = [*evaluate_public_sources(REPO_ROOT), *evaluate_public_boundary(REPO_ROOT)]
    if not failures and args.output is not None:
        failures.extend(evaluate_public_output(REPO_ROOT, args.output))
        failures.extend(evaluate_published_assets(REPO_ROOT, args.output))
    if args.json:
        print(failures_to_json(failures))
    else:
        for failure in failures:
            print(failure.render())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
