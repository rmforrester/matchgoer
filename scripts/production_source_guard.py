"""Refuse production code delivery outside freshly verified canonical master."""
import argparse
from pathlib import Path
import re
import subprocess


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                            text=True, timeout=60)
    if result.returncode:
        raise ValueError("GIT_SOURCE_CHECK_FAILED")
    return result.stdout.strip()


def require_canonical(repo, candidate):
    if not re.fullmatch(r"[0-9a-f]{40}", candidate):
        raise ValueError("EXACT_COMMIT_REQUIRED")
    commit = git(repo, "rev-parse", "--verify", candidate + "^{commit}")
    canonical = git(repo, "rev-parse", "refs/remotes/origin/master")
    remote = git(repo, "ls-remote", "--exit-code", "origin", "refs/heads/master")
    if not remote or remote.split()[0] != canonical:
        raise ValueError("CANONICAL_REF_STALE_FETCH_ORIGIN_FIRST")
    result = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                             commit, canonical], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError("REFUSE_NONCANONICAL_CODE_DEPLOYMENT")
    return commit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print("PRODUCTION SOURCE CONTINUITY: PASS " + require_canonical(args.repo, args.commit))
