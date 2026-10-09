"""Sphinx extension that warns when a public page reads a file from outside the source directory.

``docs/public/conf.py`` loads it. Every build that publishes the docs treats warnings as
errors (``-W`` in nox, ``fail_on_warning`` on Read the Docs), so a warning fails the build.
The check reads the files Sphinx recorded for each page, so it does not depend on how the
page wrote the directive or link.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Sequence
from importlib.machinery import all_suffixes
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unwrap, urlsplit

from docutils.parsers.rst.directives.misc import Raw
from sphinx.directives.code import LiteralInclude
from sphinx.directives.patches import CSVTable
from sphinx.util import logging

if TYPE_CHECKING:
    from docutils import nodes
    from sphinx.application import Sphinx

LOGGER = logging.getLogger(__name__)
# Sphinx's collectors record images, downloads and docutils dependencies on doctree-read
# at the default priority (500). Higher priorities run later.
AFTER_SPHINX_COLLECTORS = 900
MODULE_SUFFIXES = frozenset(all_suffixes())


def files_outside(root: Path, files: Iterable[str | os.PathLike[str]]) -> list[Path]:
    """Return the files outside ``root``, except source files of Python modules the build imported.

    autodoc records the source file of every module it documents. Sphinx joins recorded
    paths to the source directory and keeps their ``..`` segments, so they are resolved first.
    """

    resolved_root = root.resolve()
    outside = {path for path in (Path(file).resolve() for file in files) if not path.is_relative_to(resolved_root)}
    if any(path.suffix in MODULE_SUFFIXES for path in outside):
        outside -= _imported_module_files()
    return sorted(outside)


def _imported_module_files() -> set[Path]:
    # Iterate over a copy, as the sys.modules documentation advises: a lookup can import a module.
    files = {getattr(module, "__file__", None) for module in sys.modules.copy().values()}
    # The build imports this module too, but autodoc never documents it.
    return {Path(file).resolve() for file in files if isinstance(file, str)} - {Path(__file__).resolve()}


def _warn_about_files_outside(app: Sphinx, _doctree: nodes.document) -> None:
    # Checked while the page is read, because autodoc imports its modules at that point.
    # An incremental build skips unchanged pages, so a page that fails is read again next time.
    docname = app.env.docname
    outside = files_outside(Path(app.srcdir), app.env.dependencies.get(docname, ()))
    for path in outside:
        LOGGER.warning("page reads %s, which is outside the documentation source directory", path, location=docname)
    if outside:
        app.env.note_reread()


class DiffRecordingLiteralInclude(LiteralInclude):
    """Record the ``:diff:`` file as a page dependency. Sphinx reads it without recording it."""

    def run(self) -> list[nodes.Node]:
        if "diff" in self.options:
            self.env.note_dependency(self.env.relfn2path(self.options["diff"])[1])
        return super().run()


def _refuse_file_url(directive: Raw | CSVTable) -> None:
    # docutils reads a :url: with urllib, which opens file: URLs, and records no dependency.
    if urlsplit(unwrap(directive.options.get("url", ""))).scheme == "file":
        directive.state.document.settings.env.note_reread()
        raise directive.warning(f'"{directive.name}" must not read a local file through a file: URL')


class FileUrlRefusingRaw(Raw):
    """``raw`` without ``file:`` URLs."""

    def run(self) -> list[nodes.Node]:
        _refuse_file_url(self)
        return super().run()


class FileUrlRefusingCSVTable(CSVTable):
    """``csv-table`` without ``file:`` URLs."""

    def run(self) -> Sequence[nodes.table | nodes.system_message]:
        _refuse_file_url(self)
        return super().run()


def setup(app: Sphinx) -> dict[str, Any]:
    app.add_directive("literalinclude", DiffRecordingLiteralInclude, override=True)
    app.add_directive("raw", FileUrlRefusingRaw, override=True)
    app.add_directive("csv-table", FileUrlRefusingCSVTable, override=True)
    app.connect("doctree-read", _warn_about_files_outside, priority=AFTER_SPHINX_COLLECTORS)
    return {"version": "1", "parallel_read_safe": True, "parallel_write_safe": True}
