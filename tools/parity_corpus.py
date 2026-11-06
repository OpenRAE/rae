"""Record and check the golden parity corpus of the Python implementation (issue #1778).

The corpus records the machine-readable behavior of each exposed surface. The
Go checker in ``implementations/go/internal/parity`` compares the Go
implementation with it, and after the cutover it stays as a regression suite.

The corpus lives in ``implementations/go/internal/parity/testdata``:

- ``manifest.json`` names the corpus schema.
- ``inputs/<sha256>`` holds the bytes of each input file once.
- ``cases/<surface>/<command>/<sha256 of the name>.json`` holds one recorded
  invocation: its name, surface, command, arguments, input files by digest, and
  result. The name follows the input path; the file name does not, because
  repository path policy reserves some fixture path names.

The ``cli`` surface runs the ``raes`` command. Its result is the exit code and
the JSON standard output. The free-text ``message`` of each diagnostic is not
parity data, so the recording drops it. The ``schema`` surface validates each
contract fixture against its published schema, and its result is the verdict.

``record`` writes the corpus. ``check`` records into memory and fails when the
committed corpus differs, and it can write the fresh corpus for review.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from jsonschema import Draft202012Validator  # noqa: E402
from raes_cli.main import app  # noqa: E402
from raes_conformance.conformance import contract_payload_root  # noqa: E402
from raes_contracts import random_stream_engine  # noqa: E402
from raes_contracts.canonical import canonical_json_bytes  # noqa: E402
from raes_contracts.contracts import schema_bundle  # noqa: E402
from raes_contracts.contracts.random_stream import (  # noqa: E402
    ParticipantStreamAddressModel,
    PublicSeedModel,
    StreamAddressModel,
)
from raes_contracts.digests import sha256_digest  # noqa: E402
from raes_contracts.json_serialization import sorted_json_text_finite, sorted_json_text_unicode_finite  # noqa: E402
from raes_contracts.operational_logging import run_application  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from tools import parity_primitives, parity_shared  # noqa: E402
from tools.parity_records import case_document  # noqa: E402
from tools.parity_support import REQUEST_FILE, Case, digest, encode, json_output  # noqa: E402

CORPUS_DIR = Path("implementations/go/internal/parity/testdata")
SCHEMA = "raes-parity-corpus/v2"
JSON_FILES = "*.json"

CANONICAL_VALUE = "value.json"

RANDSTREAM_VECTOR = "vector.json"

CANONICAL_EDGE_TEXTS = (
    "1.0",
    "1e16",
    "1e15",
    "0.0001",
    "0.00001",
    "-0.0",
    "1e-7",
    "123456789.123",
    "1.5e300",
    "5e-324",
    "1.7976931348623157e308",
    "1e400",
    "-1e400",
    "9007199254740991",
    "9007199254740992",
    "-9007199254740991",
    "-9007199254740992",
    "123456789012345678901234567890",
    "-0",
    r'"é   😀 \u007f"',
    r'"\u0000\u001f\"\\\/\b\f\n\r\t</script>&"',
    '"é\U0001f600"',
    r'{"": 1, "😀": 2, "a": 3}',
    '{"b": [1, 2.5, {"d": null, "c": true}], "a": ""}',
    '{"a": 1, "a": 2}',
    '  { "a" : [ ] }',
    "true",
    "null",
    "[1, 2] 3",
    "NaN",
    "-" + "9" * 4300,
    "9" * 4301,
    r'"\ud800"',
    r'"\uDFFF"',
    r'"\ud800x\udfff"',
    r'"\ud800\ud800\udc00"',
    r'["\udc00", "\ufffd", "\\ud800", "\ud83d\ude00"]',
    r'{"\ud800":1,"\ufffd":2,"\ud800":3,"😀":4,"\ue000":5}',
    r'{"\ud83d\ude00":1,"😀":2}',
    r'{"a":"\ud800","a":1}',
    '{"a":' + "9" * 4301 + ',"a":1}',
)

SDL_CONTRACT = "sdl-yaml/v1"
SDL_COMMANDS = (
    "parse",
    "validate",
    "normalize",
    "resolve",
    "compile",
    "inspect",
    "conformance",
)
SDL_TRANSFORMS = ("canonical", "format")
PORTABLE_COMMANDS = ("validate", "inspect", "conformance")
# A portable contract rejects these commands in the same way for each contract.
UNSUPPORTED_PORTABLE_COMMANDS = ("parse", "normalize", "resolve", "compile")
MANIFEST = Path("manifest.json")
PUBLICATION_ENTRIES = Path("contracts/schema-publication/entries")


def semantic_case(command: str, contract: str, source: Path, repo: Path, *options: str, name: str = "") -> Case:
    """Return a ``raes semantic`` case for one input file."""

    case_name = source.relative_to(repo).with_suffix("").as_posix()
    if options or name:
        case_name += "/" + (name or "-".join(option.lstrip("-") for option in options))
    input_name = "input" + source.suffix
    return Case(
        surface="cli",
        command="semantic " + command,
        name=case_name,
        args=(
            "semantic",
            command,
            "--output",
            "json",
            "--contract",
            contract,
            *options,
            input_name,
        ),
        files={input_name: source.read_bytes()},
    )


def sdl_cases(repo: Path) -> Iterator[Case]:
    """Yield the semantic commands over each SDL example and each SDL source fixture."""

    fixtures = repo / "contracts" / "fixtures" / "sdl" / "sdl-yaml-v1"
    for source in sorted([*(repo / "examples" / "scenarios").rglob("*.yaml"), *fixtures.rglob("*.yaml")]):
        option_sets: list[tuple[str, ...]] = [()]
        if source.is_relative_to(fixtures) and "migration" in source.relative_to(fixtures).parts:
            option_sets.append(("--migration-policy", "accept"))
        for options in option_sets:
            for command in SDL_COMMANDS:
                yield semantic_case(command, SDL_CONTRACT, source, repo, *options)
            for transform in SDL_TRANSFORMS:
                yield semantic_case(
                    "transform",
                    SDL_CONTRACT,
                    source,
                    repo,
                    *options,
                    "--transform",
                    transform,
                )


def contract_fixtures(repo: Path, contracts: Iterable[str]) -> Iterator[tuple[str, Path]]:
    """Yield each valid and invalid fixture of each contract."""

    root = repo / "contracts" / "fixtures"
    for contract in sorted(contracts):
        for directory in sorted(path for path in root.rglob(contract) if path.is_dir()):
            for fixture in sorted(
                directory.rglob(JSON_FILES),
                key=lambda path: (
                    {"valid": 0, "invalid": 1}.get(path.relative_to(directory).parts[0], 2),
                    path.as_posix(),
                ),
            ):
                yield contract, fixture


def portable_cases(repo: Path, contracts: Iterable[str]) -> Iterator[Case]:
    """Yield the semantic commands over each portable contract fixture.

    Over the first fixture, it also yields the refused commands and an unknown contract.
    """

    fixtures = list(contract_fixtures(repo, contracts))
    for contract, fixture in fixtures:
        for command in PORTABLE_COMMANDS:
            yield semantic_case(command, contract, fixture, repo)
    for contract, fixture in fixtures[:1]:
        for command in UNSUPPORTED_PORTABLE_COMMANDS:
            yield semantic_case(command, contract, fixture, repo)
        yield semantic_case("validate", "unknown-contract-v1", fixture, repo, name="unknown-contract")


def supported_contracts() -> list[str]:
    """Return the published contracts that the semantic commands accept."""

    return [contract for contract in schema_bundle() if contract_payload_root(contract) is not None]


def schema_cases(repo: Path) -> Iterator[Case]:
    """Yield the schema verdict for each fixture of each published contract."""

    contracts = sorted(path.stem for path in (repo / PUBLICATION_ENTRIES).glob(JSON_FILES))
    for contract, fixture in contract_fixtures(repo, contracts):
        yield Case(
            surface="schema",
            command="validate",
            name=fixture.relative_to(repo).with_suffix("").as_posix(),
            args=(contract,),
            files={"payload.json": fixture.read_bytes()},
        )


def canonical_cases(repo: Path) -> Iterator[Case]:
    """Yield the canonical encodings of each JSON fixture and each edge input."""

    for fixture in sorted((repo / "contracts" / "fixtures").rglob(JSON_FILES)):
        name = fixture.relative_to(repo).with_suffix("").as_posix()
        yield Case(
            surface="canonical",
            command="encode",
            name=name,
            args=(),
            files={CANONICAL_VALUE: fixture.read_bytes()},
        )
    for index, text in enumerate(CANONICAL_EDGE_TEXTS):
        yield Case(
            surface="canonical",
            command="encode",
            name=f"edge/{index:02d}",
            args=(),
            files={CANONICAL_VALUE: (text + "\n").encode()},
        )


def randstream_cases(repo: Path) -> Iterator[Case]:
    """Yield each published random-stream vector."""

    for vector in sorted((repo / "contracts" / "fixtures" / "random-stream-vectors").rglob(JSON_FILES)):
        name = vector.relative_to(repo).with_suffix("").as_posix()
        yield Case(
            surface="randstream", command="vector", name=name, args=(), files={RANDSTREAM_VECTOR: vector.read_bytes()}
        )


def _reject_constant(constant: str) -> object:
    raise ValueError(constant)


def run_canonical(case: Case) -> dict[str, object]:
    """Return the digest of each canonical encoding of a JSON value, or ``None`` when it refuses."""

    encoders = {
        "jcs": canonical_json_bytes,
        "sorted_ascii": lambda value: sorted_json_text_finite(value).encode(),
        "sorted_unicode": lambda value: sorted_json_text_unicode_finite(value).encode(),
    }
    try:
        value = json.loads(case.files[CANONICAL_VALUE], parse_constant=_reject_constant)
    except ValueError:
        return dict.fromkeys(encoders)
    result: dict[str, object] = {}
    for form, encode_value in encoders.items():
        try:
            result[form] = sha256_digest(encode_value(value))
        except ValueError, TypeError:
            result[form] = None
    return result


def run_randstream(case: Case) -> dict[str, object]:
    """Run the random-stream engine on the inputs of a published vector."""

    vector = json.loads(case.files[RANDSTREAM_VECTOR])
    profile = vector["profile_id"]
    seed = random_stream_engine.decode_public_seed(PublicSeedModel.model_validate(vector["root_entropy"]))
    key = random_stream_engine.derive_stream_key(profile_id=profile, root_entropy=seed)
    model = ParticipantStreamAddressModel if profile == "blake3-xof-participant-v1" else StreamAddressModel
    address = model.model_validate(vector["address"])
    result: dict[str, object] = {
        "stream_key_hex": key.hex(),
        "address_canonical_bytes_hex": random_stream_engine.canonical_stream_address_bytes(address).hex(),
        "raw_block_hex": random_stream_engine.raw_block(profile_id=profile, stream_key=key, address=address).hex(),
    }
    transform = vector.get("transform")
    if transform is not None:
        draw = random_stream_engine.draw_bounded_integer(
            profile_id=profile,
            stream_key=key,
            address=address,
            minimum=transform["minimum"],
            maximum=transform["maximum"],
            max_rejection_attempts=transform["max_rejection_attempts"],
        )
        result["draw"] = {
            "value": None if draw.value is None else str(draw.value),
            "rejection_attempts": draw.rejection_attempts,
            "rejection_exhausted": draw.rejection_exhausted,
        }
    return result


def primitive_cases() -> Iterator[Case]:
    """Yield reproducible requests for the four input primitives."""

    for command, name, request in (
        *parity_primitives.primitive_requests(),
        *parity_primitives.compatibility_requests(),
    ):
        yield Case("primitive", command, name, (), {REQUEST_FILE: encode(request)})


def run_primitive(case: Case) -> dict[str, object]:
    """Record one reference primitive outcome."""

    return parity_primitives.run_primitive(case.command, json.loads(case.files[REQUEST_FILE]))


def shared_cases() -> Iterator[Case]:
    """Yield the remaining issue-1779 primitive requests."""
    for command, name, request in parity_shared.requests():
        yield Case("shared", command, name, (), {REQUEST_FILE: encode(request)})


def run_shared(case: Case) -> dict[str, object]:
    """Record the unchanged Python reference for a shared primitive."""
    return parity_shared.run(case.command, json.loads(case.files[REQUEST_FILE]))


def all_cases(repo: Path) -> list[Case]:
    """Enumerate the exposed registries, examples, fixtures and regressions."""
    from tools import parity_surfaces as surfaces

    sources = [path for path in surfaces.data_inputs(repo) if path.suffix in {".yaml", ".yml"}]
    cases = [
        *sdl_cases(repo),
        *portable_cases(repo, supported_contracts()),
        *schema_cases(repo),
        *canonical_cases(repo),
        *randstream_cases(repo),
        *primitive_cases(),
        *shared_cases(),
    ]
    existing_sdl = {case.name for case in cases if case.command == "semantic parse"}
    for source in sources:
        if source.relative_to(repo).with_suffix("").as_posix() not in existing_sdl:
            for command in SDL_COMMANDS:
                cases.append(semantic_case(command, SDL_CONTRACT, source, repo))
    cases.extend(surfaces.extended_cli_cases(repo, sources))
    cases.extend(surfaces.schema_source_cases(repo))
    cases.extend(surfaces.mcp_cases(repo, sources, surfaces.mcp_registry()))
    cases.extend(surfaces.http_cases(surfaces.http_schema()))
    cases.extend(surfaces.http_trace_cases())
    for surface in ("cli-schema", "mcp-schema", "http-schema"):
        cases.append(Case(surface, "registry", "reference", (), {}))
    return sorted(cases, key=lambda case: case.path)


def normalized_output(stdout: str) -> object:
    """Retain machine-readable output without free diagnostic wording."""
    return json_output(stdout)


def case_path(name: str) -> Path:
    target = Path(name)
    if target.is_absolute() or ".." in target.parts:
        raise ValueError("a corpus input path escapes its case")
    return target


def recipe_content(recipe: dict[str, str]) -> bytes:
    if recipe["kind"] == "invalid-key":
        return b"not a private key\n"
    if recipe["kind"] != "public-test-ed25519":
        raise ValueError("unknown input recipe")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(digest(recipe["seed_id"].encode()))).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def materialize_case(case: Case) -> None:
    for name, content in case.files.items():
        target = case_path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    for name, recipe in json.loads(case.files.get("input-recipes.json", b"{}")).items():
        target = case_path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(recipe_content(recipe))


def prepare_cli(runner: CliRunner, case: Case) -> None:
    setup = json.loads(case.files.get("setup.json", b"{}"))
    for directory in setup.get("directories", []):
        case_path(directory).mkdir(parents=True, exist_ok=True)
    if "store" in setup:
        from raes_runtime.control_plane_store import LocalControlPlaneStore

        store = LocalControlPlaneStore(Path(setup["store"]))
        owner = store.admit_runtime(target_scope="target:stub", run_scope="run:parity")
        store.close()
        owner.close()
    for command in setup.get("commands", []):
        runner.invoke(app, command, catch_exceptions=False)


def cli_stdout(case: Case, text: str) -> object:
    from tools.parity_surfaces import machine_text

    stdout = normalized_output(text.replace(str(Path.cwd()), "<case>"))
    if stdout is None and case.command == "root" and {"--version", "-V"}.intersection(case.args):
        stdout = text.strip()
    if stdout is None and case.command == "sdl format":
        stdout = machine_text(text)
    if stdout is None and text.strip().startswith("control-plane-store-"):
        stdout = text.strip()
    return stdout


def generated_outputs(case: Case) -> dict[str, object]:
    generated = {}
    for target in sorted(Path(".").rglob(JSON_FILES)):
        name = target.as_posix()
        content = target.read_bytes()
        if name not in case.files or case.files[name] != content:
            generated[name] = normalized_output(content.decode("utf-8").replace(str(Path.cwd()), "<case>"))
    return generated


def run_cli(case: Case) -> dict[str, object]:
    """Run a CLI case, its explicit setup, and observe generated JSON files."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        materialize_case(case)
        prepare_cli(runner, case)
        result = runner.invoke(app, list(case.args), input=case.files.get("stdin.bin"), catch_exceptions=False)
        output = {"exit_code": result.exit_code, "stdout": cli_stdout(case, result.stdout)}
        generated = generated_outputs(case)
        if generated:
            output["generated_files"] = generated
    return output


def run_schema(repo: Path, case: Case) -> dict[str, object]:
    """Validate the payload of a schema case against the published schema of its contract."""

    (contract,) = case.args
    entry = json.loads((repo / PUBLICATION_ENTRIES / f"{contract}.json").read_text(encoding="utf-8"))
    schema = json.loads((repo / entry["schema_path"]).read_text(encoding="utf-8"))
    try:
        payload = json.loads(case.files["payload.json"].decode("utf-8"), parse_constant=_reject_constant)
    except ValueError:
        return {"valid": False}
    return {"valid": Draft202012Validator(schema).is_valid(payload)}


def run(repo: Path, case: Case) -> dict[str, object]:
    """Invoke only the adapter explicitly named by the case."""
    from tools import parity_surfaces as surfaces

    recorders = {
        "primitive": lambda: run_primitive(case),
        "shared": lambda: run_shared(case),
        "canonical": lambda: run_canonical(case),
        "randstream": lambda: run_randstream(case),
        "cli": lambda: run_cli(case),
        "schema": lambda: run_schema(repo, case),
        "mcp": lambda: surfaces.run_mcp(case),
        "http": lambda: surfaces.run_http(case),
        "http-trace": lambda: surfaces.run_http(case),
        "cli-schema": lambda: {"commands": surfaces.cli_registry()},
        "mcp-schema": lambda: {"tools": surfaces.mcp_registry()},
        "http-schema": surfaces.http_schema,
    }
    if case.surface not in recorders:
        raise ValueError(f"unknown parity surface: {case.surface}")
    with surfaces.recording_context(case.surface + "/" + case.command + "/" + case.name):
        return recorders[case.surface]()


def provenance(repo: Path) -> dict[str, str]:
    """Identify the reference source and the locked recording environment."""

    hash_seed = os.environ.get("PYTHONHASHSEED")
    if hash_seed != "0":
        raise ValueError("reference recording requires PYTHONHASHSEED=0")
    source = "implementations/python/packages"
    commit = subprocess.check_output(
        ["git", "-C", str(repo), "log", "-1", "--format=%H", "--", source], text=True
    ).strip()
    tree = subprocess.check_output(["git", "-C", str(repo), "rev-parse", f"{commit}:{source}"], text=True).strip()
    current_tree = subprocess.check_output(["git", "-C", str(repo), "rev-parse", f"HEAD:{source}"], text=True).strip()
    if tree != current_tree:
        raise ValueError("Python source commit does not identify the current Python tree")
    return {
        "python_commit": commit,
        "python_tree": tree,
        "recorder_sha256": digest(
            encode({path.name: digest(path.read_bytes()) for path in sorted(Path(__file__).parent.glob("parity_*.py"))})
        ),
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "unicode_version": unicodedata.unidata_version,
        "hash_seed": hash_seed,
        "lock_sha256": digest((repo / "implementations/python/uv.lock").read_bytes()),
    }


def build_corpus(
    repo: Path, cases: Iterable[Case], *, inventory: Mapping[str, object] | None = None
) -> dict[Path, bytes]:
    """Record each case and return the corpus files by path."""

    files = {MANIFEST: encode({"schema": SCHEMA, "provenance": provenance(repo)})}
    if inventory is not None:
        files[Path("inventory.json")] = encode(inventory)
    for index, case in enumerate(cases, start=1):
        if index % 250 == 0:
            print(f"parity corpus: recording case {index}", file=sys.stderr, flush=True)
        if case.path in files:
            raise ValueError(f"duplicate corpus case: {case.path}")
        try:
            files[case.path] = encode(case_document(case, run(repo, case)))
        except Exception:
            print(f"parity corpus: failed {case.surface} {case.command} ({case.name})", file=sys.stderr, flush=True)
            raise
        for content in case.files.values():
            files[Path("inputs", digest(content))] = content
    return files


def read_corpus(root: Path) -> dict[Path, bytes]:
    """Return the committed corpus files by path."""

    if not root.is_dir():
        return {}
    return {path.relative_to(root): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def write_corpus(root: Path, files: Mapping[Path, bytes]) -> None:
    """Replace the corpus in root with files."""

    if root.exists():
        shutil.rmtree(root)
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def corpus_differences(recorded: Mapping[Path, bytes], committed: Mapping[Path, bytes]) -> list[str]:
    """Describe each corpus file that differs."""

    differences = []
    for path in sorted(set(recorded) | set(committed)):
        if path not in committed:
            differences.append(f"missing: {path}")
        elif path not in recorded:
            differences.append(f"unexpected: {path}")
        elif recorded[path] != committed[path]:
            differences.append(f"changed: {path}")
    return differences


def parse_args(argv: Iterable[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record or check the golden parity corpus.")
    parser.add_argument("mode", choices=("record", "check"))
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--regression-inputs", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--raw-input-dir", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="With check: write the recorded corpus here when it differs.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo = args.repo_root.resolve()
    from tools import parity_regressions as regressions
    from tools.parity_surfaces import complete_inventory

    cases = all_cases(repo)
    frozen_root = args.regression_inputs or (repo / regressions.FROZEN)
    identity = (
        regressions.source_identity(repo)
        if args.regression_inputs and not (frozen_root / "manifest.json").is_file()
        else None
    )
    captured, coverage, frozen = regressions.read_inputs(frozen_root, identity=identity)
    cases.extend(captured)
    inventory = complete_inventory(repo, cases, coverage)
    if args.require_complete and not inventory["complete"]:
        if args.output_dir is not None:
            write_corpus(args.output_dir, {Path("inventory.json"): encode(inventory)})
        print(
            "parity corpus: incomplete inventory: "
            + json.dumps(
                {
                    "missing_surfaces": inventory["missing_surfaces"],
                    "missing_inputs": inventory["missing_inputs"],
                    "regression_complete": coverage["complete"],
                }
            ),
            file=sys.stderr,
        )
        return 1
    recorded = build_corpus(repo, cases, inventory=inventory)
    recorded.update(
        {Path("regressions", name): content for name, content in frozen.items() if name.parts[0] != "blobs"}
    )
    from tools.parity_storage import pack

    recorded, raw_blobs = pack(recorded)
    if args.raw_input_dir is not None:
        args.raw_input_dir.mkdir(parents=True, exist_ok=True)
        for identity, content in raw_blobs.items():
            (args.raw_input_dir / identity).write_bytes(content)
    if args.mode == "record":
        write_corpus(repo / CORPUS_DIR, recorded)
        print(f"parity corpus: recorded {len(recorded)} files")
        return 0
    return check_recording(recorded, repo / CORPUS_DIR, args.output_dir)


def _recording_metadata_is_valid(content: bytes) -> bool:
    """Validate an existing recording receipt before accepting metadata-only drift."""
    try:
        document = json.loads(content.decode("utf-8"))
    except ValueError:
        return False
    if not isinstance(document, dict) or set(document) != {"schema", "provenance"} or document["schema"] != SCHEMA:
        return False
    provenance = document["provenance"]
    patterns = {
        "python_commit": r"[0-9a-f]{40}",
        "python_tree": r"[0-9a-f]{40}",
        "recorder_sha256": r"[0-9a-f]{64}",
        "lock_sha256": r"[0-9a-f]{64}",
        "python_version": r"[0-9]+\.[0-9]+\.[0-9]+",
        "unicode_version": r"[0-9]+\.[0-9]+\.[0-9]+",
        "hash_seed": "0",
    }
    if not isinstance(provenance, dict) or set(provenance) != set(patterns):
        return False
    return all(
        isinstance(provenance[key], str) and re.fullmatch(pattern, provenance[key]) for key, pattern in patterns.items()
    )


def check_recording(recorded: Mapping[Path, bytes], committed_root: Path, output_dir: Path | None) -> int:
    """Compare data exactly; keep historical provenance when only valid receipts differ."""
    committed = read_corpus(committed_root)
    differences = corpus_differences(recorded, committed)
    if (
        differences == [f"changed: {MANIFEST}"]
        and _recording_metadata_is_valid(committed[MANIFEST])
        and _recording_metadata_is_valid(recorded[MANIFEST])
    ):
        print("parity corpus: all data files match; retained recorded source provenance")
        return 0
    if not differences:
        print(f"parity corpus: {len(recorded)} files match")
        return 0
    for difference in differences[:50]:
        print(f"parity corpus: {difference}", file=sys.stderr)
    print(
        f"parity corpus: {len(differences)} files differ; record the corpus again",
        file=sys.stderr,
    )
    if output_dir is not None:
        write_corpus(output_dir, recorded)
    return 1


if __name__ == "__main__":
    raise SystemExit(run_application(main))
