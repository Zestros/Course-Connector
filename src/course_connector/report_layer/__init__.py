"""Report generation helpers for Course Connector."""

from course_connector.report_layer.json_report import build_json_result, write_json_result
from course_connector.report_layer.markdown_report import render_markdown_report

__all__ = [
    "build_json_result",
    "render_markdown_report",
    "write_json_result",
]
