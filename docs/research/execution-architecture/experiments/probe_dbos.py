import json
from pathlib import Path
import subprocess
import sys

from witness import Witness, observe, record


def worker(phase, key, url, guard):
    return subprocess.run(
        [sys.executable, "dbos_worker.py", phase, key, url, guard],
        capture_output=True,
        text=True,
        timeout=45,
    )


def main():
    Path("results").mkdir(exist_ok=True)
    results = {}
    with Witness() as witness:
        for guard in ("unguarded", "guarded"):
            key = "dbos-r2-" + guard
            first = worker("start", key, witness.url, guard)
            assert first.returncode == 73, first.stderr
            after_crash = observe(witness.url, key)
            second = worker("recover", key, witness.url, guard)
            assert second.returncode == 0, second.stderr
            results[guard] = {
                "worker_crash_exit": first.returncode,
                "after_crash": after_crash,
                "after_recovery": observe(witness.url, key),
                "worker": json.loads(Path("results", key + "-worker.json").read_text()),
            }
            assert results[guard]["after_recovery"]["effects"] == (
                2 if guard == "unguarded" else 1
            )
        key = "dbos-r2-cancel"
        cancellation = worker("cancel", key, witness.url, "unguarded")
        assert cancellation.returncode == 0, cancellation.stderr
        results["cancellation"] = json.loads(
            Path("results", key + "-worker.json").read_text()
        )
        assert results["cancellation"]["later"]["effects"] == 1
        assert not results["cancellation"]["following_step_executed"]
    record("dbos", results)


if __name__ == "__main__":
    main()
