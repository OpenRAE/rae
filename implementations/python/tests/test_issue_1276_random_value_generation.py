"""Configurable per-run random value generation (issue #1276, DSL-435).

Model-layer coverage for the ``random_value`` generated-artifact generator: its
recipe (alphabet/size/format/entropy), the secret-entropy floor, and the
regeneration-scope coupling. Later layers (bindings, run identity, verification,
schema, capability) add their own modules/sections.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from raes.random_value import (
    MAX_RENDERED_VALUE_LENGTH,
    SECRET_MIN_ENTROPY_BITS,
    NamedAlphabet,
    RandomValueRecipe,
)
from raes.stateful_resources import (
    GeneratedArtifact,
    GeneratedArtifactRegenerationScope,
)
from raes_backend_protocols.provisioner_capabilities import ProvisionerCapabilities
from raes_contracts.contracts import ProvisionerCapabilitiesModel
from raes_contracts.vocabulary import GeneratedArtifactKind


def _artifact(*, recipe: dict | None = None, scope: str | None = "per_run", sensitivity: str = "secret", **overrides):
    body: dict = {
        "generator": "random_value",
        "lifecycle": "reuse_valid",
        "provenance": "issue-1276 test",
        "outputs": [{"name": "flag", "path": "flag.txt", "sensitivity": sensitivity}],
    }
    if recipe is not None:
        body["random_value"] = recipe
    if scope is not None:
        body["regeneration_scope"] = scope
    body.update(overrides)
    return GeneratedArtifact.model_validate(body)


_SECRET_RECIPE = {"alphabet": "hex_lower", "length": 32}


class TestRandomValueRecipe:
    def test_length_and_named_alphabet_entropy(self) -> None:
        recipe = RandomValueRecipe.model_validate({"alphabet": "hex_lower", "length": 32})
        assert recipe.effective_entropy_bits() == pytest.approx(128.0)
        assert recipe.random_segment_length() == 32
        assert recipe.charset() == "0123456789abcdef"

    def test_entropy_bits_drives_segment_length(self) -> None:
        recipe = RandomValueRecipe.model_validate({"alphabet": "hex_lower", "entropy_bits": 128})
        assert recipe.effective_entropy_bits() == 128.0
        assert recipe.random_segment_length() == math.ceil(128 / 4)

    def test_format_wrapper_is_accepted(self) -> None:
        recipe = RandomValueRecipe.model_validate(
            {"alphabet": "hex_lower", "length": 32, "format": {"prefix": "TECHVAULT{", "suffix": "}"}}
        )
        assert recipe.format is not None
        assert recipe.format.prefix == "TECHVAULT{"

    def test_custom_alphabet(self) -> None:
        recipe = RandomValueRecipe.model_validate({"custom_alphabet": "AB012", "length": 10})
        assert recipe.charset() == "AB012"
        assert recipe.effective_entropy_bits() == pytest.approx(10 * math.log2(5))

    @pytest.mark.parametrize(
        "recipe",
        [
            {"length": 32},  # neither alphabet nor custom_alphabet
            {"alphabet": "hex_lower", "custom_alphabet": "ABCD", "length": 32},  # both
            {"alphabet": "hex_lower"},  # neither length nor entropy_bits
            {"alphabet": "hex_lower", "length": 8, "entropy_bits": 32},  # both
            {"custom_alphabet": "AABB", "length": 8},  # duplicate chars
            {"custom_alphabet": "A", "length": 8},  # degenerate alphabet
            {"custom_alphabet": "A B", "length": 8},  # whitespace
            {"alphabet": "hex_lower", "length": True},  # bool count
            {"alphabet": "hex_lower", "length": 0},  # non-positive
            {"alphabet": "not_a_real_alphabet", "length": 8},  # unknown named alphabet
            {"alphabet": "hex_lower", "length": 32, "format": {"prefix": "a\nb"}},  # control char in wrapper
            {"alphabet": "hex_lower", "length": MAX_RENDERED_VALUE_LENGTH + 1},  # unbounded
            {"alphabet": "hex_lower", "length": 8, "min_entropy_bits": 128},  # below declared floor
        ],
    )
    def test_invalid_recipes_are_rejected(self, recipe: dict) -> None:
        with pytest.raises(ValidationError):
            RandomValueRecipe.model_validate(recipe)

    def test_every_named_alphabet_resolves(self) -> None:
        for member in NamedAlphabet:
            recipe = RandomValueRecipe.model_validate({"alphabet": member.value, "length": 4})
            assert len(recipe.charset()) >= 2


class TestGeneratedArtifactRandomValue:
    def test_secret_flag_artifact(self) -> None:
        artifact = _artifact(recipe=_SECRET_RECIPE)
        assert artifact.generator is GeneratedArtifactKind.RANDOM_VALUE
        assert artifact.regeneration_scope is GeneratedArtifactRegenerationScope.PER_RUN
        assert artifact.random_value is not None

    @pytest.mark.parametrize("scope", ["per_run", "per_instantiation", "once"])
    def test_all_regeneration_scopes(self, scope: str) -> None:
        artifact = _artifact(recipe=_SECRET_RECIPE, scope=scope)
        assert artifact.regeneration_scope.value == scope

    def test_secret_output_below_floor_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match=str(SECRET_MIN_ENTROPY_BITS)):
            _artifact(recipe={"alphabet": "hex_lower", "length": 16})  # 64 bits < 128

    def test_public_output_allows_low_entropy(self) -> None:
        artifact = _artifact(recipe={"alphabet": "digits", "length": 6}, sensitivity="public")
        assert artifact.random_value is not None

    def test_random_value_requires_recipe(self) -> None:
        with pytest.raises(ValidationError, match="requires a random_value recipe"):
            _artifact(recipe=None)

    def test_random_value_requires_scope(self) -> None:
        with pytest.raises(ValidationError, match="requires a regeneration_scope"):
            _artifact(recipe=_SECRET_RECIPE, scope=None)

    def test_random_value_requires_single_output(self) -> None:
        with pytest.raises(ValidationError, match="exactly one output"):
            _artifact(
                recipe=_SECRET_RECIPE,
                outputs=[
                    {"name": "flag", "path": "flag.txt", "sensitivity": "secret"},
                    {"name": "other", "path": "other.txt", "sensitivity": "secret"},
                ],
            )

    def test_recipe_forbidden_for_other_generators(self) -> None:
        with pytest.raises(ValidationError, match="only valid for the random_value generator"):
            GeneratedArtifact.model_validate(
                {
                    "generator": "rendered_config",
                    "lifecycle": "reuse_valid",
                    "random_value": _SECRET_RECIPE,
                    "provenance": "x",
                    "outputs": [{"name": "o", "path": "o.txt", "sensitivity": "public"}],
                    "consumers": [
                        {
                            "node": "n",
                            "mount_destination": "/srv/o",
                            "access_mode": "read_only",
                            "selected_outputs": ["o"],
                        }
                    ],
                }
            )

    def test_scope_forbidden_for_other_generators(self) -> None:
        with pytest.raises(ValidationError, match="regeneration_scope is only valid"):
            GeneratedArtifact.model_validate(
                {
                    "generator": "rendered_config",
                    "lifecycle": "reuse_valid",
                    "regeneration_scope": "per_run",
                    "provenance": "x",
                    "outputs": [{"name": "o", "path": "o.txt", "sensitivity": "public"}],
                    "consumers": [
                        {
                            "node": "n",
                            "mount_destination": "/srv/o",
                            "access_mode": "read_only",
                            "selected_outputs": ["o"],
                        }
                    ],
                }
            )


class TestProvisionerRandomValueCapability:
    def _model(self, **overrides) -> dict:
        body = {
            "name": "p",
            "supported_node_types": ["compute"],
            "supported_os_families": ["linux"],
            "supports_generated_artifacts": True,
            "supported_generated_artifact_kinds": ["random_value"],
            "supported_generated_artifact_delivery_modes": ["mount"],
            "supported_regeneration_scopes": ["per_run", "once"],
        }
        body.update(overrides)
        return body

    def test_random_value_kind_requires_scopes(self) -> None:
        with pytest.raises(ValidationError, match="supported_regeneration_scopes"):
            ProvisionerCapabilitiesModel.model_validate(self._model(supported_regeneration_scopes=[]))

    def test_scopes_require_random_value_kind(self) -> None:
        with pytest.raises(ValidationError, match="random_value"):
            ProvisionerCapabilitiesModel.model_validate(
                self._model(supported_generated_artifact_kinds=["rendered_config"])
            )

    def test_valid_random_value_capability_model(self) -> None:
        model = ProvisionerCapabilitiesModel.model_validate(self._model())
        assert GeneratedArtifactKind.RANDOM_VALUE in model.supported_generated_artifact_kinds
        assert len(model.supported_regeneration_scopes) == 2

    def test_dataclass_capability_couples_scope_to_kind(self) -> None:
        with pytest.raises(ValueError, match="supported_regeneration_scopes"):
            ProvisionerCapabilities(
                name="p",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
                supports_generated_artifacts=True,
                supported_generated_artifact_kinds=frozenset({"random_value"}),
                supported_generated_artifact_delivery_modes=frozenset({"mount"}),
            )

    def test_dataclass_capability_roundtrip(self) -> None:
        caps = ProvisionerCapabilities(
            name="p",
            supported_node_types=frozenset({"compute"}),
            supported_os_families=frozenset({"linux"}),
            supports_generated_artifacts=True,
            supported_generated_artifact_kinds=frozenset({"random_value"}),
            supported_generated_artifact_delivery_modes=frozenset({"mount"}),
            supported_regeneration_scopes=frozenset({"per_run"}),
        )
        assert GeneratedArtifactKind.RANDOM_VALUE in caps.supported_generated_artifact_kinds
        assert len(caps.supported_regeneration_scopes) == 1


# --- integration: parse -> compile -> plan (file + env bindings) -------------

import textwrap  # noqa: E402
from dataclasses import replace  # noqa: E402

from raes import parse_sdl  # noqa: E402
from raes_backend_stubs.stubs import create_stub_manifest  # noqa: E402
from raes_contracts.vocabulary import GeneratedArtifactDeliveryMode  # noqa: E402
from raes_processor.compiler import compile_runtime_model  # noqa: E402
from raes_processor.planner import plan  # noqa: E402


def _with_random_value_support(manifest):
    """Return ``manifest`` with its provisioner extended to support random_value.

    The shipped stub and reference backends do not advertise random_value (the
    stub's apply is a no-op; the reference has no container-level secret delivery),
    so admission/pipeline tests construct a capable backend via ``replace`` to
    represent a provisioner that supports the generator (issue #1276).
    """

    provisioner = manifest.capabilities.provisioner
    capable = replace(
        provisioner,
        supports_generated_artifacts=True,
        supported_generated_artifact_kinds=(
            provisioner.supported_generated_artifact_kinds | {GeneratedArtifactKind.RANDOM_VALUE}
        ),
        supported_generated_artifact_delivery_modes=(
            provisioner.supported_generated_artifact_delivery_modes
            | {
                GeneratedArtifactDeliveryMode.MOUNT,
                GeneratedArtifactDeliveryMode.ENVIRONMENT,
                GeneratedArtifactDeliveryMode.ENV_FILE,
                GeneratedArtifactDeliveryMode.CONTENT_TEXT,
            }
        ),
        supported_regeneration_scopes=frozenset(GeneratedArtifactRegenerationScope),
    )
    return replace(manifest, capabilities=replace(manifest.capabilities, provisioner=capable))


def _capable_stub():
    """Stub manifest extended to declare random_value provisioner support."""

    return _with_random_value_support(create_stub_manifest())


_FLAG_WITH_FILE_CONSUMER = textwrap.dedent(
    """
    name: techvault
    nodes:
      web: {type: compute}
    generated_artifacts:
      techvault-flag:
        generator: random_value
        lifecycle: reuse_valid
        regeneration_scope: per_run
        random_value:
          alphabet: hex_lower
          length: 32
          format: {prefix: "TECHVAULT{", suffix: "}"}
        provenance: techvault/ctf-flag
        outputs:
          - {name: flag, path: flag.txt, sensitivity: secret}
        consumers:
          - {node: web, mount_destination: /srv/flag, access_mode: read_only, selected_outputs: [flag]}
    """
)


class TestRandomValuePipeline:
    def test_file_consumer_parses_and_compiles_value_free(self) -> None:
        model = compile_runtime_model(parse_sdl(_FLAG_WITH_FILE_CONSUMER))
        artifact = model.generated_artifacts["provision.generated-artifact.techvault-flag"]
        spec = artifact.spec
        # The value-free recipe + scope flow into the plan spec; no raw value.
        assert spec["generator"] == "random_value"
        assert spec["regeneration_scope"] == "per_run"
        assert spec["random_value"]["alphabet"] == "hex_lower"
        assert spec["random_value"]["length"] == 32
        # The spec carries shape only - no realized value field.
        assert "value" not in spec
        assert spec["random_value"]["format"]["prefix"] == "TECHVAULT{"

    def test_file_consumer_admitted_by_capable_backend(self) -> None:
        execution = plan(compile_runtime_model(parse_sdl(_FLAG_WITH_FILE_CONSUMER)), _capable_stub(), run_id="run-1")
        assert execution.is_valid, [d.message for d in execution.diagnostics]

    def test_backend_without_random_value_kind_rejects(self) -> None:
        manifest = _capable_stub()
        without_random = replace(
            manifest,
            capabilities=replace(
                manifest.capabilities,
                provisioner=replace(
                    manifest.provisioner,
                    supported_generated_artifact_kinds=frozenset(
                        k
                        for k in manifest.provisioner.supported_generated_artifact_kinds
                        if getattr(k, "value", k) != "random_value"
                    ),
                    supported_regeneration_scopes=frozenset(),
                ),
            ),
        )
        execution = plan(compile_runtime_model(parse_sdl(_FLAG_WITH_FILE_CONSUMER)), without_random, run_id="run-1")
        assert not execution.is_valid
        assert any("generated-artifact-kind" in d.code for d in execution.diagnostics)

    def test_backend_without_scope_rejects(self) -> None:
        manifest = _capable_stub()
        without_per_run = replace(
            manifest,
            capabilities=replace(
                manifest.capabilities,
                provisioner=replace(
                    manifest.provisioner,
                    supported_regeneration_scopes=frozenset({GeneratedArtifactRegenerationScope.ONCE}),
                ),
            ),
        )
        execution = plan(compile_runtime_model(parse_sdl(_FLAG_WITH_FILE_CONSUMER)), without_per_run, run_id="run-1")
        assert not execution.is_valid
        assert any(d.code == "provisioner.unsupported-regeneration-scope" for d in execution.diagnostics)


_FLAG_ENV_BINDING = textwrap.dedent(
    """
    name: techvault
    nodes:
      web:
        type: compute
        runtime:
          environment:
            - name: CTF_FLAG
              value_from: {generated_artifact: techvault-flag, output: flag}
              value_classification: redacted
              provenance: runtime
    generated_artifacts:
      techvault-flag:
        generator: random_value
        lifecycle: reuse_valid
        regeneration_scope: per_run
        random_value: {alphabet: hex_lower, length: 32}
        provenance: techvault/ctf-flag
        outputs:
          - {name: flag, path: flag.txt, sensitivity: secret}
    """
)


def _environment_capable_manifest():
    from raes_contracts.apparatus import RealizationObservationCapability
    from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope

    manifest = _capable_stub()
    declaration = manifest.realization_support[0]
    return replace(
        manifest,
        realization_support=(
            replace(
                declaration,
                supported_exact_requirement_kinds=(
                    declaration.supported_exact_requirement_kinds | {"runtime-environment"}
                ),
                observation_capabilities={
                    **declaration.observation_capabilities,
                    "runtime-environment": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    ),
                },
            ),
        ),
    )


class TestRandomValueEnvBinding:
    def test_env_binding_compiles_value_free_projection(self) -> None:
        model = compile_runtime_model(parse_sdl(_FLAG_ENV_BINDING))
        artifact = model.generated_artifacts["provision.generated-artifact.techvault-flag"]
        projection = artifact.spec["environment_consumers"][0]
        assert projection["delivery_mode"] == GeneratedArtifactDeliveryMode.ENVIRONMENT.value
        assert projection["output"] == "flag"
        assert projection["environment_variable"] == "CTF_FLAG"

    def test_env_binding_admitted_by_capable_backend(self) -> None:
        execution = plan(
            compile_runtime_model(parse_sdl(_FLAG_ENV_BINDING)), _environment_capable_manifest(), run_id="run-1"
        )
        assert execution.is_valid, [d.message for d in execution.diagnostics]


# --- run identity + regeneration-scope reconciliation ------------------------

from raes_processor.models import RuntimeDomain, RuntimeSnapshot, SnapshotEntry  # noqa: E402

_FLAG_ARTIFACT_ADDRESS = "provision.generated-artifact.techvault-flag"


def _scoped_flag_scenario(scope: str) -> str:
    return textwrap.dedent(
        f"""
        name: techvault
        nodes:
          web: {{type: compute}}
        generated_artifacts:
          techvault-flag:
            generator: random_value
            lifecycle: reuse_valid
            regeneration_scope: {scope}
            random_value: {{alphabet: hex_lower, length: 32}}
            provenance: techvault/ctf-flag
            outputs:
              - {{name: flag, path: flag.txt, sensitivity: secret}}
            consumers:
              - {{node: web, mount_destination: /srv/flag, access_mode: read_only, selected_outputs: [flag]}}
        """
    )


def _snapshot_from_plan(execution_plan) -> RuntimeSnapshot:
    entries: dict[str, SnapshotEntry] = {}
    for domain, operations in (
        (RuntimeDomain.PROVISIONING, execution_plan.provisioning.operations),
        (RuntimeDomain.ORCHESTRATION, execution_plan.orchestration.operations),
        (RuntimeDomain.EVALUATION, execution_plan.evaluation.operations),
    ):
        for op in operations:
            if op.action.value == "delete":
                continue
            entries[op.address] = SnapshotEntry(
                address=op.address,
                domain=domain,
                resource_type=op.resource_type,
                payload=op.payload,
                ordering_dependencies=op.ordering_dependencies,
                refresh_dependencies=op.refresh_dependencies,
                status="snapshot",
            )
    return RuntimeSnapshot(entries=entries)


def _flag_action(execution_plan) -> str:
    op = next(o for o in execution_plan.provisioning.operations if o.address == _FLAG_ARTIFACT_ADDRESS)
    return op.action.value


def _plan_scoped(scope: str, *, snapshot=None, run_id=None, instantiation_id=None):
    model = compile_runtime_model(parse_sdl(_scoped_flag_scenario(scope)))
    return plan(
        model,
        _capable_stub(),
        snapshot,
        run_id=run_id,
        instantiation_id=instantiation_id,
    )


class TestRegenerationScopeReconciliation:
    def test_per_run_regenerates_on_new_run(self) -> None:
        first = _plan_scoped("per_run", run_id="run-1")
        assert first.is_valid, [d.message for d in first.diagnostics]
        assert _flag_action(first) == "create"
        snapshot = _snapshot_from_plan(first)
        # A new authoritative run must regenerate.
        second = _plan_scoped("per_run", snapshot=snapshot, run_id="run-2")
        assert _flag_action(second) == "update"

    def test_per_run_retained_within_same_run(self) -> None:
        first = _plan_scoped("per_run", run_id="run-1")
        snapshot = _snapshot_from_plan(first)
        # Resume/retry within the same run retains the value.
        resumed = _plan_scoped("per_run", snapshot=snapshot, run_id="run-1")
        assert _flag_action(resumed) == "unchanged"

    def test_per_instantiation_regenerates_on_new_instance(self) -> None:
        first = _plan_scoped("per_instantiation", instantiation_id="inst-1")
        snapshot = _snapshot_from_plan(first)
        second = _plan_scoped("per_instantiation", snapshot=snapshot, instantiation_id="inst-2")
        assert _flag_action(second) == "update"
        same = _plan_scoped("per_instantiation", snapshot=snapshot, instantiation_id="inst-1")
        assert _flag_action(same) == "unchanged"

    def test_once_is_stable_across_runs(self) -> None:
        first = _plan_scoped("once", run_id="run-1")
        snapshot = _snapshot_from_plan(first)
        second = _plan_scoped("once", snapshot=snapshot, run_id="run-2")
        assert _flag_action(second) == "unchanged"

    def test_per_run_without_run_identity_fails_before_mutation(self) -> None:
        result = _plan_scoped("per_run")  # no run_id
        assert not result.is_valid
        assert any(d.code == "provisioner.missing-regeneration-scope-identity" for d in result.diagnostics)

    def test_per_instantiation_without_identity_fails(self) -> None:
        result = _plan_scoped("per_instantiation")
        assert not result.is_valid
        assert any(d.code == "provisioner.missing-regeneration-scope-identity" for d in result.diagnostics)


# --- content-text deferred binding -------------------------------------------

from raes import SDLValidationError  # noqa: E402


def _content_scenario(content_lines: str, *, output_extra: str = "") -> str:
    """Build a content-binding scenario. ``content_lines`` is the mapping body
    already indented two spaces under ``content:`` (no dedent gymnastics)."""

    return (
        "name: techvault\n"
        "nodes:\n"
        "  web: {type: compute}\n"
        "content:\n" + content_lines + "generated_artifacts:\n"
        "  techvault-flag:\n"
        "    generator: random_value\n"
        "    lifecycle: reuse_valid\n"
        "    regeneration_scope: per_run\n"
        "    random_value: {alphabet: hex_lower, length: 32}\n"
        "    provenance: techvault/ctf-flag\n"
        "    outputs:\n"
        f"      - {{name: flag, path: flag.txt, sensitivity: secret{output_extra}}}\n"
    )


_VALID_CONTENT = (
    "  flag-file:\n"
    "    type: file\n"
    "    target: web\n"
    "    path: /srv/flag.txt\n"
    "    sensitive: true\n"
    "    text_from: {generated_artifact: techvault-flag, output: flag}\n"
)


class TestContentTextBinding:
    def test_content_text_from_parses_and_consumes_artifact(self) -> None:
        scenario = parse_sdl(_content_scenario(_VALID_CONTENT))
        assert scenario.content["flag-file"].text_from.generated_artifact == "techvault-flag"
        # The artifact has no file consumer; the content binding is its consumer.
        assert scenario.generated_artifacts["techvault-flag"].consumers == []

    def test_content_text_and_text_from_are_mutually_exclusive(self) -> None:
        lines = (
            "  flag-file:\n"
            "    type: file\n"
            "    target: web\n"
            "    path: /srv/flag.txt\n"
            "    sensitive: true\n"
            '    text: "static"\n'
            "    text_from: {generated_artifact: techvault-flag, output: flag}\n"
        )
        with pytest.raises(Exception, match="text_from"):
            parse_sdl(_content_scenario(lines))

    def test_content_text_from_requires_file_type(self) -> None:
        lines = (
            "  flag-file:\n"
            "    type: directory\n"
            "    target: web\n"
            "    destination: /srv\n"
            "    text_from: {generated_artifact: techvault-flag, output: flag}\n"
        )
        with pytest.raises(Exception, match="text_from"):
            parse_sdl(_content_scenario(lines))

    def test_content_text_from_unknown_artifact_rejected(self) -> None:
        lines = (
            "  flag-file:\n"
            "    type: file\n"
            "    target: web\n"
            "    path: /srv/flag.txt\n"
            "    sensitive: true\n"
            "    text_from: {generated_artifact: does-not-exist, output: flag}\n"
        )
        with pytest.raises(SDLValidationError, match="does-not-exist"):
            parse_sdl(_content_scenario(lines))

    def test_content_text_from_secret_requires_sensitive(self) -> None:
        lines = (
            "  flag-file:\n"
            "    type: file\n"
            "    target: web\n"
            "    path: /srv/flag.txt\n"
            "    sensitive: false\n"
            "    text_from: {generated_artifact: techvault-flag, output: flag}\n"
        )
        with pytest.raises(SDLValidationError, match="sensitive"):
            parse_sdl(_content_scenario(lines))

    def test_content_text_from_producer_private_rejected(self) -> None:
        with pytest.raises(SDLValidationError, match="producer_private|producer-private"):
            parse_sdl(_content_scenario(_VALID_CONTENT, output_extra=", disposition: producer_private"))

    def test_content_binding_compiles_projection_and_dependency(self) -> None:
        model = compile_runtime_model(parse_sdl(_content_scenario(_VALID_CONTENT)))
        artifact = model.generated_artifacts["provision.generated-artifact.techvault-flag"]
        projection = artifact.spec["content_consumers"][0]
        assert projection["delivery_mode"] == "content_text"
        assert projection["output"] == "flag"
        assert projection["content"] == "flag-file"
        placement = model.content_placements["provision.content.flag-file"]
        assert "provision.generated-artifact.techvault-flag" in placement.ordering_dependencies

    def test_content_binding_admitted_by_capable_backend(self) -> None:
        execution = plan(
            compile_runtime_model(parse_sdl(_content_scenario(_VALID_CONTENT))), _capable_stub(), run_id="run-1"
        )
        assert execution.is_valid, [d.message for d in execution.diagnostics]

    def test_content_binding_rejected_without_content_text_delivery(self) -> None:
        manifest = _capable_stub()
        no_content = replace(
            manifest,
            capabilities=replace(
                manifest.capabilities,
                provisioner=replace(
                    manifest.provisioner,
                    supported_generated_artifact_delivery_modes=frozenset(
                        m
                        for m in manifest.provisioner.supported_generated_artifact_delivery_modes
                        if getattr(m, "value", m) != "content_text"
                    ),
                ),
            ),
        )
        execution = plan(
            compile_runtime_model(parse_sdl(_content_scenario(_VALID_CONTENT))), no_content, run_id="run-1"
        )
        assert not execution.is_valid
        assert any("delivery-mode" in d.code for d in execution.diagnostics)


# --- verification: deferred expected value (StringPredicate.expected_from) ----

_FLAG_EVIDENCE = (
    "evidence_requirements:\n"
    "  flag-evidence:\n"
    "    description: submitted flag observation\n"
    "    source_class: participant_action\n"
    "    scope_refs: [nodes.web]\n"
    "    boundary_kind: participant_submission\n"
    "    channel: api_response\n"
    "    sensitivity: redacted\n"
    "    redaction: none\n"
    "    integrity: checksum\n"
    "    retention: study_lifetime\n"
    "    loss_disclosure: required\n"
)

_FLAG_ARTIFACT_BLOCK = (
    "generated_artifacts:\n"
    "  techvault-flag:\n"
    "    generator: random_value\n"
    "    lifecycle: reuse_valid\n"
    "    regeneration_scope: per_run\n"
    "    random_value: {alphabet: hex_lower, length: 32}\n"
    "    provenance: techvault/ctf-flag\n"
    "    outputs:\n"
    "      - {name: flag, path: flag.txt, sensitivity: secret}\n"
)


def _verification_scenario(
    *, basis: str = "observed_state", operator: str = "equals", predicate_extra: str = ""
) -> str:
    return (
        "name: techvault\n"
        "nodes:\n"
        "  web: {type: compute}\n" + _FLAG_EVIDENCE + "propositions:\n"
        "  flag-correct:\n"
        "    description: submitted flag equals generated flag\n"
        "    subjects: [nodes.web]\n"
        f"    basis: {basis}\n"
        "    evidence_requirements: [flag-evidence]\n"
        "    predicate:\n"
        "      kind: string\n"
        "      property: submitted.flag\n"
        "      semantic_ref: urn:techvault:flag\n"
        f"      operator: {operator}\n" + predicate_extra + _FLAG_ARTIFACT_BLOCK
    )


_EXPECTED_FROM_LINE = "      expected_from: {generated_artifact: techvault-flag, output: flag}\n"


class TestDeferredVerification:
    def test_expected_from_parses_and_consumes_artifact(self) -> None:
        scenario = parse_sdl(_verification_scenario(predicate_extra=_EXPECTED_FROM_LINE))
        predicate = scenario.propositions["flag-correct"].predicate
        assert predicate.expected_from.generated_artifact == "techvault-flag"
        assert predicate.expected is None
        # Consumed by verification -> not an orphan even without a delivery consumer.
        assert scenario.generated_artifacts["techvault-flag"].consumers == []

    def test_expected_and_expected_from_mutually_exclusive(self) -> None:
        extra = '      expected: "static"\n' + _EXPECTED_FROM_LINE
        with pytest.raises(Exception, match="expected"):
            parse_sdl(_verification_scenario(predicate_extra=extra))

    def test_membership_operator_rejects_expected_from(self) -> None:
        with pytest.raises(Exception, match="expected_from"):
            parse_sdl(_verification_scenario(operator="in", predicate_extra=_EXPECTED_FROM_LINE))

    def test_expected_from_requires_observed_state_basis(self) -> None:
        with pytest.raises(SDLValidationError, match="observed_state"):
            parse_sdl(_verification_scenario(basis="declared_state", predicate_extra=_EXPECTED_FROM_LINE))

    def test_expected_from_unknown_artifact_rejected(self) -> None:
        line = "      expected_from: {generated_artifact: nope, output: flag}\n"
        with pytest.raises(SDLValidationError, match="nope"):
            parse_sdl(_verification_scenario(predicate_extra=line))

    def test_expected_from_admitted_when_evaluator_declares_support(self) -> None:
        # A backend that explicitly declares deferred comparison admits the
        # predicate (no diagnostic). The bundled stub/reference do NOT claim it,
        # so this opts in via a capability override.
        manifest = _capable_stub()
        capable = replace(
            manifest,
            capabilities=replace(
                manifest.capabilities,
                evaluator=replace(manifest.capabilities.evaluator, supports_deferred_expected_comparison=True),
            ),
        )
        execution = plan(
            compile_runtime_model(parse_sdl(_verification_scenario(predicate_extra=_EXPECTED_FROM_LINE))),
            capable,
            run_id="run-1",
        )
        assert not any(d.code == "evaluator.unsupported-deferred-expected-comparison" for d in execution.diagnostics)

    def test_expected_from_fails_closed_on_default_backend(self) -> None:
        # The bundled evaluators do not implement run-bound comparison, so they do
        # not claim it: an expected_from predicate is rejected before evaluation,
        # so an unsupported backend can never report a passing deferred comparison.
        assert create_stub_manifest().capabilities.evaluator.supports_deferred_expected_comparison is False
        execution = plan(
            compile_runtime_model(parse_sdl(_verification_scenario(predicate_extra=_EXPECTED_FROM_LINE))),
            _capable_stub(),
            run_id="run-1",
        )
        assert not execution.is_valid
        assert any(d.code == "evaluator.unsupported-deferred-expected-comparison" for d in execution.diagnostics)


# --- reference backend generation --------------------------------------------

from raes_reference_backend.artifact_generation import generated_artifact_projections  # noqa: E402


class TestReferenceGeneration:
    def test_reference_generates_formatted_secret_on_create(self) -> None:
        execution = plan(compile_runtime_model(parse_sdl(_FLAG_WITH_FILE_CONSUMER)), _capable_stub(), run_id="r1")
        projections = generated_artifact_projections(execution.provisioning)
        assert len(projections) == 1
        rendered = next(iter(projections.values())).decode("utf-8")
        assert rendered.startswith("TECHVAULT{") and rendered.endswith("}")
        assert len(rendered) == len("TECHVAULT{") + 32 + len("}")

    def test_reference_regenerates_only_on_scope_transition(self) -> None:
        # Generation follows reconciliation, not invocation (issue #1276):
        # create generates; a same-run resume (UNCHANGED) retains it; a new run
        # (UPDATE) regenerates a fresh value.
        first = _plan_scoped("per_run", run_id="r1")
        assert _flag_action(first) == "create"
        assert generated_artifact_projections(first.provisioning)  # generated on create
        snapshot = _snapshot_from_plan(first)

        resume = _plan_scoped("per_run", snapshot=snapshot, run_id="r1")
        assert _flag_action(resume) == "unchanged"
        assert generated_artifact_projections(resume.provisioning) == {}  # retained, not rotated

        new_run = _plan_scoped("per_run", snapshot=snapshot, run_id="r2")
        assert _flag_action(new_run) == "update"
        assert generated_artifact_projections(new_run.provisioning)  # regenerated for the new scope


# --- direct-plan content-consumer admission (finding #4) ---------------------

from raes_processor.planner.stateful_admission import generated_artifact_payload_diagnostic  # noqa: E402

_FLAG_ADDRESS = "provision.generated-artifact.techvault-flag"


def _artifact_spec_with_content_consumer(
    *,
    output: str,
    sensitivity: str = "secret",
    disposition: str | None = None,
    target: str = "provision.content.flag-file",
) -> dict:
    out = {"name": "flag", "path": "flag.txt", "sensitivity": sensitivity}
    if disposition is not None:
        out["disposition"] = disposition
    return {
        "generator": "random_value",
        "lifecycle": "reuse_valid",
        "regeneration_scope": "per_run",
        "random_value": {"alphabet": "hex_lower", "length": 32},
        "provenance": "techvault/ctf-flag",
        "outputs": [out],
        "consumers": [],
        "content_consumers": [
            {"content": "flag-file", "target_address": target, "delivery_mode": "content_text", "output": output}
        ],
    }


_CONTENT_SPECS = {
    "provision.content.flag-file": {
        "spec": {
            "type": "file",
            "target": "web",
            "path": "/srv/flag.txt",
            "sensitive": True,
            "text_from": {"generated_artifact": "techvault-flag", "output": "flag"},
        }
    }
}


class TestDirectPlanContentAdmission:
    def _provisioner(self):
        return _capable_stub().provisioner

    def _diagnostic(self, *, spec, content_specs=_CONTENT_SPECS):
        return generated_artifact_payload_diagnostic(
            address=_FLAG_ADDRESS, spec=spec, provisioner=self._provisioner(), content_specs=content_specs
        )

    def test_valid_content_consumer_admitted(self) -> None:
        assert self._diagnostic(spec=_artifact_spec_with_content_consumer(output="flag")) is None

    def test_unknown_output_rejected(self) -> None:
        diag = self._diagnostic(spec=_artifact_spec_with_content_consumer(output="ghost"))
        assert diag is not None and diag.code == "provisioner.generated-artifact-invalid"

    def test_producer_private_output_rejected(self) -> None:
        diag = self._diagnostic(
            spec=_artifact_spec_with_content_consumer(output="flag", disposition="producer_private")
        )
        assert diag is not None and diag.code == "provisioner.generated-artifact-invalid"

    def test_mismatched_content_target_rejected(self) -> None:
        diag = self._diagnostic(
            spec=_artifact_spec_with_content_consumer(output="flag", target="provision.content.somewhere-else")
        )
        assert diag is not None and diag.code == "provisioner.generated-artifact-invalid"

    def test_phantom_content_placement_rejected(self) -> None:
        # A fabricated content_consumers row with no declared placement is rejected.
        diag = self._diagnostic(spec=_artifact_spec_with_content_consumer(output="flag"), content_specs={})
        assert diag is not None and diag.code == "provisioner.generated-artifact-invalid"


# --- run-identity plumbing through published models + digest (finding #2) -----

from raes_contracts.plan_projection import (  # noqa: E402
    evaluation_plan_model,
    provisioning_plan_model,
    runtime_plan_digest,
)
from raes_contracts.planning import EvaluationPlan, ProvisioningPlan  # noqa: E402
from raes_runtime.control_plane_api_models import _provisioning_plan  # noqa: E402


class TestRunIdentityPlumbing:
    def test_scope_identity_projects_onto_published_model(self) -> None:
        plan_obj = ProvisioningPlan(run_id="run-1", instantiation_id="inst-1")
        model = provisioning_plan_model(plan_obj)
        assert model.run_id == "run-1"
        assert model.instantiation_id == "inst-1"
        eval_model = evaluation_plan_model(EvaluationPlan(run_id="run-1", instantiation_id="inst-1"))
        assert eval_model.run_id == "run-1"
        assert eval_model.instantiation_id == "inst-1"

    def test_digest_binds_run_identity(self) -> None:
        # Otherwise-identical plans for different runs must not collapse to the same
        # authorization digest (prevents cross-run replay / comparison oracle).
        base = runtime_plan_digest(ProvisioningPlan())
        run1 = runtime_plan_digest(ProvisioningPlan(run_id="run-1"))
        run2 = runtime_plan_digest(ProvisioningPlan(run_id="run-2"))
        assert base != run1 != run2 and run1 != run2

    def test_api_round_trip_preserves_scope_identity(self) -> None:
        model = provisioning_plan_model(ProvisioningPlan(run_id="run-1", instantiation_id="inst-1"))
        restored = _provisioning_plan(model)
        assert restored.run_id == "run-1"
        assert restored.instantiation_id == "inst-1"


# --- reference provisioner apply/readback + resume (findings #4, #5) ----------


class TestReferenceProvisionerDelivery:
    def test_apply_delivers_secret_and_retains_across_same_scope_resume(self) -> None:
        from raes_reference_backend import create_reference_backend_target
        from raes_runtime.manager import RuntimeManager

        scenario = parse_sdl(_FLAG_WITH_FILE_CONSUMER)
        # The shipped reference does not advertise random_value (it has no
        # container-level secret delivery); override its capabilities to represent
        # a backend that supports the generator and exercise the generator end to
        # end through the canonical apply path (issue #1276).
        base = create_reference_backend_target()
        target = replace(base, manifest=_with_random_value_support(base.manifest))
        manager = RuntimeManager(target)
        addr, node = "provision.generated-artifact.techvault-flag", "provision.node.web"

        first = manager.plan(scenario, run_id="r1")
        assert not [d for d in first.diagnostics if d.is_error], [d.message for d in first.diagnostics]
        assert manager.apply(first).success
        v1 = target.provisioner.generated_output(addr, node, "flag").decode("utf-8")
        assert v1.startswith("TECHVAULT{") and v1.endswith("}")

        # Same-run resume reconciles UNCHANGED and RETAINS the delivered value.
        resume = manager.plan(scenario, run_id="r1")
        assert manager.apply(resume).success
        assert target.provisioner.generated_output(addr, node, "flag").decode("utf-8") == v1

        # A new authoritative run regenerates a fresh value.
        new_run = manager.plan(scenario, run_id="r2")
        assert manager.apply(new_run).success
        assert target.provisioner.generated_output(addr, node, "flag").decode("utf-8") != v1


# --- module composition namespaces new artifact references (finding: security)

from pathlib import Path  # noqa: E402

from raes import parse_sdl_file  # noqa: E402


def _write_module_with_import(tmp_path: Path, module_body: str) -> Path:
    (tmp_path / "mod.yaml").write_text(
        "name: mod\n"
        "version: 1.0.0\n"
        "module:\n"
        "  id: acme/mod\n"
        "  version: 1.0.0\n"
        "  exports:\n"
        "    nodes: [web]\n"
        "    generated_artifacts: [flag]\n" + module_body,
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        "name: root\nimports:\n  - source: local:mod.yaml\n    namespace: shared\n    version: 1.0.0\n",
        encoding="utf-8",
    )
    return root


_MODULE_FLAG = (
    "generated_artifacts:\n"
    "  flag:\n"
    "    generator: random_value\n"
    "    lifecycle: reuse_valid\n"
    "    regeneration_scope: per_run\n"
    "    random_value: {alphabet: hex_lower, length: 32}\n"
    "    provenance: mod/flag\n"
    "    outputs:\n"
    "      - {name: value, path: flag.txt, sensitivity: secret}\n"
)


class TestCompositionNamespacing:
    def test_content_text_from_reference_is_namespaced(self, tmp_path: Path) -> None:
        body = (
            "nodes:\n  web: {type: compute}\n"
            "content:\n"
            "  flag-file:\n"
            "    type: file\n"
            "    target: web\n"
            "    path: /srv/flag.txt\n"
            "    sensitive: true\n"
            "    text_from: {generated_artifact: flag, output: value}\n" + _MODULE_FLAG
        )
        scenario = parse_sdl_file(_write_module_with_import(tmp_path, body))
        assert "shared.flag" in scenario.generated_artifacts
        bindings = [c.text_from for c in scenario.content.values() if c.text_from is not None]
        assert len(bindings) == 1
        assert bindings[0].generated_artifact == "shared.flag"

    def test_proposition_expected_from_reference_is_namespaced(self, tmp_path: Path) -> None:
        body = (
            "nodes:\n  web: {type: compute}\n"
            "evidence_requirements:\n"
            "  flag-evidence:\n"
            "    description: submission\n"
            "    source_class: participant_action\n"
            "    scope_refs: [nodes.web]\n"
            "    boundary_kind: participant_submission\n"
            "    channel: api_response\n"
            "    sensitivity: redacted\n"
            "    redaction: none\n"
            "    integrity: checksum\n"
            "    retention: study_lifetime\n"
            "    loss_disclosure: required\n"
            "propositions:\n"
            "  flag-correct:\n"
            "    description: submitted flag equals generated flag\n"
            "    subjects: [nodes.web]\n"
            "    basis: observed_state\n"
            "    evidence_requirements: [flag-evidence]\n"
            "    predicate:\n"
            "      kind: string\n"
            "      property: submitted.flag\n"
            "      semantic_ref: urn:techvault:flag\n"
            "      operator: equals\n"
            "      expected_from: {generated_artifact: flag, output: value}\n" + _MODULE_FLAG
        )
        scenario = parse_sdl_file(_write_module_with_import(tmp_path, body))
        assert "shared.flag" in scenario.generated_artifacts
        sources = [
            p.predicate.expected_from
            for p in scenario.propositions.values()
            if getattr(p.predicate, "expected_from", None) is not None
        ]
        assert len(sources) == 1
        assert sources[0].generated_artifact == "shared.flag"
