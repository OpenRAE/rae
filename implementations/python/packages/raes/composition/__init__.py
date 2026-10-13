"""Module/import expansion for multi-file SDL scenarios.

This package is a thin facade over cohesive subdomains:

* :mod:`._references` - pure symbol/reference-rewriting primitives.
* :mod:`._sections` - foundational/proposition/narrative/observation/content/
  stateful/account/deployment/relationship section rewriters.
* :mod:`._runtime_references` - node-runtime reference rewriters
  (security-monitoring detection definitions).
* :mod:`._behavior` - behavior-specification and agent rewriters.
* :mod:`._terminal` - time/objective/workflow/variation rewriters and
  namespacing.
* :mod:`._expand` - the ``expand_sdl_modules`` import-expansion coordinator and
  the shared ``_rewrite_payload_with_symbols`` rewrite seam.

``_rewrite_payload_with_symbols`` and ``_namespace_payload`` are private but
imported by ``_transformation_rename`` and the test suite; they are re-exported
here to preserve the pre-split ``raes.composition`` import surface.
"""

from __future__ import annotations

from ._expand import _namespace_payload, _rewrite_payload_with_symbols, expand_sdl_modules
