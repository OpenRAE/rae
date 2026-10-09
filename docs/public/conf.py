import json
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version
from pathlib import Path

# -- Project information -------------------------------------------------------

project = "Reproducible Agentic Environments System"
copyright = "2026, Brad Edwards"
author = "Brad Edwards"

# The docs build version derives from the installed `raes` distribution
# metadata (the release-please-owned source of truth), not a hand-maintained
# literal (GOV-901). The honest PEP 440 sentinel `0.0.0+unknown` is used when
# the distribution is not installed, so the docs never imply a false release.
try:
    release = _distribution_version("raes")
except PackageNotFoundError:
    release = "0.0.0+unknown"
version = release.split("+", 1)[0]

# -- General configuration -----------------------------------------------------

# Load tools.public_docs_guard from the repository root. It warns when a page
# reads a file from outside this directory, which fails the warning-strict build.
sys.path.append(str(Path(__file__).resolve().parents[2]))

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosummary",
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_reredirects",
    "tools.public_docs_guard",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
redirects = json.loads((Path(__file__).parent / "redirects.json").read_text(encoding="utf-8"))

# Bound remote I/O and avoid connection-pool stalls during the required
# repository-wide link check. Links back into this repository are covered by
# local policy and schema checks, so do not spend unauthenticated GitHub quota
# rechecking them over the network.
linkcheck_timeout = 15
linkcheck_workers = 1
linkcheck_ignore = [
    r"^https://github\.com/(?:RAESystem|OpenRAE)/rae(?:/|$)",
]

# -- MyST (Markdown) settings --------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "tasklist",
]
myst_heading_anchors = 3

# -- Options for HTML output ---------------------------------------------------

html_theme = "furo"
html_title = "RAES Documentation"
html_static_path = ["_static"]

html_theme_options = {
    "source_repository": "https://github.com/OpenRAE/rae",
    "source_branch": "main",
    "source_directory": "docs/public/",
    "navigation_with_keys": True,
}

# -- autodoc settings ----------------------------------------------------------

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"
autodoc_class_signature = "separated"

# -- napoleon settings ---------------------------------------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True

# -- autosummary ---------------------------------------------------------------

autosummary_generate = True
