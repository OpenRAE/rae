"""Process-local component ownership complements the deployment's external fence."""

from threading import RLock
from weakref import ref

_LOCK = RLock()
_CLAIMS = {}


def ledger_identity(store):
    raw = getattr(store, "raw_store", store)
    path = getattr(raw, "_database_path", None)
    if path is not None:
        return ("local-ledger", str(path.resolve()))
    config = getattr(raw, "_configuration", None)
    if config is not None and hasattr(config, "database"):
        return ("postgresql-ledger", config.host, config.port, config.database, config.user)
    return ("in-memory-ledger", raw)


class RuntimeResourceClaim:
    def __init__(self, owner, target, *, ledger=None):
        self._owner = ref(owner, self._owner_gone)
        self.unresolved = False
        self.ledger = ledger
        self.closed = False
        self.components = tuple(
            component
            for name in (
                "provisioner",
                "orchestrator",
                "evaluator",
                "participant_runtime",
                "time_runtime",
                "operation_provider",
            )
            if (component := getattr(target, name, None)) is not None
        )
        with _LOCK:
            for component in self.components:
                prior = _CLAIMS.get(id(component))
                if (
                    prior is not None
                    and (prior._owner() is not None or prior.unresolved)
                    and not (prior.closed and ledger is not None and prior.ledger == ledger)
                ):
                    raise RuntimeError(
                        "backend already has a runtime owner; use exactly one worker and the admitted ledger"
                    )
            for component in self.components:
                _CLAIMS[id(component)] = self

    def release(self, *, unresolved=False):
        with _LOCK:
            self.closed = True
            self.unresolved = unresolved
            if unresolved:
                # An uncertain resource may be reopened only with the same ledger,
                # whose retained reservations continue to exclude new effects.
                return
            for component in self.components:
                if _CLAIMS.get(id(component)) is self:
                    del _CLAIMS[id(component)]

    def retain_unresolved(self):
        with _LOCK:
            self.unresolved = True

    def _owner_gone(self, _reference):
        with _LOCK:
            if not self.unresolved:
                for component in self.components:
                    if _CLAIMS.get(id(component)) is self:
                        del _CLAIMS[id(component)]
