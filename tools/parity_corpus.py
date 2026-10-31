"""Record and check the golden parity corpus of the Python implementation (issue #1778).

The corpus records the machine-readable behavior of each exposed surface. The
Go checker in ``implementations/go/internal/parity`` compares the Go
implementation with it, and after the cutover it stays as a regression suite.

The corpus lives in ``implementations/go/internal/parity/testdata``:

- ``manifest.json`` names the corpus schema and the last commit that changed
  the Python implementation.
- ``inputs/<sha256>`` holds the bytes of each input file once.
- ``cases/<surface>/<command>/<sha256 of the name>.json`` holds one recorded
  invocation: its name, surface, command, arguments, input files by digest, and
  result. The name follows the input path; the file name does not, because
  repository path policy reserves some fixture path names.

The ``cli`` surface runs the ``raes`` command. Its result is the exit code and
the JSON standard output. The free-text ``message`` of each diagnostic is not
parity data, so the recording drops it. The ``schema`` surface validates each
contract fixture against its published schema, and its result is the verdict.
The ``canonical`` surface encodes each JSON fixture and each edge input in the
RFC 8785 form and in the two sorted ``json.dumps`` forms. Its result is the
digest of each encoding, or ``null`` when the encoding refuses the input. The
``randstream`` surface runs the random-stream engine on each published vector:
its result is the stream key, the canonical address bytes, the raw block, and
the bounded draw of the vector.

``record`` writes the corpus. ``check`` records into memory and fails when the
committed corpus differs, and it can write the fresh corpus for review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
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
from raes_contracts.json_serialization import (  # noqa: E402
    sorted_json_text_finite,
    sorted_json_text_unicode_finite,
)
from raes_contracts.operational_logging import run_application  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

CORPUS_DIR = Path("implementations/go/internal/parity/testdata")
PYTHON_DIR = "implementations/python"
SCHEMA = "raes-parity-corpus/v1"
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
# JSON texts at the edges of the canonical forms: number notation, the exact
# integer range of RFC 8785, string escapes, and the two key orders.
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
    '  { "a" : [ ] }  ',
    "true",
    "null",
    "[1, 2] 3",
    "NaN",
)


@dataclass(frozen=True)
class Case:
    """One invocation of a surface command with its input files."""

    surface: str
    command: str
    name: str
    args: tuple[str, ...]
    files: Mapping[str, bytes]

    @property
    def path(self) -> Path:
        """Return the case file path relative to the corpus directory."""

        return Path("cases", self.surface, self.command.replace(" ", "-"), digest(self.name.encode()) + ".json")


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
            for kind in ("valid", "invalid"):
                for fixture in sorted((directory / kind).glob("*.json")):
                    yield contract, fixture


def portable_cases(repo: Path, contracts: Iterable[str]) -> Iterator[Case]:
    """Yield the semantic commands over each portable contract fixture."""

    first: tuple[str, Path] | None = None
    for contract, fixture in contract_fixtures(repo, contracts):
        first = first or (contract, fixture)
        for command in PORTABLE_COMMANDS:
            yield semantic_case(command, contract, fixture, repo)
    if first is None:
        return
    contract, fixture = first
    for command in UNSUPPORTED_PORTABLE_COMMANDS:
        yield semantic_case(command, contract, fixture, repo)
    yield semantic_case("validate", "unknown-contract-v1", fixture, repo, name="unknown-contract")


def supported_contracts() -> list[str]:
    """Return the published contracts that the semantic commands accept."""

    return [contract for contract in schema_bundle() if contract_payload_root(contract) is not None]


def schema_cases(repo: Path) -> Iterator[Case]:
    """Yield the schema verdict for each fixture of each published contract."""

    contracts = sorted(path.stem for path in (repo / PUBLICATION_ENTRIES).glob("*.json"))
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

    for fixture in sorted((repo / "contracts" / "fixtures").rglob("*.json")):
        name = fixture.relative_to(repo).with_suffix("").as_posix()
        yield Case(
            surface="canonical",
            command="encode",
            name=name,
            args=(),
            files={"value.json": fixture.read_bytes()},
        )
    for index, text in enumerate(CANONICAL_EDGE_TEXTS):
        yield Case(
            surface="canonical",
            command="encode",
            name=f"edge/{index:02d}",
            args=(),
            files={"value.json": text.encode()},
        )


def randstream_cases(repo: Path) -> Iterator[Case]:
    """Yield each published random-stream vector."""

    for vector in sorted((repo / "contracts" / "fixtures" / "random-stream-vectors").rglob("*.json")):
        name = vector.relative_to(repo).with_suffix("").as_posix()
        yield Case(
            surface="randstream", command="vector", name=name, args=(), files={"vector.json": vector.read_bytes()}
        )


def all_cases(repo: Path) -> list[Case]:
    """Return every case of the corpus, sorted by case path."""

    cases = [
        *sdl_cases(repo),
        *portable_cases(repo, supported_contracts()),
        *schema_cases(repo),
        *canonical_cases(repo),
        *randstream_cases(repo),
    ]
    return sorted(cases, key=lambda case: case.path)


def normalized_output(stdout: str) -> object:
    """Return JSON standard output without diagnostic messages, or ``None`` for other output."""

    try:
        output = json.loads(stdout)
    except ValueError:
        return None
    if isinstance(output, dict) and isinstance(output.get("diagnostics"), list):
        for diagnostic in output["diagnostics"]:
            if isinstance(diagnostic, dict):
                diagnostic.pop("message", None)
    return output


def run_cli(case: Case) -> dict[str, object]:
    """Run one CLI case in an isolated directory and return its exit code and output."""

    runner = CliRunner()
    with runner.isolated_filesystem():
        for name, content in case.files.items():
            Path(name).write_bytes(content)
        result = runner.invoke(app, list(case.args), catch_exceptions=False)
    return {"exit_code": result.exit_code, "stdout": normalized_output(result.stdout)}


def run_schema(repo: Path, case: Case) -> dict[str, object]:
    """Validate the payload of a schema case against the published schema of its contract."""

    (contract,) = case.args
    entry = json.loads((repo / PUBLICATION_ENTRIES / f"{contract}.json").read_text(encoding="utf-8"))
    schema = json.loads((repo / entry["schema_path"]).read_text(encoding="utf-8"))
    try:
        payload = json.loads(case.files["payload.json"])
    except ValueError:
        return {"valid": False}
    return {"valid": Draft202012Validator(schema).is_valid(payload)}


def _reject_constant(constant: str) -> object:
    raise ValueError(constant)


def run_canonical(case: Case) -> dict[str, object]:
    """Return the digest of each canonical encoding of a JSON value, or ``None`` when it refuses."""

    try:
        value = json.loads(case.files["value.json"], parse_constant=_reject_constant)
    except ValueError:
        value = ValueError
    encoders = {
        "jcs": canonical_json_bytes,
        "sorted_ascii": lambda value: sorted_json_text_finite(value).encode(),
        "sorted_unicode": lambda value: sorted_json_text_unicode_finite(value).encode(),
    }
    result: dict[str, object] = {}
    for form, encode_value in encoders.items():
        try:
            result[form] = None if value is ValueError else sha256_digest(encode_value(value))
        except ValueError, TypeError, UnicodeError:
            result[form] = None
    return result


def run_randstream(case: Case) -> dict[str, object]:
    """Run the random-stream engine on the inputs of a published vector."""

    vector = json.loads(case.files["vector.json"])
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


def run(repo: Path, case: Case) -> dict[str, object]:
    """Return the result of one case."""

    runners = {"cli": run_cli, "canonical": run_canonical, "randstream": run_randstream}
    if case.surface in runners:
        return runners[case.surface](case)
    return run_schema(repo, case)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def encode(document: object) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def case_document(case: Case, result: Mapping[str, object]) -> dict[str, object]:
    """Return the JSON document that records one case and its result."""

    return {
        "name": case.name,
        "surface": case.surface,
        "command": case.command,
        "args": list(case.args),
        "files": {name: digest(content) for name, content in sorted(case.files.items())},
        "result": dict(result),
    }


def build_corpus(repo: Path, cases: Iterable[Case], commit: str) -> dict[Path, bytes]:
    """Record each case and return the corpus files by path."""

    files = {MANIFEST: encode({"schema": SCHEMA, "python_commit": commit})}
    for case in cases:
        files[case.path] = encode(case_document(case, run(repo, case)))
        for content in case.files.values():
            files[Path("inputs", digest(content))] = content
    return files


def python_commit(repo: Path) -> str:
    """Return the last commit that changed the Python implementation."""

    completed = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", PYTHON_DIR],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


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
    """Describe each corpus file that differs. The recorded Python commit is provenance, not data."""

    differences = []
    for path in sorted(set(recorded) | set(committed)):
        if path not in committed:
            differences.append(f"missing: {path}")
        elif path not in recorded:
            differences.append(f"unexpected: {path}")
        elif path == MANIFEST:
            if json.loads(recorded[path])["schema"] != json.loads(committed[path]).get("schema"):
                differences.append(f"changed: {path}")
        elif recorded[path] != committed[path]:
            differences.append(f"changed: {path}")
    return differences


def parse_args(argv: Iterable[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record or check the golden parity corpus.")
    parser.add_argument("mode", choices=("record", "check"))
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="With check: write the recorded corpus here when it differs.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo = args.repo_root.resolve()
    recorded = build_corpus(repo, all_cases(repo), python_commit(repo))
    if args.mode == "record":
        write_corpus(repo / CORPUS_DIR, recorded)
        print(f"parity corpus: recorded {len(recorded)} files")
        return 0
    differences = corpus_differences(recorded, read_corpus(repo / CORPUS_DIR))
    if not differences:
        print(f"parity corpus: {len(recorded)} files match")
        return 0
    for difference in differences[:50]:
        print(f"parity corpus: {difference}", file=sys.stderr)
    print(
        f"parity corpus: {len(differences)} files differ; record the corpus again",
        file=sys.stderr,
    )
    if args.output_dir is not None:
        write_corpus(args.output_dir, recorded)
    return 1


if __name__ == "__main__":
    raise SystemExit(run_application(main))
