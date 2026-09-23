"""Verify engine outcomes as well as the retained probe's effect observations."""

import asyncio
import json
from pathlib import Path


def verify(results):
    for attempts in (2, 1):
        result = results[f"temporal-crash-{attempts}"]
        assert result["after_recovery"]["effects"] == attempts
        if attempts == 2:
            assert result.get("result") == "effect-returned"
            assert "error_type" not in result
        else:
            assert result.get("error_type") == "WorkflowFailureError"
            assert "result" not in result
    for mode, count in (("uncooperative", 1), ("cooperative", 0)):
        result = results[f"temporal-cancel-{mode}"]
        assert result["later"]["effects"] == count
        if mode == "cooperative":
            assert result["workflow_status"] == "CANCELED"
            assert result.get("error_type") == "WorkflowFailureError"
            assert "result" not in result
        else:
            assert result["workflow_status"] == "COMPLETED"
            assert result.get("result") == "effect-returned"
            assert "error_type" not in result


def main():
    # Keep the original source byte-for-byte reproducible; verify its fresh output.
    from probe_temporal import main as run_probe

    output = Path("results/temporal.json")
    if output.exists():
        raise RuntimeError("use a fresh experiment directory")
    asyncio.run(run_probe())
    verify(json.loads(output.read_text()))
    print("Temporal recovery and cancellation outcomes verified", flush=True)


if __name__ == "__main__":
    main()
