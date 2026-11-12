"""The checker selection must pass the repository's real admission policy."""

from tools.tooling_policy_gate import load_tooling_host_profile_selection_with_current_interpreter


def test_model_checker_host_has_exact_admitted_payload() -> None:
    selected = load_tooling_host_profile_selection_with_current_interpreter("model-check-ubuntu-26.04-x86_64")
    artifact = next(item for item in selected["artifacts"] if item["artifact_id"] == "mcrl2")
    assert artifact["version"] == "202607.0"
    assert artifact["platform"]["installed_tree"]["format"] == "deb"
    assert artifact["platform"]["installed_manifest"][0]["path"] == "usr/bin/ltscompare"
    assert {"bubblewrap", "dpkg", "util-linux", "libc6", "libstdc++6"} <= set(
        selected["host_profile"]["host_prerequisite_package_ids"]
    )
