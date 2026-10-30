"""Generic, source-located parsing for research workspace materials.

Parsing does not call the platform LLM, run uploaded code, or write databases.
The process boundary in parser_worker keeps layout/OCR models out of the API.
"""

from __future__ import annotations

import ast
import base64
import csv
import io
import json
import logging
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

log = logging.getLogger(__name__)
ROOT = Path(__file__).absolute().parents[3]
TEXT_LIMIT = 16 * 1024 * 1024
CODE_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".java",
    ".rs",
    ".go",
    ".sh",
    ".ps1",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".ipynb",
}
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {
    "w": W,
    "m": M,
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _block(kind, text, heading="", page=None, bbox=None, metadata=None):
    return {
        "kind": kind,
        "heading": str(heading or ""),
        "text": str(text or ""),
        "page": page,
        "bbox": bbox,
        "metadata": metadata or {},
    }


def _finish(title, blocks, parser, warnings=None, quality=None):
    warnings = list(dict.fromkeys(warnings or []))
    for i, block in enumerate(blocks):
        block["ordinal"] = i
    quality = {
        **(quality or {}),
        "block_count": len(blocks),
        "text_characters": sum(len(b["text"]) for b in blocks),
        "formula_count": sum(b["kind"] == "formula" for b in blocks),
        "table_count": sum(b["kind"] == "table" for b in blocks),
        "figure_count": sum(b["kind"] == "figure" for b in blocks),
    }
    if not quality["text_characters"]:
        warnings.append("没有提取到可供知识抽取的文字，请检查原文件或 OCR 配置。")
        quality["status"] = "partial"
    return {
        "title": title.strip() or "未命名资料",
        "blocks": blocks,
        "parser": parser,
        "warnings": warnings,
        "quality": quality,
    }


def _decode(path):
    raw = path.read_bytes()
    if len(raw) > TEXT_LIMIT:
        raise ValueError("文本资料超过 16 MiB，请按文件拆分后上传。")
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            text = raw.decode(encoding)
            if "\x00" not in text:
                return text
        except UnicodeError:
            continue
    raise ValueError("无法识别文本编码，请保存为 UTF-8 后重试。")


def _title_from_filename(path):
    return (
        path.stem
        if not re.fullmatch(r"(?:upload-)?[0-9a-f]{20,}", path.stem)
        else "未命名资料"
    )


def _native_code(path, text=None):
    text = _decode(path) if text is None else text
    lines = text.splitlines()
    warnings, blocks = [], []
    language = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
    }.get(path.suffix.lower(), path.suffix.lstrip("."))
    if path.suffix.lower() in {".py", ".pyi"}:
        try:
            tree = ast.parse(text)
            parents = {}
            for parent in ast.walk(tree):
                for child in ast.iter_child_nodes(parent):
                    parents[child] = parent
            symbols = [
                n
                for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            ]
            symbols.sort(
                key=lambda n: (n.lineno, -(getattr(n, "end_lineno", n.lineno)))
            )
            for node in symbols:
                lineage, p = [node.name], parents.get(node)
                while p:
                    if isinstance(
                        p, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        lineage.insert(0, p.name)
                    p = parents.get(p)
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                end = getattr(node, "end_lineno", node.lineno)
                blocks.append(
                    _block(
                        "code",
                        "\n".join(lines[start - 1 : end]),
                        ".".join(lineage),
                        metadata={
                            "start_line": start,
                            "end_line": end,
                            "symbol": ".".join(lineage),
                            "symbol_kind": "class"
                            if isinstance(node, ast.ClassDef)
                            else "function",
                            "language": language,
                            "docstring": ast.get_docstring(node) or "",
                        },
                    )
                )
            # Preserve imports, constants and entry-point code as well as symbols.
            for start in range(0, len(lines), 100):
                blocks.append(
                    _block(
                        "code",
                        "\n".join(lines[start : start + 100]),
                        path.name,
                        metadata={
                            "start_line": start + 1,
                            "end_line": min(start + 100, len(lines)),
                            "language": language,
                            "context_block": True,
                        },
                    )
                )
        except SyntaxError as exc:
            warnings.append(
                f"Python 语法解析失败（第 {exc.lineno} 行），保留逐行原文。"
            )
    if not blocks:
        for start in range(0, len(lines), 100):
            blocks.append(
                _block(
                    "code",
                    "\n".join(lines[start : start + 100]),
                    path.name,
                    metadata={
                        "start_line": start + 1,
                        "end_line": min(start + 100, len(lines)),
                        "language": language,
                    },
                )
            )
    return _finish(
        _title_from_filename(path),
        blocks,
        "python-ast" if language == "python" and not warnings else "source-text",
        warnings,
        {"status": "partial" if warnings else "complete", "line_count": len(lines)},
    )


def _native_repository(path):
    manifest = json.loads(_decode(path))
    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("files"), list)
        or not manifest.get("repository")
    ):
        raise ValueError("代码仓库清单缺少 repository 或 files。")
    blocks, warnings = [], []
    for entry in manifest["files"]:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("text"), str)
        ):
            warnings.append("已跳过格式无效的仓库文件条目。")
            continue
        virtual = Path(entry["path"])
        if len(entry["text"].encode("utf-8")) > TEXT_LIMIT:
            warnings.append(f"{virtual.name} 超过单文件处理范围。")
            continue
        parsed = _native_code(virtual, entry["text"])
        for block in parsed["blocks"]:
            block["metadata"].update(
                path=entry["path"],
                commit=manifest.get("commit"),
                url=entry.get("url"),
                repository=manifest["repository"],
                hash=entry.get("hash"),
            )
            blocks.append(block)
        warnings.extend(parsed["warnings"])
    return _finish(
        str(manifest.get("title") or manifest["repository"]),
        blocks,
        "repository-ast",
        warnings,
        {
            "status": "partial" if warnings else "complete",
            "commit": manifest.get("commit"),
            "file_count": len(manifest["files"]),
        },
    )


def _native_text(path):
    text = _decode(path)
    blocks, heading, title = [], "", _title_from_filename(path)
    lines = text.splitlines()
    paragraph, paragraph_start = [], 1
    warnings = []

    def flush(end_line):
        value = "\n".join(paragraph).strip()
        if value:
            for offset in range(0, len(value), 8000):
                blocks.append(
                    _block(
                        "text",
                        value[offset : offset + 8000],
                        heading,
                        metadata={"start_line": paragraph_start, "end_line": end_line},
                    )
                )
        paragraph.clear()

    index = 0
    while index < len(lines):
        value = lines[index].strip()
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", value)
        if match:
            flush(index)
            heading = match[2]
            if not blocks and len(match[1]) == 1:
                title = heading
            blocks.append(
                _block(
                    "heading",
                    heading,
                    heading,
                    metadata={
                        "level": len(match[1]),
                        "start_line": index + 1,
                        "end_line": index + 1,
                    },
                )
            )
        elif value.startswith("```") or value.startswith("~~~"):
            flush(index)
            fence = value[:3]
            language = value[3:].strip()
            start = index + 1
            code = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(fence):
                code.append(lines[index])
                index += 1
            if index == len(lines):
                warnings.append("一个代码块缺少闭合标记，已保留其原文。")
            blocks.append(
                _block(
                    "code",
                    "\n".join(code),
                    heading,
                    metadata={
                        "language": language,
                        "start_line": start,
                        "end_line": min(index + 1, len(lines)),
                    },
                )
            )
        elif value.startswith("$$"):
            flush(index)
            start = index + 1
            formula = value[2:]
            if formula.endswith("$$"):
                formula = formula[:-2]
            else:
                pieces = [formula]
                index += 1
                while index < len(lines) and "$$" not in lines[index]:
                    pieces.append(lines[index])
                    index += 1
                if index < len(lines):
                    pieces.append(lines[index].split("$$", 1)[0])
                else:
                    warnings.append("一个公式块缺少闭合标记，已保留其原文。")
                formula = "\n".join(pieces)
            blocks.append(
                _block(
                    "formula",
                    formula.strip(),
                    heading,
                    metadata={
                        "latex": formula.strip(),
                        "original_text": formula.strip(),
                        "recognition": "source_latex",
                        "start_line": start,
                        "end_line": min(index + 1, len(lines)),
                    },
                )
            )
        elif not value:
            flush(index)
        else:
            if not paragraph:
                paragraph_start = index + 1
            paragraph.append(lines[index])
        index += 1
    flush(len(lines))
    return _finish(
        title,
        blocks,
        "structured-text",
        warnings,
        quality={"status": "partial" if warnings else "complete"},
    )


def _native_json(path):
    value = json.loads(_decode(path))
    blocks = []
    records = (
        list(enumerate(value))
        if isinstance(value, list)
        else list(value.items())
        if isinstance(value, dict)
        else [("value", value)]
    )
    for key, item in records:
        rendered = json.dumps(item, ensure_ascii=False, indent=2)
        for offset in range(0, len(rendered), 8000):
            blocks.append(
                _block(
                    "table" if isinstance(item, list) else "text",
                    rendered[offset : offset + 8000],
                    str(key),
                    metadata={
                        "json_path": f"$[{key}]"
                        if isinstance(value, list)
                        else f"$.{key}",
                        "offset": offset,
                    },
                )
            )
    return _finish(
        _title_from_filename(path), blocks, "json", quality={"status": "complete"}
    )


def _native_html(path):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_decode(path), "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    title_tag = soup.find("h1") or soup.find("title")
    title = (
        title_tag.get_text(" ", strip=True) if title_tag else _title_from_filename(path)
    )
    blocks, heading = [], ""
    tags = [
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "li",
        "pre",
        "table",
        "math",
        "figure",
    ]
    for tag in (soup.body or soup).find_all(tags):
        if tag.find_parent(["table", "pre", "math", "figure"]):
            continue
        if tag.name == "p" and tag.find_parent("li"):
            continue
        text = tag.get_text(" ", strip=True)
        metadata = {
            "anchor": tag.get("id"),
            "urls": [a.get("href") for a in tag.find_all("a", href=True)],
        }
        kind = "text"
        if tag.name.startswith("h") and tag.name[1:].isdigit():
            kind, heading = "heading", text
            metadata["level"] = int(tag.name[1:])
        elif tag.name == "table":
            rows = [
                [
                    cell.get_text(" ", strip=True)
                    for cell in row.find_all(["td", "th"], recursive=False)
                ]
                for row in tag.find_all("tr")
            ]
            metadata["cells"] = rows
            text = "\n".join("\t".join(row) for row in rows)
            kind = "table"
        elif tag.name == "pre":
            kind = "code"
            text = tag.get_text("\n", strip=False)
        elif tag.name == "math":
            kind = "formula"
            text = tag.get("alttext") or text
            metadata.update(latex=text, original_text=text, recognition="source_math")
        elif tag.name == "figure":
            kind = "figure"
            image, caption = tag.find("img"), tag.find("figcaption")
            text = caption.get_text(" ", strip=True) if caption else ""
            if image and image.get("src"):
                metadata["image_url"] = image.get("src")
        if text or kind == "figure":
            blocks.append(_block(kind, text, heading, metadata=metadata))
    return _finish(
        title,
        blocks,
        "html",
        quality={"status": "complete", "coordinates": "html_anchors"},
    )


def _table_block(rows, heading, metadata):
    # The text is a faithful, compact representation; numeric meaning is not inferred.
    cells = [[_cell(v) for v in row] for row in rows]
    return _block(
        "table",
        "\n".join("\t".join(row) for row in cells),
        heading,
        metadata={**metadata, "cells": cells},
    )


def _cell(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _native_csv(path):
    text = _decode(path)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if any(len(row) > 1000 for row in rows) or len(rows) > 100000:
        raise ValueError("表格超出单份资料的处理范围，请拆分后上传。")
    blocks = [
        _table_block(
            rows[start : start + 200],
            path.name,
            {
                "sheet": path.stem,
                "start_row": start + 1,
                "end_row": min(start + 200, len(rows)),
                "cell_range": f"A{start + 1}:{_column(max((len(r) for r in rows[start : start + 200]), default=1))}{min(start + 200, len(rows))}",
            },
        )
        for start in range(0, len(rows), 200)
    ]
    return _finish(
        _title_from_filename(path),
        blocks,
        "csv",
        quality={"status": "complete", "row_count": len(rows)},
    )


def _column(number):
    label = ""
    while number:
        number, digit = divmod(number - 1, 26)
        label = chr(65 + digit) + label
    return label or "A"


def _native_xlsx(path):
    from openpyxl import load_workbook

    book = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    blocks, warnings = [], []
    try:
        for sheet in book:
            if sheet.max_row > 100000 or sheet.max_column > 1000:
                raise ValueError(f"工作表 {sheet.title} 过大，请拆分后上传。")
            rows = []
            start = 1
            for row_number, row in enumerate(sheet.iter_rows(values_only=True), 1):
                rows.append(list(row))
                if len(rows) == 200:
                    blocks.append(
                        _table_block(
                            rows,
                            sheet.title,
                            {
                                "sheet": sheet.title,
                                "start_row": start,
                                "end_row": row_number,
                                "cell_range": f"A{start}:{_column(sheet.max_column)}{row_number}",
                                "formula_values": "source_formula_not_evaluated",
                            },
                        )
                    )
                    rows, start = [], row_number + 1
            if rows:
                blocks.append(
                    _table_block(
                        rows,
                        sheet.title,
                        {
                            "sheet": sheet.title,
                            "start_row": start,
                            "end_row": start + len(rows) - 1,
                            "cell_range": f"A{start}:{_column(sheet.max_column)}{start + len(rows) - 1}",
                            "formula_values": "source_formula_not_evaluated",
                        },
                    )
                )
    finally:
        book.close()
    return _finish(
        _title_from_filename(path), blocks, "openpyxl", warnings, {"status": "complete"}
    )


def _math_text(node):
    """Preserve common OMML constructions as LaTeX rather than flattening fractions."""
    if node is None:
        return ""
    tag = node.tag.split("}")[-1]
    children = list(node)
    if tag == "t":
        symbols = {
            "ℝ": r"\mathbb{R}",
            "∈": r"\in ",
            "σ": r"\sigma ",
            "δ": r"\delta ",
            "μ": r"\mu ",
            "∂": r"\partial ",
            "θ": r"\theta ",
            "π": r"\pi ",
            "α": r"\alpha ",
            "β": r"\beta ",
            "γ": r"\gamma ",
            "ε": r"\epsilon ",
            "−": "-",
            "×": r"\times ",
            "≤": r"\leq ",
            "≥": r"\geq ",
            "∞": r"\infty ",
            "→": r"\to ",
        }
        # Word stores deliberate equation separation as space-only runs. LaTeX
        # ignores ordinary spaces, so preserve those gaps explicitly.
        original = re.sub(r"[ \t]{2,}", lambda match: r"\qquad ", node.text or "")
        value = "".join(symbols.get(char, char) for char in original)
        return re.sub(
            r"(?<![\\a-zA-Z])(tanh|sigmoid|sin|cos|exp|log)(?![a-zA-Z])",
            lambda match: r"\operatorname{sigmoid}"
            if match[1] == "sigmoid"
            else "\\" + match[1],
            value,
        )
    if tag.endswith("Pr"):
        return ""

    def child(name):
        return _math_text(node.find(f"{{{M}}}{name}"))

    if tag == "f":
        return r"\frac{" + child("num") + "}{" + child("den") + "}"
    if tag == "sSup":
        return "{" + child("e") + "}^{" + child("sup") + "}"
    if tag == "sSub":
        return "{" + child("e") + "}_{" + child("sub") + "}"
    if tag == "sSubSup":
        return "{" + child("e") + "}_{" + child("sub") + "}^{" + child("sup") + "}"
    if tag == "rad":
        degree = child("deg")
        return (
            r"\sqrt" + ("[" + degree + "]" if degree else "") + "{" + child("e") + "}"
        )
    if tag == "d":
        props = node.find(f"{{{M}}}dPr")

        def delimiter(name, default):
            setting = props.find(f"{{{M}}}{name}") if props is not None else None
            return (
                setting.get(f"{{{M}}}val", default) if setting is not None else default
            )

        begin, end = delimiter("begChr", "("), delimiter("endChr", ")")
        begin = {"{": r"\{", "}": r"\}"}.get(begin, begin) or "."
        end = {"{": r"\{", "}": r"\}"}.get(end, end) or "."
        values = [_math_text(e) for e in node.findall(f"{{{M}}}e")]
        return (
            r"\left" + begin + delimiter("sepChr", "|").join(values) + r"\right" + end
        )
    if tag == "m":
        rows = [
            " & ".join(_math_text(e) for e in row.findall(f"{{{M}}}e"))
            for row in node.findall(f"{{{M}}}mr")
        ]
        return r"\begin{matrix}" + r" \\ ".join(rows) + r"\end{matrix}"
    if tag == "eqArr":
        return (
            r"\begin{aligned}"
            + r" \\ ".join(_math_text(e) for e in node.findall(f"{{{M}}}e"))
            + r"\end{aligned}"
        )
    if tag == "limLow":
        return "{" + child("e") + "}_{" + child("lim") + "}"
    if tag == "limUpp":
        return "{" + child("e") + "}^{" + child("lim") + "}"
    if tag == "sPre":
        return "{}_{" + child("sub") + "}^{" + child("sup") + "}" + child("e")
    if tag == "bar":
        return r"\overline{" + child("e") + "}"
    if tag == "acc":
        accent = node.find(f"{{{M}}}accPr/{{{M}}}chr")
        mark = accent.get(f"{{{M}}}val", "̂") if accent is not None else "̂"
        command = {
            "̂": r"\hat",
            "̄": r"\bar",
            "⃗": r"\vec",
            "̇": r"\dot",
            "̈": r"\ddot",
            "̃": r"\tilde",
        }.get(mark, r"\hat")
        return command + "{" + child("e") + "}"
    if tag == "nary":
        symbol = node.find(f"{{{M}}}naryPr/{{{M}}}chr")
        value = symbol.get(f"{{{M}}}val", "∑") if symbol is not None else "∑"
        return (
            value
            + ("_{" + child("sub") + "}" if child("sub") else "")
            + ("^{" + child("sup") + "}" if child("sup") else "")
            + child("e")
        )
    return "".join(_math_text(c) for c in children)


def _docx_fallback(path, reason=None):
    blocks, heading, title = [], "", _title_from_filename(path)
    with zipfile.ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError("DOCX 解压内容超过处理上限。")
        root = ET.fromstring(archive.read("word/document.xml"))
        for item in root.find("w:body", NS):
            if item.tag == f"{{{W}}}tbl":
                rows = [
                    [
                        "".join(t.text or "" for t in cell.findall(".//w:t", NS))
                        for cell in row.findall("w:tc", NS)
                    ]
                    for row in item.findall("w:tr", NS)
                ]
                blocks.append(
                    _table_block(
                        rows,
                        heading,
                        {"table_index": sum(b["kind"] == "table" for b in blocks) + 1},
                    )
                )
                continue
            if item.tag != f"{{{W}}}p":
                continue
            texts = []
            for part in item:
                if part.tag in {f"{{{M}}}oMath", f"{{{M}}}oMathPara"}:
                    texts.append("$" + _math_text(part) + "$")
                else:
                    texts.append(
                        "".join(t.text or "" for t in part.findall(".//w:t", NS))
                    )
            text = "".join(texts).strip()
            style_node = item.find("w:pPr/w:pStyle", NS)
            style = style_node.get(f"{{{W}}}val", "") if style_node is not None else ""
            if re.match(r"(?i)(?:heading|标题)\s*\d*", style) or style.lower() in {
                "title",
                "subtitle",
            }:
                heading = text
                if title == _title_from_filename(path) and style.lower() == "title":
                    title = text
                blocks.append(
                    _block("heading", text, heading, metadata={"style": style})
                )
            elif text:
                blocks.append(_block("text", text, heading, metadata={"style": style}))
            for math in item.findall(".//m:oMath", NS):
                latex = _math_text(math)
                if latex:
                    blocks.append(
                        _block(
                            "formula",
                            latex,
                            heading,
                            metadata={
                                "latex": latex,
                                "original_text": "".join(
                                    t.text or "" for t in math.findall(".//m:t", NS)
                                ),
                                "source_omml": ET.tostring(math, encoding="unicode"),
                                "recognition": "source_omml",
                            },
                        )
                    )
            for blip in item.findall(".//a:blip", NS):
                rid = blip.get(f"{{{NS['r']}}}embed")
                if not rid or "word/_rels/document.xml.rels" not in archive.namelist():
                    continue
                rels = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
                rel = next((r for r in rels if r.get("Id") == rid), None)
                if rel is None or rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target", "")
                name = "word/" + target.lstrip("/")
                if ".." in target or name not in archive.namelist():
                    continue
                raw = archive.read(name)
                if len(raw) < 4 * 1024 * 1024 and Path(name).suffix.lower() in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".webp",
                }:
                    mime = (
                        "image/jpeg"
                        if Path(name).suffix.lower() in {".jpg", ".jpeg"}
                        else "image/" + Path(name).suffix[1:]
                    )
                    encoded = base64.b64encode(raw).decode()
                    blocks.append(
                        _block(
                            "figure",
                            "",
                            heading,
                            metadata={
                                "image_url": f"data:{mime};base64," + encoded,
                                "image_base64": encoded,
                                "mime_type": mime,
                                "filename": Path(name).name,
                            },
                        )
                    )
    return _finish(
        title,
        blocks,
        "ooxml",
        [reason] if reason else [],
        {"status": "partial" if reason else "complete", "coordinates": "paragraphs"},
    )


def _pdf_title(document):
    metadata = (document.metadata or {}).get("title", "").strip()
    if len(metadata) > 10 and not re.match(
        r"(?i)^(?:untitled|microsoft|latex|arxiv|template|document|paper\.)", metadata
    ):
        return re.sub(r"\s+", " ", metadata)
    page = document[0]
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(s.get("text", "") for s in spans).strip()
            if len(text) < 3 or line["bbox"][1] > page.rect.height * 0.55:
                continue
            size = max((s.get("size", 0) for s in spans), default=0)
            lines.append({"text": text, "size": size, "box": line["bbox"]})
    candidates = [
        line
        for line in lines
        if len(line["text"]) > 10
        and not re.match(
            r"(?i)^(?:arxiv:|https?://|copyright|proceedings|submitted|published|accepted|ieee)",
            line["text"],
        )
    ]
    if not candidates:
        return metadata or "未命名论文"
    largest = max(line["size"] for line in candidates)
    chosen = [line for line in candidates if line["size"] >= largest * 0.93]
    chosen.sort(key=lambda x: (x["box"][1], x["box"][0]))
    first = chosen[0]
    title = [first["text"]]
    bottom = first["box"][3]
    for line in chosen[1:]:
        if line["box"][1] - bottom > largest * 2.0:
            break
        title.append(line["text"])
        bottom = line["box"][3]
    return re.sub(r"\s+", " ", " ".join(title))


def _pdf_text_coverage(path):
    import pymupdf

    with pymupdf.open(path) as doc:
        if doc.is_encrypted:
            raise ValueError("PDF 已加密，请提供可读取的原文件。")
        pages = len(doc)
        if not pages:
            raise ValueError("PDF 没有页面。")
        text_pages = sum(len(page.get_text().strip()) > 40 for page in doc)
        return pages, text_pages / max(pages, 1), _pdf_title(doc)


def _pdf_fallback(path, reason):
    import pymupdf

    blocks = []
    with pymupdf.open(path) as doc:
        title = _pdf_title(doc)
        for page in doc:
            spans = [
                s
                for b in page.get_text("dict")["blocks"]
                for line in b.get("lines", [])
                for s in line.get("spans", [])
                if s.get("text", "").strip()
            ]
            median = statistics.median([s["size"] for s in spans]) if spans else 10
            raw = [b for b in page.get_text("dict")["blocks"] if b.get("type") == 0]
            # Sort a two-column body within its columns, preserving full-width title/header material.
            left = [b for b in raw if b["bbox"][2] < page.rect.width * 0.58]
            right = [b for b in raw if b["bbox"][0] > page.rect.width * 0.42]
            if len(left) > 1 and len(right) > 1:
                body_top = max(
                    min(b["bbox"][1] for b in left), min(b["bbox"][1] for b in right)
                )
                full = [b for b in raw if b not in left and b not in right]
                raw = (
                    sorted(
                        [b for b in full if b["bbox"][1] < body_top],
                        key=lambda b: b["bbox"][1],
                    )
                    + sorted(left, key=lambda b: b["bbox"][1])
                    + sorted(right, key=lambda b: b["bbox"][1])
                    + sorted(
                        [b for b in full if b["bbox"][1] >= body_top],
                        key=lambda b: b["bbox"][1],
                    )
                )
            else:
                raw.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
            heading = ""
            for b in raw:
                text = "\n".join(
                    "".join(s["text"] for s in line["spans"])
                    for line in b.get("lines", [])
                ).strip()
                if not text:
                    continue
                size = max(
                    s.get("size", 0)
                    for line in b.get("lines", [])
                    for s in line.get("spans", [])
                )
                kind = "text"
                if len(text) < 180 and (
                    size > median * 1.15
                    or re.match(
                        r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:Abstract|Introduction|Method(?:ology)?|Experiments?|Results?|Conclusion|Discussion|References)\b",
                        text,
                        re.I,
                    )
                ):
                    kind, heading = "heading", text
                blocks.append(
                    _block(
                        kind,
                        text,
                        heading,
                        page.number + 1,
                        list(b["bbox"]),
                        {
                            "page_width": page.rect.width,
                            "page_height": page.rect.height,
                            "coordinate_origin": "top-left",
                        },
                    )
                )
        page_count = len(doc)
    return _finish(
        title,
        blocks,
        "pymupdf-layout",
        [reason, "当前为兼容文字与版面解析；公式、表格结构和图内内容尚未完成识别。"],
        {
            "status": "partial",
            "page_count": page_count,
            "formula_status": "not_parsed",
            "table_status": "not_parsed",
        },
    )


def _docling(path):
    # Keep all downloaded weights and model metadata inside this project.
    cache = ROOT / ".tmp" / "models"
    os.environ.setdefault("HF_HOME", str(cache / "huggingface"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("TORCH_HOME", str(cache / "torch"))
    os.environ.setdefault("DOCLING_ARTIFACTS_PATH", str(cache / "docling"))
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.pipeline_options import CodeFormulaVlmOptions
    from docling.datamodel.vlm_engine_options import TransformersVlmEngineOptions
    from docling.datamodel.accelerator_options import (
        AcceleratorOptions,
        AcceleratorDevice,
    )

    options = PdfPipelineOptions()
    options.accelerator_options = AcceleratorOptions(
        num_threads=4, device=AcceleratorDevice.CPU
    )
    full_formulas = (
        os.environ.get("PAPERSTRIDE_FORMULA_MODE", "bounded").lower() == "full"
    )
    options.do_formula_enrichment = full_formulas
    options.do_code_enrichment = full_formulas
    # The upstream preset prefers bfloat16, which is extremely slow on CPUs
    # without native BF16 instructions. Keep local processing in float32.
    options.code_formula_options = CodeFormulaVlmOptions.from_preset(
        "codeformulav2",
        engine_options=TransformersVlmEngineOptions(
            device=AcceleratorDevice.CPU,
            torch_dtype="float32",
            load_in_8bit=False,
            compile_model=False,
        ),
        expansion_factor=0.08,
    )
    options.do_table_structure = True
    options.generate_page_images = False
    options.generate_picture_images = False
    page_count, text_ratio, title = (None, None, _title_from_filename(path))
    if path.suffix.lower() == ".pdf":
        page_count, text_ratio, title = _pdf_text_coverage(path)
        options.do_ocr = text_ratio < 0.8
        if options.do_ocr:
            from docling.datamodel.pipeline_options import RapidOcrOptions

            options.ocr_options = RapidOcrOptions(backend="torch")
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    result = converter.convert(path)
    doc = result.document
    blocks, heading, warnings = [], "", []
    status = str(getattr(result, "status", "")).lower()
    if "failure" in status:
        raise RuntimeError("Docling 未能完成文档转换。")
    if "partial" in status:
        warnings.append("Docling 仅完成部分结构解析，请查看各内容块与原文。")
    for item, level in doc.iterate_items():
        label = str(getattr(item, "label", "")).split(".")[-1].lower()
        text = str(getattr(item, "text", "") or "")
        if label in {"page_header", "page_footer"}:
            continue
        metadata = {
            "label": label,
            "level": level,
            "docling_ref": getattr(item, "self_ref", ""),
        }
        provs = getattr(item, "prov", []) or []
        page, bbox = None, None
        if provs:
            prov = provs[0]
            page = getattr(prov, "page_no", None)
            box = getattr(prov, "bbox", None)
            page_info = doc.pages.get(page) if page is not None else None
            size = getattr(page_info, "size", None)
            width, height = getattr(size, "width", None), getattr(size, "height", None)
            if width and height:
                metadata.update(page_width=width, page_height=height)
            if box is not None:
                origin = str(getattr(box, "coord_origin", "")).lower()
                if "bottom" in origin and height:
                    bbox = [
                        float(box.l),
                        float(height - box.t),
                        float(box.r),
                        float(height - box.b),
                    ]
                else:
                    bbox = [float(box.l), float(box.t), float(box.r), float(box.b)]
                bbox = [
                    min(bbox[0], bbox[2]),
                    min(bbox[1], bbox[3]),
                    max(bbox[0], bbox[2]),
                    max(bbox[1], bbox[3]),
                ]
                metadata["coordinate_origin"] = "top-left"
        if label in {"title", "section_header"}:
            kind, heading = "heading", text
            if (
                label == "title"
                and text.strip()
                and title in {_title_from_filename(path), "未命名论文", "未命名资料"}
            ):
                title = text.strip()
        elif label == "formula":
            kind = "formula"
            metadata.update(
                latex=text if full_formulas else "",
                original_text=text,
                recognition="extracted_unverified" if full_formulas else "not_parsed",
            )
            if path.suffix.lower() == ".pdf" and page and bbox:
                import pymupdf

                with pymupdf.open(path) as pdf:
                    metadata["original_text"] = pdf[page - 1].get_textbox(
                        pymupdf.Rect(bbox)
                    )
                if not text.strip():
                    text = metadata["original_text"]
        elif label == "table":
            kind = "table"
            data = getattr(item, "data", None)
            if data is not None and data.num_rows and data.num_cols:
                cells = [
                    ["" for _ in range(data.num_cols)] for _ in range(data.num_rows)
                ]
                spans = []
                for cell in data.table_cells:
                    row, column = cell.start_row_offset_idx, cell.start_col_offset_idx
                    if 0 <= row < len(cells) and 0 <= column < len(cells[row]):
                        cells[row][column] = str(cell.text or "")
                        spans.append(
                            {
                                "row": row,
                                "column": column,
                                "row_span": cell.row_span,
                                "col_span": cell.col_span,
                            }
                        )
                metadata.update(cells=cells, cell_spans=spans)
                text = "\n".join("\t".join(row) for row in cells)
            else:
                text = item.export_to_markdown(doc=doc)
            metadata["table_index"] = sum(b["kind"] == "table" for b in blocks) + 1
            try:
                metadata["caption"] = item.caption_text(doc)
            except (AttributeError, TypeError):
                pass
        elif label == "picture":
            kind = "figure"
            try:
                text = item.caption_text(doc)
            except (AttributeError, TypeError):
                text = ""
            metadata["visual_content_status"] = "not_interpreted"
        elif label == "code":
            kind = "code"
            metadata["language"] = str(getattr(item, "code_language", "") or "")
        elif label == "caption":
            kind = "caption"
        else:
            kind = "text"
        if text.strip() or kind in {"figure", "formula"}:
            blocks.append(_block(kind, text, heading, page, bbox, metadata))
    if path.suffix.lower() == ".docx":
        # Page coordinates are not reliable for reflowable DOCX documents.
        for block in blocks:
            block["page"] = None
            block["bbox"] = None
        # Preserve OOXML formulas/images when an importer emitted only text.
        native = _docx_fallback(path)
        native_formulas = [b for b in native["blocks"] if b["kind"] == "formula"]
        imported_formulas = [b for b in blocks if b["kind"] == "formula"]
        if len(native_formulas) == len(imported_formulas):
            for imported, original in zip(imported_formulas, native_formulas):
                imported["text"] = original["text"]
                imported["metadata"].update(original["metadata"])
        elif native_formulas:
            blocks = [
                block for block in blocks if block["kind"] != "formula"
            ] + native_formulas
        native_images = [b for b in native["blocks"] if b["kind"] == "figure"]
        imported_images = [b for b in blocks if b["kind"] == "figure"]
        if imported_images:
            for imported, original in zip(imported_images, native_images):
                imported["metadata"].update(original["metadata"])
        else:
            blocks.extend(native_images)
        if title == _title_from_filename(path):
            title = native["title"]
    native_formula_count = sum(block["kind"] == "formula" for block in blocks)
    formula_coverage = (
        {
            "total": native_formula_count,
            "selected": native_formula_count,
            "attempted": native_formula_count,
            "recognized": native_formula_count,
            "mode": "source_omml",
        }
        if path.suffix.lower() == ".docx"
        else {}
    )
    if path.suffix.lower() == ".pdf" and not full_formulas:
        try:
            formula_coverage, formula_warnings = _bounded_enrich_formulas(path, blocks)
            warnings.extend(formula_warnings)
        except Exception as exc:
            log.warning(
                "Formula worker unavailable: %s: %s", type(exc).__name__, str(exc)[:500]
            )
            formula_coverage = {
                "total": sum(block["kind"] == "formula" for block in blocks),
                "selected": 0,
                "attempted": 0,
                "recognized": 0,
                "mode": "bounded",
            }
            warnings.append("公式转写未完成，已保留结构解析、公式原图与来源文字。")
    from app.knowledge.math_content import usable_latex
    for block in blocks:
        if block["kind"] == "formula" and block["metadata"].get("latex") and not usable_latex(block["metadata"]["latex"]):
            block["metadata"]["recognition"] = "malformed_latex"
            block["metadata"]["latex"] = ""
            warnings.append("部分公式转写包含缺失字符或不完整结构，已保留原图供核对。")
    formula_coverage["recognized"] = sum(bool(usable_latex(b["metadata"].get("latex"))) for b in blocks if b["kind"] == "formula")
    return _finish(
        title,
        blocks,
        "docling",
        warnings,
        {
            "status": "partial" if warnings else "complete",
            "page_count": page_count,
            "text_page_ratio": text_ratio,
            "formula_status": "partial"
            if formula_coverage.get("recognized", 0) < formula_coverage.get("total", 0)
            else "extracted_unverified",
            "formula_coverage": formula_coverage,
            "figure_status": "captions_and_regions",
            "table_status": "extracted_unverified",
        },
    )


def _bounded_enrich_formulas(path, blocks):
    """Keep document layout available even when local formula inference is slow."""
    import pymupdf

    formulas = [
        (index, block)
        for index, block in enumerate(blocks)
        if block["kind"] == "formula"
    ]
    coverage = {
        "total": len(formulas),
        "selected": 0,
        "attempted": 0,
        "recognized": 0,
        "mode": "bounded",
    }
    if not formulas:
        return coverage, []
    limit = max(0, min(32, int(os.environ.get("PAPERSTRIDE_FORMULA_MAX_ITEMS", "4"))))
    budget = max(
        0, min(600, float(os.environ.get("PAPERSTRIDE_FORMULA_BUDGET_SECONDS", "45")))
    )

    def rank(pair):
        index, block = pair
        title = block["heading"].casefold()
        score = 4 * bool(
            re.search(
                r"method|approach|policy|architecture|algorithm|model|方法|算法|模型|结构",
                title,
            )
        )
        score -= 8 * bool(
            re.search(r"appendix|supplement|reference|附录|参考文献", title)
        )
        score -= 3 * bool(re.search(r"introduction|background|引言|背景", title))
        return (-score, len(block["text"]) > 800, index)

    selected = sorted(formulas, key=rank)[:limit]
    if not selected or budget == 0:
        return coverage, ["已识别公式区域；本次未启用公式转写，可继续查看原图。"]
    payload = []
    with pymupdf.open(path) as pdf:
        for index, block in selected:
            if not block.get("page") or not block.get("bbox"):
                continue
            page = pdf[block["page"] - 1]
            region = pymupdf.Rect(block["bbox"])
            padding = max(2, min(10, region.height * 0.08))
            region = (region + (-padding, -padding, padding, padding)) & page.rect
            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(1.67, 1.67), clip=region, alpha=False
            )
            payload.append(
                {
                    "index": index,
                    "image": base64.b64encode(pix.tobytes("png")).decode("ascii"),
                }
            )
    coverage["selected"] = len(payload)
    if not payload:
        return coverage, ["公式区域没有可用页面定位，已保留来源文字。"]
    warnings = []
    with tempfile.TemporaryDirectory(
        prefix="stride-formulas-", dir=ROOT / ".tmp", ignore_cleanup_errors=True
    ) as folder:
        temp = Path(folder)
        request, result = temp / "request.json", temp / "result.json"
        request.write_text(json.dumps({"images": payload}), encoding="utf-8")
        with (temp / "worker.log").open("w", encoding="utf-8") as log_file:
            # Use the real interpreter: Windows venv launchers may leave a
            # different Python PID alive after a timed-out launcher is killed.
            executable = getattr(sys, "_base_executable", sys.executable)
            packages = str(
                Path(sys.prefix)
                / (
                    "Lib/site-packages"
                    if os.name == "nt"
                    else f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
                )
            )
            command = [
                executable,
                "-X",
                "utf8",
                "-c",
                "import sys,site,runpy; site.addsitedir(sys.argv.pop(1)); runpy.run_module('app.knowledge.parser_worker',run_name='__main__')",
                packages,
                "--formula-input",
                str(request),
                "--formula-output",
                str(result),
            ]
            process = subprocess.Popen(
                command,
                cwd=ROOT / "backend",
                stdout=log_file,
                stderr=log_file,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                process.wait(timeout=budget)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        check=False,
                    )
                process.kill()
                process.wait(timeout=10)
                warnings.append(
                    f"公式转写达到 {int(budget)} 秒预算，已保留完成结果和其余公式原图。"
                )
        if process.returncode and not result.is_file():
            log.warning(
                "Formula worker exited with code %s: %s",
                process.returncode,
                (temp / "worker.log").read_text(encoding="utf-8", errors="replace")[
                    -1200:
                ],
            )
        if result.is_file():
            try:
                data = json.loads(result.read_text(encoding="utf-8"))
                coverage["attempted"] = len(data.get("attempted", []))
                for item in data.get("results", []):
                    from app.knowledge.math_content import usable_latex
                    index = item.get("index")
                    latex = usable_latex(item.get("latex"))
                    if (
                        not isinstance(index, int)
                        or index < 0
                        or index >= len(blocks)
                        or not latex
                    ):
                        continue
                    block = blocks[index]
                    block["text"] = latex
                    block["metadata"].update(
                        latex=latex, recognition="extracted_unverified"
                    )
                    coverage["recognized"] += 1
                warnings.extend(data.get("errors", []))
            except (ValueError, OSError):
                warnings.append("公式转写结果不完整，已保留原图与来源文字。")
    if coverage["recognized"] < coverage["total"]:
        warnings.append(
            f"检测到 {coverage['total']} 个公式区域，已转写 {coverage['recognized']} 个；其余保留原图，未标为已识别。"
        )
    return coverage, warnings


def run_formula_worker(request_path, output_path):
    """One disposable CPU worker; persist each completed formula before the next."""
    import torch
    from PIL import Image
    from docling.datamodel.accelerator_options import (
        AcceleratorOptions,
        AcceleratorDevice,
    )
    from docling.datamodel.pipeline_options import CodeFormulaVlmOptions
    from docling.datamodel.vlm_engine_options import TransformersVlmEngineOptions
    from docling.models.inference_engines.vlm import create_vlm_engine, VlmEngineInput
    from docling.models.utils.generation_utils import TailRepetitionStopper

    torch.set_num_threads(4)
    options = CodeFormulaVlmOptions.from_preset(
        "codeformulav2",
        engine_options=TransformersVlmEngineOptions(
            device=AcceleratorDevice.CPU,
            torch_dtype="float32",
            load_in_8bit=False,
            compile_model=False,
        ),
    )
    engine = create_vlm_engine(
        options=options.engine_options,
        model_spec=options.model_spec,
        accelerator_options=AcceleratorOptions(
            num_threads=4, device=AcceleratorDevice.CPU
        ),
        artifacts_path=ROOT / ".tmp/models/docling",
        enable_remote_services=False,
    )
    items = json.loads(Path(request_path).read_text(encoding="utf-8"))["images"]
    state = {"attempted": [], "results": [], "errors": []}
    output_path = Path(output_path)

    def save():
        staging = output_path.with_suffix(".writing")
        staging.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        staging.replace(output_path)

    save()
    for item in items:
        state["attempted"].append(item["index"])
        save()
        try:
            image = Image.open(io.BytesIO(base64.b64decode(item["image"]))).convert(
                "RGB"
            )
            value = engine.predict_batch(
                [
                    VlmEngineInput(
                        image=image,
                        prompt="<formula>",
                        max_new_tokens=256,
                        temperature=0.0,
                        extra_generation_config={
                            "skip_special_tokens": False,
                            "custom_stopping_criteria": [TailRepetitionStopper()],
                        },
                    )
                ]
            )[0]
            latex = re.sub(
                r"<\|[^|]*\|>|</?doctag>|<end_of_utterance>|</?formula>|<loc_\d+>",
                "",
                value.text,
            ).strip()
            from app.knowledge.math_content import usable_latex
            latex = usable_latex(latex)
            if not latex:
                state["errors"].append("一处公式转写未通过结构检查，保留原图。")
            else:
                state["results"].append({"index": item["index"], "latex": latex})
        except Exception as exc:
            log.warning("Formula extraction failed: %s", type(exc).__name__)
            state["errors"].append("一处公式转写失败，保留原图。")
        save()
    return state


def parse_source(path: Path, kind: str, use_docling: bool = True) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ValueError("资料原文件不存在。")
    suffix = path.suffix.lower()
    if suffix in {".docx", ".xlsx"}:
        with zipfile.ZipFile(path) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("文档解压内容超过 100 MiB，请拆分后上传。")
    if path.name.lower().endswith(".repo.json"):
        return _native_repository(path)
    if suffix in CODE_SUFFIXES or kind == "code":
        return _native_code(path)
    if suffix in {".md", ".markdown", ".txt", ".rst", ".tex"}:
        return _native_text(path)
    if suffix == ".json":
        return _native_json(path)
    if suffix in {".html", ".htm"}:
        return _native_html(path)
    if suffix in {".csv", ".tsv"}:
        return _native_csv(path)
    if suffix == ".xlsx":
        return _native_xlsx(path)
    if suffix not in {".pdf", ".docx"}:
        raise ValueError(f"暂不支持 {suffix or '无扩展名'} 格式。")
    if use_docling:
        try:
            return _docling(path)
        except Exception as exc:
            log.warning(
                "Structured parser unavailable: %s: %s",
                type(exc).__name__,
                str(exc)[:500],
            )
            reason = f"结构解析未完成（{type(exc).__name__}），已保留兼容解析结果。"
    else:
        reason = "本次未启用 Docling 结构解析，使用兼容解析。"
    return (
        _pdf_fallback(path, reason)
        if suffix == ".pdf"
        else _docx_fallback(path, reason)
    )
