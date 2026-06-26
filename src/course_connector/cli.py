"""Command line entry point for course connector."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from course_connector.pipeline import PipelineInputs, run_pipeline


@dataclass(frozen=True)
class FileArgument:
    """Validation rules for a CLI file argument."""

    name: str
    path: Path | None
    allowed_suffixes: tuple[str, ...]
    required: bool = True


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        prog="course-connector",
        description="Run the course connector pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Validate input files and run the pipeline.",
        description="Validate course inputs and run the course connector pipeline.",
    )
    run_parser.add_argument("--course-a", required=True, type=Path, help="Course A file: .md or .yaml.")
    run_parser.add_argument("--course-b", required=True, type=Path, help="Course B file: .md or .yaml.")
    run_parser.add_argument("--mapping", required=True, type=Path, help="Mapping file: .yaml or .json.")
    run_parser.add_argument(
        "--source-pack",
        required=True,
        type=Path,
        help="Additional source pack file: .md, .csv, or .yaml.",
    )
    run_parser.add_argument("--config", type=Path, help="Optional config file: .yaml.")
    run_parser.add_argument("--output-dir", required=True, type=Path, help="Directory for output files.")
    run_parser.set_defaults(handler=_handle_run)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the course connector CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler")
    return handler(args, parser)


def _handle_run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    file_arguments = (
        FileArgument("--course-a", args.course_a, (".md", ".yaml")),
        FileArgument("--course-b", args.course_b, (".md", ".yaml")),
        FileArgument("--mapping", args.mapping, (".yaml", ".json")),
        FileArgument("--source-pack", args.source_pack, (".md", ".csv", ".yaml")),
        FileArgument("--config", args.config, (".yaml",), required=False),
    )
    errors = list(_validate_file_arguments(file_arguments))
    if errors:
        parser.exit(2, "\n".join(errors) + "\n")

    result = run_pipeline(
        PipelineInputs(
            course_a=args.course_a,
            course_b=args.course_b,
            mapping=args.mapping,
            source_pack=args.source_pack,
            config=args.config,
        ),
        output_dir=args.output_dir,
    )
    print("Pipeline completed.")
    print(f"Markdown report: {result.report_md}")
    print(f"JSON summary: {result.summary_json}")
    return 0


def _validate_file_arguments(arguments: Iterable[FileArgument]) -> Iterable[str]:
    for argument in arguments:
        if argument.path is None:
            if argument.required:
                yield f"Error: {argument.name} is required."
            continue

        suffix = argument.path.suffix.lower()
        if suffix not in argument.allowed_suffixes:
            allowed = ", ".join(argument.allowed_suffixes)
            yield (
                f"Error: {argument.name} has unsupported file extension: "
                f"{argument.path}. Allowed extensions: {allowed}."
            )
            continue

        if not argument.path.is_file():
            yield f"Error: {argument.name} file not found: {argument.path}"


if __name__ == "__main__":
    sys.exit(main())
