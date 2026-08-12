#!/usr/bin/env python3
"""Run the customer-intelligence pipeline in dependency order.

The runner deliberately delegates all analytical work to the existing scripts
and notebooks. It adds only cross-platform orchestration, stage selection, and
fail-fast behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parent
EXPECTED_PYTHON = (3, 14, 6)
DEFAULT_NOTEBOOK_TIMEOUT = 1_800
SOURCE_ARCHIVE = Path("data/raw/online+retail+ii.zip")
EXPECTED_ARCHIVE_SIZE = 45_622_418
EXPECTED_ARCHIVE_SHA256 = (
    "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
)


@dataclass(frozen=True)
class Stage:
    """One executable pipeline stage."""

    key: str
    description: str
    target: Path
    kind: str


STAGES = [
    Stage(
        "ingest",
        "Ingest the verified UCI archive",
        Path("src/data/ingest.py"),
        "script",
    ),
    Stage(
        "validate",
        "Profile and validate the raw transactions",
        Path("src/data/validate.py"),
        "script",
    ),
    Stage(
        "clean",
        "Clean transactions and build analytical inputs",
        Path("src/data/clean.py"),
        "script",
    ),
    Stage(
        "01",
        "Data understanding",
        Path("notebooks/01_data_understanding.ipynb"),
        "notebook",
    ),
    Stage(
        "02",
        "RFM segmentation",
        Path("notebooks/02_rfm_segmentation.ipynb"),
        "notebook",
    ),
    Stage(
        "03",
        "ML customer segmentation",
        Path("notebooks/03_ml_customer_segmentation.ipynb"),
        "notebook",
    ),
    Stage(
        "04",
        "Temporal churn dataset",
        Path("notebooks/04_churn_dataset.ipynb"),
        "notebook",
    ),
    Stage(
        "05",
        "Churn modeling",
        Path("notebooks/05_churn_modeling.ipynb"),
        "notebook",
    ),
    Stage(
        "06",
        "Customer lifetime value modeling",
        Path("notebooks/06_clv_modeling.ipynb"),
        "notebook",
    ),
    Stage(
        "07",
        "Retention decision engine",
        Path("notebooks/07_retention_decision_engine.ipynb"),
        "notebook",
    ),
]

STAGE_INDEX = {stage.key: index for index, stage in enumerate(STAGES)}


def positive_integer(value: str) -> int:
    """Parse a strictly positive command-line integer."""

    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface."""

    parser = argparse.ArgumentParser(
        description=(
            "Run ingestion, validation, cleaning, and notebooks 01-07 "
            "in dependency order."
        )
    )
    parser.add_argument(
        "--start-at",
        choices=STAGE_INDEX,
        default=STAGES[0].key,
        help="First stage to run (default: ingest).",
    )
    parser.add_argument(
        "--stop-after",
        choices=STAGE_INDEX,
        default=STAGES[-1].key,
        help="Last stage to run, inclusive (default: 07).",
    )
    parser.add_argument(
        "--notebook-timeout",
        type=positive_integer,
        default=DEFAULT_NOTEBOOK_TIMEOUT,
        metavar="SECONDS",
        help=(
            "Per-cell execution timeout passed to nbconvert "
            f"(default: {DEFAULT_NOTEBOOK_TIMEOUT})."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selected stages and commands without executing them.",
    )
    parser.add_argument(
        "--list-stages",
        action="store_true",
        help="List stage keys and descriptions, then exit.",
    )
    return parser


def command_for(stage: Stage, notebook_timeout: int) -> list[str]:
    """Build the subprocess command for one stage."""

    target = str(stage.target)
    if stage.kind == "script":
        return [sys.executable, target]

    return [
        sys.executable,
        "-m",
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        "--inplace",
        target,
        f"--ExecutePreprocessor.timeout={notebook_timeout}",
    ]


def display_command(command: list[str]) -> str:
    """Format a command for readable logging on the current platform."""

    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def selected_stages(start_at: str, stop_after: str) -> list[Stage]:
    """Return the requested inclusive stage range."""

    start_index = STAGE_INDEX[start_at]
    stop_index = STAGE_INDEX[stop_after]
    if start_index > stop_index:
        raise ValueError(
            f"--start-at {start_at!r} occurs after --stop-after {stop_after!r}."
        )
    return STAGES[start_index : stop_index + 1]


def preflight(stages: list[Stage]) -> None:
    """Check source files required to begin the selected run."""

    for stage in stages:
        target = PROJECT_ROOT / stage.target
        if not target.is_file():
            raise FileNotFoundError(f"Pipeline target does not exist: {target}")

    if stages[0].key == "ingest":
        archive = PROJECT_ROOT / SOURCE_ARCHIVE
        if not archive.is_file():
            raise FileNotFoundError(
                "Missing source archive: "
                f"{archive}\nSee README.md and DATA_PROVENANCE.md for the "
                "official UCI download and checksum."
            )

        archive_size = archive.stat().st_size
        if archive_size != EXPECTED_ARCHIVE_SIZE:
            raise ValueError(
                f"Source archive size is {archive_size:,} bytes; expected "
                f"{EXPECTED_ARCHIVE_SIZE:,} bytes. Re-download it from UCI."
            )

        with archive.open("rb") as archive_handle:
            archive_sha256 = hashlib.file_digest(
                archive_handle,
                "sha256",
            ).hexdigest()
        if archive_sha256 != EXPECTED_ARCHIVE_SHA256:
            raise ValueError(
                "Source archive SHA-256 does not match the verified UCI "
                f"archive. Found {archive_sha256}; expected "
                f"{EXPECTED_ARCHIVE_SHA256}."
            )


def main() -> int:
    """Parse arguments and execute the requested pipeline stages."""

    parser = build_parser()
    args = parser.parse_args()

    if args.list_stages:
        for stage in STAGES:
            print(f"{stage.key:>8}  {stage.description}")
        return 0

    try:
        stages = selected_stages(args.start_at, args.stop_after)
        preflight(stages)
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))

    current_python = sys.version_info[:3]
    if current_python != EXPECTED_PYTHON:
        print(
            "WARNING: verified Python is "
            f"{'.'.join(map(str, EXPECTED_PYTHON))}; running "
            f"{'.'.join(map(str, current_python))}.",
            file=sys.stderr,
        )

    environment = os.environ.copy()
    environment.setdefault("PYTHONUTF8", "1")

    print(f"Project root: {PROJECT_ROOT}")
    print(f"Python:       {sys.executable}")
    print(f"Stages:       {stages[0].key} -> {stages[-1].key}")

    pipeline_started = time.perf_counter()

    for position, stage in enumerate(stages, start=1):
        command = command_for(stage, args.notebook_timeout)
        print("\n" + "=" * 78, flush=True)
        print(
            f"[{position}/{len(stages)}] {stage.key}: {stage.description}",
            flush=True,
        )
        print(display_command(command), flush=True)

        if args.dry_run:
            continue

        stage_started = time.perf_counter()
        try:
            subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                env=environment,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            print(
                f"\nPipeline stopped: stage {stage.key!r} failed "
                f"with exit code {error.returncode}.",
                file=sys.stderr,
            )
            return error.returncode or 1

        elapsed = time.perf_counter() - stage_started
        print(f"Completed stage {stage.key} in {elapsed:,.1f} seconds.")

    total_elapsed = time.perf_counter() - pipeline_started
    if args.dry_run:
        print("\nDry run complete; no stages were executed.")
    else:
        print(
            f"\nPipeline completed successfully in {total_elapsed:,.1f} seconds."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
