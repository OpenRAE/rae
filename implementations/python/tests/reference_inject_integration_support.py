"""Real-container inject setup using the existing reviewed-image integration harness."""

from __future__ import annotations

import contextlib
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep

from raes import canonical_instantiated_sdl_digest, instantiate_scenario, parse_sdl
from raes_contracts.associated_artifacts import associated_artifact_set_digest
from raes_contracts.canonical import canonical_json_bytes
from raes_contracts.contracts import (
    AssociatedArtifactManifestModel,
    InjectOrderModel,
    InjectTriggerRequestModel,
    OperationArtifactReferenceModel,
)
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.runtime_state import OperationState
from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.planner import plan
from raes_reference_backend import create_reference_backend_target
from raes_reference_backend.drivers.oci import ImageTrustPolicy, OciDeploymentDriver
from raes_reference_backend.drivers.oci_inject import OciInjectDriver
from raes_reference_backend.inject_bindings import OciInjectPermit, OciInjectProbe, OciInjectProgram
from raes_reference_backend.inject_evidence import artifact_manifest, manifest_reference
from raes_reference_backend.inject_execution import ReferenceOciInjectExecutor
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_profiles import ControlPlaneProfile
from raes_runtime.control_plane_store_local import LocalControlPlaneStore

AFTER = b"authored-world-content"
_SERVER = r"""mkdir -p /tmp/inject-www/cgi-bin
printf '%s' before > /tmp/world-state
printf '%s' ready > /tmp/inject-www/index.html
cat > /tmp/inject-www/cgi-bin/inject <<'RAES_CGI'
#!/bin/sh
printf '%s' "$QUERY_STRING" > /tmp/world-state
printf 'Content-Type: text/plain\r\n\r\nok\n'
RAES_CGI
chmod 755 /tmp/inject-www/cgi-bin/inject
exec httpd -f -p 19067 -h /tmp/inject-www
"""


def _source_manifest(scenario, descriptor, timestamp):
    manifest = AssociatedArtifactManifestModel(
        schema_version="associated-artifact-manifest/v1",
        manifest_id="concrete-inject-source",
        manifest_version="1",
        canonicalization_profile="associated-artifact-set/v1",
        scope="scenario",
        parent_ref={"ref_kind": "scenario", "ref_id": scenario.name},
        set_digest="sha256:" + "0" * 64,
        artifacts={
            "inject-source": {
                "artifact_id": "inject-source",
                "role": "configuration",
                "media_type": "application/json",
                "uri": "urn:raes:concrete-inject:source",
                "checksum": {"algorithm": "sha256", "value": hashlib.sha256(descriptor).hexdigest()},
                "size_bytes": len(descriptor),
                "created_at": timestamp,
                "source": "operator-admitted-CI-image",
                "sensitivity": "public",
            }
        },
    )
    return manifest.model_copy(update={"set_digest": associated_artifact_set_digest(manifest)})


@dataclass
class ConcreteInjectRun:
    driver: OciDeploymentDriver
    program: OciInjectProgram
    request: InjectTriggerRequestModel
    ledger: Path
    execution_plan: object
    plane: RuntimeControlPlane | None = None
    executor: ReferenceOciInjectExecutor | None = None

    def reopen(self):
        if self.plane is not None:
            self.plane.close()
        self.executor = ReferenceOciInjectExecutor(self.driver, programs=(self.program,))
        target = create_reference_backend_target(driver=self.driver, inject_execution=self.executor)
        self.plane = RuntimeControlPlane(
            target,
            store=LocalControlPlaneStore(self.ledger),
            profile=ControlPlaneProfile.P1,
            inject_execution=self.executor,
            operation_evidence=self.executor,
        )
        self.executor.bind_record_reader(lambda operation_id: self.plane._store.load_records().get(operation_id))
        return self.plane


@contextlib.contextmanager
def concrete_inject_run(container_runtime, tmp_path, *, failed_entrypoint=False):
    from test_reference_backend_docker_integration import realized, run_workspace

    workspace = run_workspace("inject")
    tag = f"raes-inject-ci-{workspace}:1"
    driver = OciDeploymentDriver(
        runtime=container_runtime.runtime,
        workspace=workspace,
        image_policy=ImageTrustPolicy(allowed_images=(container_runtime.image.reference, tag)),
    )
    native = OciInjectDriver(driver)
    context = tmp_path / "inject-image-context"
    context.mkdir()
    url = "http://127.0.0.1:19067/cgi-bin/inject?" + AFTER.decode("ascii")
    command = ["wget", "-q", "-T", "5", "-O", "/dev/null", url]
    if failed_entrypoint:
        command = ["/bin/sh", "-c", " ".join(command) + "; exit 7"]
    (context / "Dockerfile").write_text(f"FROM {container_runtime.image.reference}\nCMD {json.dumps(command)}\n")
    native.call(
        ["build", "--pull=false", "--network=none", "--tag", tag, str(context)],
        deadline=monotonic() + 90,
        max_output_bytes=65536,
    )
    run = None
    try:
        source_id = (
            native.call(["image", "inspect", "--format", "{{.Id}}", "--", tag], deadline=monotonic() + 5)
            .decode()
            .strip()
        )
        scenario = parse_sdl(f"""name: concrete-inject-world
nodes:
  host:
    type: compute
    source: {container_runtime.image.reference}
    resources: {{ram: 1 gib, cpu: 1}}
    roles: {{operator: ops}}
    injects: {{release: operator}}
injects:
  release:
    source: {{name: inject-source, version: '1'}}
""")
        target = create_reference_backend_target(driver=driver)
        execution_plan = plan(compile_scenario_runtime_model(scenario), target.manifest)
        with realized(driver, workspace=workspace, runtime=container_runtime.runtime):
            with RuntimeControlPlane(target) as provisioner:
                provisioner.register_planner_produced_plan(execution_plan)
                receipt = provisioner.submit_provisioning(execution_plan.provisioning)
                assert provisioner.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
                snapshot = provisioner.snapshot
            node_id = driver._native_ids["provision.node.host"]
            native.call(["exec", "--detach", "--", node_id, "/bin/sh", "-c", _SERVER], deadline=monotonic() + 5)
            for attempt in range(30):
                try:
                    native.call(
                        ["exec", "--", node_id, "wget", "-q", "-T", "1", "-O", "/dev/null", "http://127.0.0.1:19067/"],
                        deadline=monotonic() + 2,
                    )
                    break
                except ValueError:
                    if attempt == 29:
                        raise
                    sleep(0.1)
            binding = native.binding(
                "orchestration.inject-binding.host.release", "provision.node.host", deadline=monotonic() + 5
            )
            request = InjectTriggerRequestModel(
                request_key="concrete-request-1",
                occurrence_id="concrete-occurrence-1",
                target_scope="target:reference-emulation",
                run_scope="run:default",
                inject="orchestration.inject.release",
                bindings=(binding,),
                placement={"kind": "independent"},
                expected_head="inject-order:genesis",
                plan={
                    "contract_id": "orchestration-plan-v1",
                    "artifact_id": "concrete-plan",
                    "digest": runtime_plan_digest(execution_plan.orchestration),
                },
            )
            order = InjectOrderModel(scope=request.run_scope, predecessor=request.expected_head, position=1)
            timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            evidence = artifact_manifest(
                scenario,
                "concrete-order-permit",
                {
                    "ordered-request": canonical_json_bytes(
                        {"request": request.model_dump(mode="json"), "order": order.model_dump(mode="json")}
                    )
                },
                timestamp,
            )
            descriptor = canonical_json_bytes(
                {"profile": "reference-oci-entrypoint/v1", "image": tag, "image_config_digest": source_id}
            )
            program = OciInjectProgram(
                scenario=scenario,
                scenario_reference=OperationArtifactReferenceModel(
                    contract_id="instantiated-scenario-v1",
                    artifact_id=scenario.name,
                    digest=canonical_instantiated_sdl_digest(instantiate_scenario(scenario)).value,
                ),
                plan=execution_plan.orchestration,
                source_manifest=_source_manifest(scenario, descriptor, timestamp),
                source_descriptor=descriptor,
                probes=(OciInjectProbe(binding=binding, path="/tmp/world-state", before=b"before", after=AFTER),),
                permits=(OciInjectPermit(request, order, (manifest_reference(evidence),)),),
            )
            ledger = tmp_path / "inject-ledger"
            seed = LocalControlPlaneStore(ledger)
            lease = seed.admit_runtime(target_scope=request.target_scope, run_scope=request.run_scope)
            try:
                seed.save_snapshot(snapshot, expected_revision=0)
            finally:
                seed.close()
                lease.close()
            run = ConcreteInjectRun(driver, program, request, ledger, execution_plan)
            run.reopen().register_planner_produced_plan(execution_plan)
            try:
                yield run
            finally:
                if getattr(run.plane, "_runtime_ready", False) is False:
                    run.reopen()
                records = list(run.plane._store.load_records().values())
                run.plane.close()
                for record in records:
                    if record.inject_occurrence is not None and record.invocation.consumed:
                        for probe in program.probes:
                            native.remove(record.invocation.request, probe, program.source, deadline=monotonic() + 5)
    finally:
        native.call(["image", "rm", "--", tag], deadline=monotonic() + 10)
