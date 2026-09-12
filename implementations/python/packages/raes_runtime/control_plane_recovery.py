"""Compatibility tombstone for the removed record-only recovery writer.

Interrupted accepted and running operations remain durably claimed until a
governed recovery flow can commit a complete snapshot, terminal record, and
actor-bound audit.  This module intentionally exposes no recovery function.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
