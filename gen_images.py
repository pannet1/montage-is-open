#!/usr/bin/env python3
"""Generate scene images from scene_plan using local SDXL model.

Usage:
    uv run python gen_images.py <project>
"""
import argparse
import sys
from main import cmd_gen_images, check_submodule, banner


def main():
    check_submodule()
    banner()
    parser = argparse.ArgumentParser(
        description="Generate scene images from scene_plan using local SDXL model",
        add_help=False,
    )
    parser.add_argument("project", help="Project name")
    args = parser.parse_args()
    cmd_gen_images(args)


if __name__ == "__main__":
    main()
