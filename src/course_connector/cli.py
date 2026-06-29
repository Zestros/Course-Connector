"""Command line entry point for Course Connector."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from course_connector.input_layer import InputLayerError, load_input_payload
from course_connector.pipeline import run_pipeline
from course_connector.preprocessing_layer.config import PreprocessingConfigurationError


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        prog="course-connector",
        description="Run the Course Connector pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Load MVP input files and run the pipeline.",
        description="Load course inputs and run the Course Connector pipeline.",
    )
    run_parser.add_argument("--course-a", required=True, type=Path, help="Course A file: .md, .yaml, or .yml.")
    run_parser.add_argument("--course-b", required=True, type=Path, help="Course B file: .md, .yaml, or .yml.")
    run_parser.add_argument(
        "--skill-dictionary",
        required=True,
        type=Path,
        help="Skill dictionary file: .yaml, .yml, or .json.",
    )
    run_parser.add_argument(
        "--assessments",
        required=True,
        type=Path,
        help="Assessment materials file: .md, .yaml, .yml, or .csv.",
    )
    run_parser.add_argument("--config", type=Path, help="Optional config file: .yaml or .yml.")
    run_parser.add_argument("--output-dir", required=True, type=Path, help="Directory for output files.")
    run_parser.set_defaults(handler=_handle_run)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Course Connector CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler")
    return handler(args, parser)


def _handle_run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        input_payload = load_input_payload(
            course_a=args.course_a,
            course_b=args.course_b,
            skill_dictionary=args.skill_dictionary,
            assessments=args.assessments,
            config=args.config,
        )
    except InputLayerError as exc:
        parser.exit(2, f"Error: {exc}\n")

    try:
        result = run_pipeline(input_payload, output_dir=args.output_dir)
    except PreprocessingConfigurationError as exc:
        parser.exit(2, f"Error: {exc}\n")
    print("Pipeline completed.")
    print(f"Markdown report: {result.report_md}")
    print(f"JSON result: {result.result_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
