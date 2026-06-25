#!/usr/bin/env python3
import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse, parse_qsl, urlunparse
from urllib.request import Request, build_opener, ProxyHandler


OPENER = build_opener(ProxyHandler({}))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export raw Moodle course API responses and downloadable module contents."
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", required=True)
    parser.add_argument("--out-dir", default="data/raw-courses")
    parser.add_argument("--course", action="append", required=True, help="Course shortname. Can be repeated.")
    return parser.parse_args()


def slugify(value, fallback="item"):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9а-яё]+", "-", value, flags=re.IGNORECASE)
    value = value.strip("-")[:80]
    return value or fallback


def pad(value):
    return str(value).zfill(2)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def request_bytes(url):
    request = Request(url, headers={"User-Agent": "course-connector-exporter/1.0"})
    with OPENER.open(request, timeout=60) as response:
        return response.read(), response.headers.get("content-type", "")


def request_json(url):
    data, _content_type = request_bytes(url)
    text = data.decode("utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Expected JSON from {url}, got: {text[:200]}") from error
    if isinstance(payload, dict) and ("exception" in payload or "errorcode" in payload):
        raise RuntimeError(f"Moodle API error from {url}: {text[:500]}")
    return payload


def api_url(base_url, token, wsfunction, params):
    query = {
        "wstoken": token,
        "wsfunction": wsfunction,
        "moodlewsrestformat": "json",
        **params,
    }
    return f"{base_url.rstrip('/')}/webservice/rest/server.php?{urlencode(query)}"


def file_url_with_token(file_url, token):
    parsed = urlparse(file_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["token"] = token
    return urlunparse(parsed._replace(query=urlencode(query)))


def export_course(args, shortname):
    out_dir = Path(args.out_dir)
    course_response = request_json(
        api_url(args.base_url, args.token, "core_course_get_courses_by_field", {
            "field": "shortname",
            "value": shortname,
        })
    )

    courses = course_response.get("courses", [])
    if not courses:
        raise RuntimeError(f"Course not found by shortname: {shortname}")
    course = courses[0]

    contents_response = request_json(
        api_url(args.base_url, args.token, "core_course_get_contents", {
            "courseid": str(course["id"]),
        })
    )

    course_dir = out_dir / shortname
    if course_dir.exists():
        import shutil
        shutil.rmtree(course_dir)

    write_json(course_dir / "raw" / "course.json", course_response)
    write_json(course_dir / "raw" / "contents.json", contents_response)

    course_index = {
        "course": {
            "id": course["id"],
            "shortname": course["shortname"],
            "fullname": course["fullname"],
        },
        "raw": {
            "course": "raw/course.json",
            "contents": "raw/contents.json",
        },
        "sections": [],
    }

    for fallback_section_index, section in enumerate(contents_response):
        section_number = section.get("section", fallback_section_index)
        section_dir_name = f"{pad(section_number)}-{slugify(section.get('name'), 'section')}"
        section_dir = course_dir / "sections" / section_dir_name
        write_json(section_dir / "section.raw.json", section)

        section_index = {
            "section": section_number,
            "name": section.get("name"),
            "path": str(section_dir.relative_to(course_dir)),
            "modules": [],
        }

        for module_index, module in enumerate(section.get("modules", []), start=1):
            module_dir_name = f"{pad(module_index)}-{module.get('modname')}-{slugify(module.get('name'), 'module')}"
            module_dir = section_dir / "modules" / module_dir_name
            write_json(module_dir / "module.raw.json", module)

            module_entry = {
                "id": module.get("id"),
                "name": module.get("name"),
                "modname": module.get("modname"),
                "path": str(module_dir.relative_to(course_dir)),
                "contents": [],
            }

            for content_index, content in enumerate(module.get("contents", []), start=1):
                meta_name = f"{pad(content_index)}-{slugify(content.get('filename'), 'content')}.meta.raw.json"
                write_json(module_dir / "contents" / meta_name, content)

                file_url = content.get("fileurl")
                if file_url:
                    download_url = file_url_with_token(file_url, args.token)
                    data, content_type = request_bytes(download_url)
                    filename = f"{pad(content_index)}-{content.get('filename') or 'content'}"
                    file_path = module_dir / "contents" / filename
                    write_bytes(file_path, data)
                    module_entry["contents"].append({
                        "source_fileurl": file_url,
                        "downloaded": str(file_path.relative_to(course_dir)),
                        "content_type": content_type,
                    })

            section_index["modules"].append(module_entry)

        course_index["sections"].append(section_index)

    write_json(course_dir / "index.json", course_index)
    return course_index


def main():
    args = parse_args()
    args.base_url = args.base_url.rstrip("/")

    results = []
    for shortname in args.course:
        results.append(export_course(args, shortname))

    write_json(Path(args.out_dir) / "raw-course-tree.index.json", {
        "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "base_url": args.base_url,
        "courses": [
            {
                "id": result["course"]["id"],
                "shortname": result["course"]["shortname"],
                "fullname": result["course"]["fullname"],
                "path": result["course"]["shortname"],
            }
            for result in results
        ],
    })
    print(f"Exported {len(results)} course(s) to {args.out_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
