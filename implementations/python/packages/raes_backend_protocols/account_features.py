"""Canonical account-feature extraction for the provisioner capability boundary.

``provisioner_account_features`` is the single spec->feature-term mapping shared
by the processor planner gate (``raes_processor.planner._validate_manifest``) and
backend capability-envelope diagnostics (issue #605), so the two never diverge.
It is kept out of ``capabilities`` (which declares *what a backend supports*)
because it reads *what a plan's account spec uses* — a plan-payload
semantics concern, not a capability declaration.
"""

from __future__ import annotations

from collections.abc import Mapping


def provisioner_account_features(account_spec: Mapping[str, object]) -> frozenset[str]:
    """Return the governed account-feature terms an account-placement spec exercises.

    Checked against ``ProvisionerCapabilities.supported_account_features``. Only
    opt-in, non-default values count: a bare username, an enabled account
    (``disabled`` falsy), and a plain password login (``auth_method`` unset or
    ``"password"``) are descriptive defaults, not features.
    """

    features: set[str] = set()
    if account_spec.get("groups"):
        features.add("groups")
    if account_spec.get("mail"):
        features.add("mail")
    if account_spec.get("spn"):
        features.add("spn")
    if account_spec.get("shell"):
        features.add("shell")
    if account_spec.get("home"):
        features.add("home")
    if account_spec.get("disabled") not in (False, None, ""):
        features.add("disabled")
    if account_spec.get("auth_method") not in ("", None, "password"):
        features.add("auth_method")
    if account_spec.get("credential_bindings"):
        features.add("credential_bindings")
    return frozenset(features)
