#!/usr/bin/env python3
"""Generate contents.json for the WinNative Components catalogue.

Two sources are supported:

  --source local      Scan the component folders in this repo (DXVK/, Wine/, ...)
                       and emit entries pointing at the release URLs the files
                       will be published under. Used to bootstrap the catalogue
                       before the GitHub releases exist.

  --source releases    Query the GitHub Releases API for this repo and build the
                       catalogue from whatever assets are actually published.
                       This is the mode the CI workflow runs every day.

Both modes produce byte-for-byte comparable output so the file stays stable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "WinNative-Emu/Components")

# Component folder -> content type understood by the WinNative app.
TYPE_BY_FOLDER = {
    "DXVK": "DXVK",
    "VKD3D": "VKD3D",
    "Box64": "Box64",
    "WOWBox64": "WOWBox64",
    "FEXCore": "FEXCore",
    "Proton": "Proton",
    "Wine": "Wine",
}

# Stable release tag -> content type.
STABLE_TAGS = {
    "Stable-DXVK": "DXVK",
    "Stable-DXVK-arm64ec": "DXVK",
    "Stable-DXVK-Sarek": "DXVK",
    "Stable-VKD3D": "VKD3D",
    "Stable-VKD3D-arm64ec": "VKD3D",
    "Stable-Box64": "Box64",
    "Stable-WOWBox64": "WOWBox64",
    "Stable-FEXCore": "FEXCore",
    "Stable-Proton": "Proton",
    "Stable-Wine": "Wine",
}

# Nightly release tag prefix -> content type. The CI build workflows publish
# nightly assets under "<prefix><commit>" tags; they are discovered dynamically.
NIGHTLY_PREFIXES = {
    "dxvk-nightly-": "DXVK",
    "dxvk-arm64ec-nightly-": "DXVK",
    "vkd3d-nightly-": "VKD3D",
    "vkd3d-arm64ec-nightly-": "VKD3D",
    "fex-nightly-": "FEXCore",
    "box64-nightly-": "Box64",
    "wowbox64-nightly-": "WOWBox64",
}

WCP_SUFFIXES = (".wcp", ".wcp.xz")


def ver_name(filename: str) -> str:
    """Display name = asset filename without its .wcp / .wcp.xz suffix."""
    for suffix in WCP_SUFFIXES:
        if filename.endswith(suffix):
            return filename[: -len(suffix)]
    return filename


def stable_tag(folder: str, filename: str) -> str:
    """Pick the stable release tag a folder/file pair belongs to."""
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
    return "Stable-" + folder  # Stable-Box64 / Stable-WOWBox64 / Stable-FEXCore / Stable-Proton / Stable-Wine


def entry(ctype: str, filename: str, tag: str) -> dict:
    return {
        "type": ctype,
        "verName": ver_name(filename),
        "verCode": 0,
        "remoteUrl": f"https://github.com/{REPO}/releases/download/{tag}/{filename}",
    }


def sort_key(item: dict):
    """Group by type, then newest version first, then name."""
    numbers = [-int(n) for n in re.findall(r"\d+", item["verName"])]
    return (item["type"], numbers, item["verName"])


def collect_local(root: str) -> list[dict]:
    packs: list[dict] = []
    for folder, ctype in TYPE_BY_FOLDER.items():
        folder_path = os.path.join(root, folder)
        if not os.path.isdir(folder_path):
            continue
        for filename in sorted(os.listdir(folder_path)):
            if not filename.endswith(WCP_SUFFIXES):
                continue
            packs.append(entry(ctype, filename, stable_tag(folder, filename)))
    return packs


def gh_api(path: str) -> object:
    url = f"https://api.github.com/repos/{REPO}{path}"
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def collect_releases() -> list[dict]:
    packs: list[dict] = []

    # Discover every release once so nightly tags are picked up automatically.
    releases: list[dict] = []
    page = 1
    while True:
        chunk = gh_api(f"/releases?per_page=100&page={page}")
        if not isinstance(chunk, list) or not chunk:
            break
        releases.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1

    # Newest first, so the first release matching a nightly prefix is the latest.
    releases.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    # Only the most recent nightly per variant is listed; older nightly releases
    # may still exist for manual download but are kept out of the catalogue.
    nightly_seen: set[str] = set()
    for release in releases:
        tag = release.get("tag_name", "")
        ctype = STABLE_TAGS.get(tag)
        if ctype is None:
            prefix = next((p for p in NIGHTLY_PREFIXES if tag.startswith(p)), None)
            if prefix is None or prefix in nightly_seen:
                continue
            nightly_seen.add(prefix)
            ctype = NIGHTLY_PREFIXES[prefix]
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(WCP_SUFFIXES):
                packs.append(entry(ctype, name, tag))
    return packs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("local", "releases"), default="releases")
    parser.add_argument(
        "--root",
        default=os.path.join(os.path.dirname(__file__), ".."),
        help="Repository root (local mode only).",
    )
    parser.add_argument("--out", default="contents.json")
    args = parser.parse_args()

    if args.source == "local":
        packs = collect_local(os.path.abspath(args.root))
    else:
        packs = collect_releases()

    packs.sort(key=sort_key)

    out_path = os.path.join(os.path.abspath(args.root), args.out) if args.source == "local" else args.out
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(packs, handle, indent=2)
        handle.write("\n")

    print(f"Wrote {len(packs)} entries to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
