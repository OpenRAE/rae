"""Re-record only the changed satisfiability CLI surface through its real owner."""

import hashlib
import json
import subprocess
from pathlib import Path

from tools.parity_corpus import run
from tools.parity_storage import pack, read_blob, read_document
from tools.parity_support import Case, encode

root = Path.cwd()
corpus = root / "implementations/go/internal/parity/testdata"
changed = []
for path in sorted((corpus / "cases/cli/processor-satisfiability").glob("*.json")):
    original = subprocess.check_output(["git", "show", "HEAD:" + str(path.relative_to(root))])
    row = read_document(corpus, path.relative_to(corpus))
    files = {name: read_blob(corpus, ref.removeprefix("sha256:")) for name, ref in row.get("files", {}).items()}
    case = Case(row["surface"], row["command"], row["name"], tuple(row["args"]), files)
    row["result"] = run(root, case)
    data = encode(row)
    packed, _ = pack({path.relative_to(corpus): data})
    for relative, content in packed.items():
        target = corpus / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    changed.append(
        {
            "path": str(path.relative_to(root)),
            "previous_sha256": hashlib.sha256(original).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    )
sources = {
    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for base in [
        "implementations/python/packages/raes_processor/satisfiability",
        "implementations/python/packages/raes_contracts",
    ]
    for p in sorted((root / base).rglob("*.py"))
}
sources["implementations/python/packages/raes/canonical.py"] = hashlib.sha256(
    (root / "implementations/python/packages/raes/canonical.py").read_bytes()
).hexdigest()
manifest = {
    "format_version": 1,
    "reason": "Authorized breaking correction of Python serialization; schema v2, snapshot profile v3. Only the satisfiability CLI surface is re-recorded. Global corpus manifest identifies the original capture; this source-hashed amendment identifies these replacement records.",
    "command": "PYTHONPATH=. PYTHONHASHSEED=0 implementations/python/.venv/bin/python implementations/go/processor/analysis/testdata/reference_cli_driver.py",
    "source_sha256": sources,
    "cases": changed,
}
(root / "implementations/go/processor/analysis/testdata/cli-v2-provenance.json").write_text(
    json.dumps(manifest, indent=2) + "\n"
)
print("recorded", len(changed))
