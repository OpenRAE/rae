"""Fixed-path offline producer: python -m implementations.formal.participant_crossing."""

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Construct or check the complete crossing model bundle.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Publish a new bundle; refuse existing drift.",
    )
    parser.add_argument(
        "--profile",
        choices=("single", "multi"),
        default="single",
        help="Select the exact governed construction profile.",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    try:
        if args.profile == "multi":
            from .multi_export import check, publish
        else:
            from .export import check, publish

        (publish if args.write else check)(root)
    except (OSError, ValueError):
        print("participant-crossing model export failed validation", file=sys.stderr)
        return 1
    print("participant-crossing model bundle verified; no equivalence result claimed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
