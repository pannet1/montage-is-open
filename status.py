#!/usr/bin/env python3
"""Show pipeline progress for a project."""
import argparse
from main import cmd_status


def main():
    parser = argparse.ArgumentParser(
        prog="uv run status",
        description="Show pipeline progress for a project",
        add_help=False,
    )
    parser.add_argument("name", nargs="?", default=None, help="Project name (default: latest)")
    args = parser.parse_args()
    cmd_status(args)


if __name__ == "__main__":
    main()
