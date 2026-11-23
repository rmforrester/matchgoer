"""Materialize a service's recorded production source from a canonical Git commit.

This only stages files for the existing CLI/Docker delivery process. It never
uploads, deploys, reads secrets, or executes application entrypoints.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from production_source_guard import require_canonical


def blob(repo, commit, path):
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("UNSAFE_SOURCE_PATH")
    return subprocess.check_output(["git", "-C", str(repo), "show", commit + ":" + path])


def verify_files(root, service):
    profile = json.loads((root / "ops/production_sources.json").read_text())["services"][service]
    for target, item in profile["files"].items():
        data = (root / item["source"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("SERVICE_SOURCE_DRIFT: " + target)
    return len(profile["files"])


def stage(repo, commit, service, destination):
    require_canonical(repo, commit)
    if destination.exists():
        raise ValueError("DESTINATION_MUST_NOT_EXIST")
    profile = json.loads(blob(repo, commit, "ops/production_sources.json"))["services"][service]
    contents = {}
    for target, item in profile["files"].items():
        if PurePosixPath(target).is_absolute() or ".." in PurePosixPath(target).parts:
            raise ValueError("UNSAFE_TARGET_PATH")
        data = blob(repo, commit, item["source"])
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("SEALED_SERVICE_SOURCE_DRIFT")
        contents[target] = data
    destination.mkdir(parents=True)
    for target, data in contents.items():
        path = destination / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return len(contents)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service")
    parser.add_argument("commit")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    print("Staged", stage(repo, args.commit, args.service, args.destination), "verified source files")
