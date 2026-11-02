"""Bounded opaque storage for corpus v2, with decoded credential scanning."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from tools.parity_support import digest, encode

INLINE_BYTES = 256 * 1024
MAX_BLOB_BYTES = 64 * 1024 * 1024
MAX_PARTS = 512


def pack(files: Mapping[Path, bytes]) -> tuple[dict[Path, bytes], dict[str, bytes]]:
    output: dict[Path, bytes] = {}
    blobs: dict[str, bytes] = {}
    for path, content in files.items():
        if path.parts[0] == "inputs":
            blobs[path.name] = content
        elif path.suffix == ".json" and len(content) > INLINE_BYTES:
            identity = digest(content)
            blobs[identity] = content
            output[path] = encode({"document_ref": identity})
        else:
            output[path] = content
    for identity, content in blobs.items():
        if len(content) > MAX_BLOB_BYTES:
            raise ValueError("a parity input exceeds the bounded storage limit")
        compressed = gzip.compress(content, mtime=0)
        if len(compressed) <= INLINE_BYTES:
            output[Path("inputs", identity)] = compressed
        else:
            pieces = [compressed[index : index + INLINE_BYTES] for index in range(0, len(compressed), INLINE_BYTES)]
            output[Path("inputs", identity)] = encode({"parts": len(pieces)})
            for index, piece in enumerate(pieces):
                output[Path("pieces", identity, str(index))] = b"\x00" + piece
    return output, blobs


def read_blob(root: Path, identity: str) -> bytes:
    if (
        not isinstance(identity, str)
        or len(identity) != 64
        or any(character not in "0123456789abcdef" for character in identity)
    ):
        raise ValueError("invalid parity blob identity")
    with (root / "inputs" / identity).open("rb") as stream:
        data = stream.read(INLINE_BYTES + 1)
    if len(data) > INLINE_BYTES:
        raise ValueError("an encoded parity input exceeds its piece limit")
    if not data.startswith(b"\x1f\x8b"):
        data = read_pieces(root, identity, data)
    with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as stream:
        content = stream.read(MAX_BLOB_BYTES + 1)
    if len(content) > MAX_BLOB_BYTES or digest(content) != identity:
        raise ValueError("a parity input is oversized or does not match its digest")
    return content


def read_pieces(root: Path, identity: str, data: bytes) -> bytes:
    index = json.loads(data)
    if set(index) != {"parts"} or type(index["parts"]) is not int or not 0 < index["parts"] <= MAX_PARTS:
        raise ValueError("invalid parity input piece index")
    parts = []
    for number in range(index["parts"]):
        with (root / "pieces" / identity / str(number)).open("rb") as stream:
            piece = stream.read(INLINE_BYTES + 2)
        if not piece.startswith(b"\x00") or len(piece) > INLINE_BYTES + 1:
            raise ValueError("invalid parity input piece")
        parts.append(piece[1:])
    return b"".join(parts)


def read_document(root: Path, path: Path) -> object:
    document = json.loads((root / path).read_bytes())
    if isinstance(document, dict) and set(document) == {"document_ref"}:
        return json.loads(read_blob(root, document["document_ref"]))
    return document


def scan(root: Path, repo: Path) -> int:
    # The existing installer supplies the reviewed binary; never trust PATH.
    repo = repo.resolve()
    root = root.resolve()
    packages = repo / "implementations/python/packages"
    if str(packages) not in sys.path:
        sys.path.insert(0, str(packages))
    from tools.gitleaks_tool import ensure_gitleaks

    if not root.exists():
        return 0
    return subprocess.call(
        [
            str(ensure_gitleaks(repo)),
            "dir",
            "--no-banner",
            "--redact=100",
            "--config",
            str(repo / ".gitleaks.toml"),
            "--",
            "./" + root.name,
        ],
        cwd=root.parent,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("scan", "unpack"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "scan":
        return scan(args.root, args.repo_root)
    if args.output is None:
        parser.error("unpack requires --output")
    else:
        args.output.mkdir(parents=True, exist_ok=True)
        for path in sorted((args.root / "inputs").iterdir()):
            (args.output / path.name).write_bytes(read_blob(args.root, path.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
