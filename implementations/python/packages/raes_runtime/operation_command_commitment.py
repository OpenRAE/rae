"""Owner-private exact command identity without a durable credential verifier."""

import hmac

from raes_contracts.plan_projection import runtime_plan_digest


def native_command_commitment(plane, plan):
    # The key exists only in the live artifact owner. A reopened ledger retains
    # this opaque commitment, never the key or a recreated dispatch authority.
    message = b"raes-native-command/v1\0" + runtime_plan_digest(plan).encode("ascii")
    return "sha256:" + hmac.digest(plane._command_commitment_key, message, "sha256").hex()
