#!/usr/bin/env python3
"""Execute a single pipeline stage."""
import argparse
from main import STAGE_ORDER, cmd_stage


def main():
    parser = argparse.ArgumentParser(
        prog="uv run stage",
        description="Execute a single pipeline stage",
        add_help=False,
    )
    parser.add_argument("project", help="Project name")
    parser.add_argument("stage", choices=STAGE_ORDER, help="Stage to execute")
    args = parser.parse_args()
    cmd_stage(args)


if __name__ == "__main__":
    main()
