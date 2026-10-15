#!/usr/bin/env python3
"""Update the Scoop manifest from existing official Pebrel release assets."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


REPOSITORY = "Kuddev/pebrel"
RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MANIFEST = Path(__file__).resolve().parents[1] / "bucket" / "pebrel.json"


def open_url(url, *, api=False):
    """Retry temporary network errors; send the token only to the GitHub API."""
    headers = {"User-Agent": "Tao-Boy-scoop-bucket-updater"}
    if api:
        if urlsplit(url).netloc != "api.github.com":
            raise ValueError("API requests must use api.github.com")
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    for attempt in range(3):
        try:
            return urlopen(Request(url, headers=headers), timeout=60)
        except HTTPError as error:
            if attempt == 2 or (error.code != 429 and error.code < 500):
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("Network retry limit reached")


def version_tuple(value):
    # Only stable numeric release tags are accepted. Never execute tag text.
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+){1,3}", value):
        raise ValueError(f"Unsupported stable version: {value!r}")
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * (4 - len(parts))


def asset_sha256(asset):
    # GitHub calculates this digest for uploaded release assets.
    digest = asset.get("digest")
    if isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        return digest.split(":", 1)[1].lower()
    # Older assets may not have a digest. Stream the existing ZIP for hashing;
    # never extract, install, execute, or compile the application.
    checksum = hashlib.sha256()
    size = 0
    with open_url(asset["browser_download_url"]) as response:
        while chunk := response.read(1024 * 1024):
            checksum.update(chunk)
            size += len(chunk)
    if size != asset["size"]:
        raise ValueError(f"Incomplete download: {asset['name']}")
    return checksum.hexdigest()


def updated_manifest(manifest, release):
    """Prepare both architectures before returning any change to the caller."""
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("Only published stable releases are supported")
    tag = release["tag_name"]
    version = tag.removeprefix("v")
    if version_tuple(version) < version_tuple(manifest["version"]):
        print(f"Keeping {manifest['version']}: latest release {version} is older.")
        return manifest
    result = copy.deepcopy(manifest)
    result["version"] = version
    assets = release["assets"]
    for architecture in ("64bit", "arm64"):
        template = manifest["autoupdate"]["architecture"][architecture]["url"]
        url = template.replace("$version", version)
        prefix = f"https://github.com/{REPOSITORY}/releases/download/{tag}/"
        if not url.startswith(prefix):
            raise ValueError(f"Unexpected release URL for {architecture}: {url}")
        matches = [asset for asset in assets if asset.get("browser_download_url") == url]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one uploaded {architecture} ZIP: {url}")
        asset = matches[0]
        if asset.get("state") != "uploaded" or asset.get("size", 0) <= 0:
            raise ValueError(f"Release asset is not ready: {asset.get('name')}")
        result["architecture"][architecture]["url"] = url
        result["architecture"][architecture]["hash"] = asset_sha256(asset)
    return result


def update(path, release, *, dry_run=False):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    result = updated_manifest(manifest, release)
    if result == manifest:
        print(f"pebrel.json is up to date ({manifest['version']}).")
        return False
    if dry_run:
        print(f"Would update pebrel.json: {manifest['version']} -> {result['version']}.")
        return True
    # Replace only after both architectures are valid, preserving the old file
    # if an API request, asset lookup, or checksum download fails.
    text = json.dumps(result, ensure_ascii=False, indent=4) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"Updated pebrel.json: {manifest['version']} -> {result['version']}.")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Check without writing JSON")
    args = parser.parse_args()
    with open_url(RELEASE_API, api=True) as response:
        release = json.load(response)
    update(MANIFEST, release, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Manifest update failed: {error}", file=sys.stderr)
        sys.exit(1)
