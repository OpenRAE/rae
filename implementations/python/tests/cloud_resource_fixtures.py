"""Synthetic cloud state; no cloud credentials or provider calls."""

from copy import deepcopy

AUTHORITY = "nodes.iam.runtime.identity_authorities.cloud"
SCOPE_A = f"{AUTHORITY}.resource_scopes.project-a"
SCOPE_B = f"{AUTHORITY}.resource_scopes.project-b"
PRINCIPAL = f"{AUTHORITY}.subjects.worker"
APP = "nodes.secrets.runtime.platform_applications.manager"
SECRET = f"{APP}.secrets.database"
VERSION = f"{SECRET}.versions.v1"
DISABLED = f"{SECRET}.versions.v2"


def cloud_scenario() -> dict:
    return deepcopy(
        {
            "name": "cross-project-secret",
            "nodes": {
                "worker": {"type": "compute"},
                "iam": {
                    "type": "compute",
                    "runtime": {
                        "identity_authorities": [
                            {
                                "identity_authority_id": "cloud",
                                "kind": "cloud_iam",
                                "resource_scopes": [
                                    {
                                        "scope_id": "project-a",
                                        "provider": "gcp",
                                        "scope_kind": "project",
                                        "native_id": "Project-A",
                                    },
                                    {
                                        "scope_id": "project-b",
                                        "provider": "gcp",
                                        "scope_kind": "project",
                                        "native_id": "Project-B",
                                    },
                                ],
                                "subjects": [
                                    {
                                        "subject_id": "worker",
                                        "kind": "service_account",
                                        "name": "worker",
                                        "resource_scope_ref": SCOPE_A,
                                    }
                                ],
                                "identity_uses": [
                                    {
                                        "use_id": "worker-use",
                                        "workload_ref": "nodes.worker",
                                        "principal_ref": PRINCIPAL,
                                        "mode": "attached",
                                    }
                                ],
                                "policies": [
                                    {
                                        "policy_id": "reader",
                                        "policy_kind": "access",
                                        "resource_access": {
                                            "attachment_ref": SCOPE_B,
                                            "bindings": [
                                                {
                                                    "binding_id": "read",
                                                    "principal_refs": [PRINCIPAL],
                                                    "actions": ["secretmanager.versions.access"],
                                                    "resource_refs": [SECRET],
                                                    "effect": "allow",
                                                }
                                            ],
                                        },
                                    }
                                ],
                                "access_observations": [
                                    {
                                        "observation_id": "denied",
                                        "principal_ref": PRINCIPAL,
                                        "action": "secretmanager.versions.access",
                                        "resource_ref": DISABLED,
                                        "outcome": "denied",
                                        "evidence_refs": ["urn:example:denied-attempt"],
                                    }
                                ],
                            }
                        ]
                    },
                },
                "secrets": {
                    "type": "compute",
                    "services": [{"name": "api", "port": 443, "protocol": "tcp"}],
                    "runtime": {
                        "platform_applications": [
                            {
                                "platform_application_id": "manager",
                                "service": "api",
                                "product": "GCP Secret Manager",
                                "secrets": [
                                    {
                                        "secret_id": "database",
                                        "resource_scope_ref": SCOPE_B,
                                        "native_id": "database",
                                        "versions": [
                                            {"version_id": "v1", "native_id": "1", "state": "enabled"},
                                            {"version_id": "v2", "native_id": "2", "state": "disabled"},
                                            {"version_id": "v3", "native_id": "3", "state": "destroyed"},
                                        ],
                                        "consumers": [
                                            {
                                                "selection_id": "worker-version",
                                                "consumer_ref": "nodes.worker",
                                                "version_ref": VERSION,
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    },
                },
            },
        }
    )


def authority(raw: dict) -> dict:
    return raw["nodes"]["iam"]["runtime"]["identity_authorities"][0]


def secret(raw: dict) -> dict:
    return raw["nodes"]["secrets"]["runtime"]["platform_applications"][0]["secrets"][0]
