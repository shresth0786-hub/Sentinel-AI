"""
Export the curated OpenAPI spec + a generated API reference.

Usage (from backend/):

    python export_openapi.py

Writes:
    ../docs/openapi.json   -> machine-readable spec (importable into Postman)
    ../docs/API.md         -> human-readable endpoint reference
"""

from __future__ import annotations

import json
import os

from app.main import app


def _write_json(spec: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2, ensure_ascii=False)


def _write_markdown(spec: dict, out_path: str) -> None:
    info = spec.get("info", {})
    lines = [
        f"# {info.get('title', 'API')}",
        "",
        f"**Version:** {info.get('version', '')}",
        "",
        "> Generated from the live OpenAPI schema (`python export_openapi.py`).",
        "> Interactive docs: `/docs` (Swagger UI) and `/redoc`.",
        "",
        "## Tag groups",
        "",
    ]
    for t in spec.get("tags", []):
        lines.append(f"- **{t['name']}** — {t.get('description', '')}")
    lines.append("")

    # group operations by tag
    by_tag: dict[str, list] = {}
    for route, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            tag = (op.get("tags") or ["misc"])[0]
            by_tag.setdefault(tag, []).append((method.upper(), route, op))

    for tag in [t["name"] for t in spec.get("tags", [])] + ["misc"]:
        ops = by_tag.get(tag)
        if not ops:
            continue
        lines.append(f"## {tag}")
        lines.append("")
        for method, route, op in sorted(ops, key=lambda x: (x[1], x[0])):
            summary = op.get("summary") or op.get("description") or ""
            lines.append(f"### `{method} {route}`")
            if summary:
                lines.append("")
                lines.append(summary)
            lines.append("")
            params = op.get("parameters") or []
            if params:
                lines.append("| param | in | required | description |")
                lines.append("| --- | --- | --- | --- |")
                for p in params:
                    req = "yes" if p.get("required") else "no"
                    desc = (p.get("description") or "").replace("|", "\\|").replace("\n", " ")
                    lines.append(
                        f"| `{p.get('name')}` | {p.get('in')} | {req} | {desc} |")
                lines.append("")
        lines.append("")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main() -> None:
    spec = app.openapi()
    out_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "openapi.json")
    md_path = os.path.join(out_dir, "API.md")
    _write_json(spec, json_path)
    _write_markdown(spec, md_path)
    n_paths = len(spec.get("paths", {}))
    n_ops = sum(len(v) for v in spec.get("paths", {}).values())
    print(f"wrote {json_path} ({n_paths} paths, {n_ops} operations)")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
