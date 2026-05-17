#!/usr/bin/env python3
"""Publish the stable .wcp packages in the component folders to GitHub Releases.

This is a one-off bootstrap helper: it takes whatever .wcp files are sitting in
DXVK/, VKD3D/, Box64/, WOWBox64/, FEXCore/, Proton/ and Wine/ and uploads them to
the matching `Stable-*` release tag on this repository. It is safe to re-run —
existing releases are reused and assets are overwritten with --clobber.

Requirements:
  * the GitHub CLI `gh`, authenticated (`gh auth login`) with write access, or
    a GH_TOKEN / GITHUB_TOKEN environment variable.

Usage:
  python3 tools/seed-releases.py [--repo OWNER/NAME] [--dry-run]

After it finishes, the `Update contents.json` workflow regenerates contents.json
from the releases automatically (or run generate_contents.py locally).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

REPO_DEFAULT = "WinNative-Emu/Components"

# Component folder -> the same stable-tag rules used by generate_contents.py.
FOLDERS = ("DXVK", "VKD3D", "Box64", "WOWBox64", "FEXCore", "Proton", "Wine")

TAG_TITLES = {
    "Stable-DXVK": "DXVK — Stable",
    "Stable-DXVK-arm64ec": "DXVK ARM64EC — Stable",
    "Stable-DXVK-Sarek": "DXVK-Sarek — Stable",
    "Stable-VKD3D": "VKD3D — Stable",
    "Stable-VKD3D-arm64ec": "VKD3D ARM64EC — Stable",
    "Stable-Box64": "Box64 — Stable",
    "Stable-WOWBox64": "WOWBox64 — Stable",
    "Stable-FEXCore": "FEXCore — Stable",
    "Stable-Proton": "Proton — Stable",
    "Stable-Wine": "Wine — Stable",
}


def stable_tag(folder: str, filename: str) -> str:
    low = filename.lower()
    if folder == "DXVK":
        if "sarek" in low:
            return "Stable-DXVK-Sarek"
        if "arm64ec" in low:
            return "Stable-DXVK-arm64ec"
        return "Stable-DXVK"
    if folder == "VKD3D":
        if "arm64ec" in low:
            return "Stable-VKD3D-arm64ec"
        return "Stable-VKD3D"
    return "Stable-" + folder


def run(cmd: list[str], dry_run: bool) -> int:
    print("  $", " ".join(cmd))
    if dry_run:
        return 0
    return subprocess.run(cmd).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", REPO_DEFAULT))
    parser.add_argument("--root", default=os.path.join(os.path.dirname(__file__), ".."))
    parser.add_argument("--dry-run", action="store_true", help="Print actions without running them.")
    args = parser.parse_args()

    if shutil.which("gh") is None:
        print("error: the GitHub CLI 'gh' is required. Install it and run 'gh auth login'.", file=sys.stderr)
        return 1

    root = os.path.abspath(args.root)

    # tag -> list of file paths
    buckets: dict[str, list[str]] = {}
    for folder in FOLDERS:
        folder_path = os.path.join(root, folder)
        if not os.path.isdir(folder_path):
            continue
        for filename in sorted(os.listdir(folder_path)):
            if filename.endswith((".wcp", ".wcp.xz")):
                tag = stable_tag(folder, filename)
                buckets.setdefault(tag, []).append(os.path.join(folder_path, filename))

    if not buckets:
        print("Nothing to upload — no .wcp files found in the component folders.")
        return 0

    total = sum(len(v) for v in buckets.values())
    print(f"Publishing {total} package(s) across {len(buckets)} release(s) to {args.repo}\n")

    for tag in sorted(buckets):
        files = buckets[tag]
        title = TAG_TITLES.get(tag, tag)
        print(f"[{tag}] {len(files)} file(s)")

        exists = subprocess.run(
            ["gh", "release", "view", tag, "--repo", args.repo],
            capture_output=True,
        ).returncode == 0

        if not exists:
            run(
                [
                    "gh", "release", "create", tag,
                    "--repo", args.repo,
                    "--title", title,
                    "--notes", f"Curated stable {title.split(' — ')[0]} packages for the WinNative emulator.",
                ],
                args.dry_run,
            )

        rc = run(
            ["gh", "release", "upload", tag, "--repo", args.repo, "--clobber", *files],
            args.dry_run,
        )
        if rc != 0:
            print(f"  ! upload failed for {tag}", file=sys.stderr)
        print()

    print("Done. The 'Update contents.json' workflow will refresh contents.json,")
    print("or run: python3 tools/generate_contents.py --source releases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
