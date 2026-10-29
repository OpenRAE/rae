"""Hosted-only process-loss witness at supervised PostgreSQL transaction cuts."""

import os
import sys
from pathlib import Path

from postgresql_ledger_fixtures import ledger_configuration
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.planning import ProvisioningPlan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore


def main():
    if os.environ.get("RAES_EXECUTION_INTEGRATION") != "1":
        raise RuntimeError("process-loss witness requires the hosted integration composition")
    phase, marker, database = sys.argv[1], Path(sys.argv[2]), sys.argv[3]

    class CrashStore(PostgreSQLControlPlaneStore):
        def save_record(self, record):
            if record.invocation is not None and record.invocation.consumed and phase == "before-grant":
                os._exit(86)
            super().save_record(record)
            if record.invocation is not None and record.invocation.consumed and phase == "after-grant":
                os._exit(86)

        def commit_terminal_operation(self, *args, **kwargs):
            result = super().commit_terminal_operation(*args, **kwargs)
            if phase == "after-terminal":
                os._exit(86)
            return result

    target = create_stub_target()
    original = target.provisioner.apply

    def apply(plan, snapshot):
        marker.write_text("invoked")
        if phase == "after-dispatch":
            os._exit(86)
        return original(plan, snapshot)

    target.provisioner.apply = apply
    store = CrashStore(ledger_configuration(database))
    with RuntimeControlPlane(target, store=store) as plane:
        plane.submit_provisioning(ProvisioningPlan(operation_id="crash-case"), idempotency_key="crash-retry")
        raise RuntimeError("configured crash cut was not reached")


if __name__ == "__main__":
    main()
