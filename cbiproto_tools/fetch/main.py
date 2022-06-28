#!/usr/bin/env python


from __future__ import annotations

import argparse
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from git import Blob
    from git.repo import Repo
    from git.util import stream_copy
except ImportError as err:
    print(
        "\033[31m"
        f"Unable to import `{err.name}`!"
        "Please ensure that you've installed cbiproto with the [tools] extra"
        "so that compiler dependencies are included."
        "\033[0m"
    )
    raise SystemExit(1)


from .requirements import Requirements


@dataclass
class Args:
    requirements: Path  # Path to proto_requirements.txt
    output: Path  # Directory to store the proto files
    git_url: str  # Git url of the protos


def _only_proto_files(i: Any, _: int) -> bool:
    return isinstance(i, Blob) and str(i.path).endswith(".proto")


def run(
    output: Path,  # Directory to store the proto files
    requirements: Path = Path("proto_requirements.txt"),  # Path to proto_requirements.txt
    git_url: str = "git@gitlab.cbinsights.com:engineering/protos.git",  # Git url of the protos
) -> None:
    """Entrypoint when running from tools or scripts"""

    with tempfile.TemporaryDirectory() as local_path:
        req = Requirements.from_file(requirements)
        current_txt = output / "current.txt"
        current = Requirements.from_file(current_txt, ignore_errors=True)

        repo = Repo.clone_from(git_url, local_path)
        for entry in req.entries:
            if not current.has(entry.name, entry.value):
                tree = repo.tag(entry.as_tag()).commit.tree
                for blob in tree.traverse(predicate=_only_proto_files):
                    assert isinstance(blob, Blob)
                    dest = output / Path(blob.path)
                    dest.resolve().parent.mkdir(parents=True, exist_ok=True)
                    with dest.open("wb") as proto:
                        stream_copy(blob.repo.odb.stream(blob.binsha).stream, proto)
            current.add(entry.name, entry.value, entry.section)

        current.write_file(current_txt, include_root_header=False)


def main() -> None:
    """Entrypoint when running from command line."""

    parser = argparse.ArgumentParser(prog="cbiproto-fetch")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--git-url", default="git@gitlab.cbinsights.com:engineering/protos.git")
    parser.add_argument("requirements", nargs="?", type=Path, default="proto_requirements.txt")
    result = parser.parse_args()
    return run(**result.__dict__)
