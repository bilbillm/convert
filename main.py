from __future__ import annotations

import os
import mimetypes
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.requests import Request
from starlette.background import BackgroundTask


APP_DIR = Path(__file__).resolve().parent
CONVERSION_TIMEOUT_SECONDS = int(os.getenv("CONVERSION_TIMEOUT_SECONDS", "600"))
CONVERSION_SLOTS = threading.BoundedSemaphore(int(os.getenv("CONVERSION_WORKERS", "2")))

IMAGE_INPUTS = {
    "avif", "bmp", "dds", "gif", "heic", "heif", "ico", "j2k", "jp2",
    "jpeg", "jpg", "pcx", "pgm", "png", "ppm", "psd", "tga",
    "tif", "tiff", "webp",
}
IMAGE_OUTPUTS = [
    "png", "jpg", "webp", "gif", "tiff", "bmp", "ico", "jp2", "dds",
    "psd", "pcx", "tga", "ppm", "pgm", "pbm",
]

WORD_INPUTS = {
    "doc", "docx", "docm", "odt", "rtf", "txt", "md", "mdown", "mkd",
    "markdown", "gfm", "html", "htm", "xhtml", "epub", "fb2", "tex",
    "latex", "rst", "org",
}
SHEET_INPUTS = {"xls", "xlsx", "xlsm", "ods", "csv", "tsv"}
SLIDE_INPUTS = {"ppt", "pptx", "pptm", "odp"}
PDF_INPUTS = {"pdf"}

WORD_OUTPUTS = ["pdf", "docx", "odt", "rtf", "txt", "html", "md", "epub", "fb2", "tex", "rst", "org", "gfm", "adoc", "png", "jpg", "webp"]
SHEET_OUTPUTS = ["pdf", "xlsx", "ods", "csv", "html", "png", "jpg", "webp"]
SLIDE_OUTPUTS = ["pdf", "pptx", "odp", "png", "jpg", "webp"]
PDF_OUTPUTS = ["txt", "png", "jpg", "webp", "tiff"]

FORMAT_LABELS = {
    "pdf": "PDF",
    "docx": "Word 文档（DOCX）",
    "odt": "OpenDocument 文本文档（ODT）",
    "rtf": "RTF 文档",
    "txt": "纯文本（TXT）",
    "html": "网页（HTML）",
    "md": "Markdown（MD）",
    "epub": "电子书（EPUB）",
    "fb2": "FictionBook 电子书（FB2）",
    "tex": "LaTeX（TEX）",
    "rst": "reStructuredText（RST）",
    "org": "Org Mode（ORG）",
    "gfm": "GitHub Markdown（GFM）",
    "asciidoc": "AsciiDoc（ADOC）",
    "adoc": "AsciiDoc（ADOC）",
    "xlsx": "Excel 工作簿（XLSX）",
    "ods": "OpenDocument 表格（ODS）",
    "csv": "CSV 表格",
    "pptx": "PowerPoint 演示文稿（PPTX）",
    "odp": "OpenDocument 演示文稿（ODP）",
    "png": "PNG 图片",
    "jpg": "JPEG 图片",
    "webp": "WebP 图片",
    "gif": "GIF 动图",
    "tiff": "TIFF 图片",
    "bmp": "BMP 图片",
    "ico": "图标（ICO）",
    "jp2": "JPEG 2000 图片",
    "dds": "DDS 纹理图片",
    "psd": "Photoshop 图片（PSD）",
    "pcx": "PCX 图片",
    "tga": "TGA 图片",
    "ppm": "PPM 图片",
    "pgm": "PGM 图片",
    "pbm": "PBM 图片",
}

PANDOC_INPUTS = {
    "docx": "docx",
    "odt": "odt",
    "rtf": "rtf",
    "txt": "markdown",
    "md": "markdown",
    "markdown": "markdown",
    "mdown": "markdown",
    "mkd": "markdown",
    "gfm": "gfm",
    "html": "html",
    "htm": "html",
    "xhtml": "html",
    "epub": "epub",
    "fb2": "fb2",
    "tex": "latex",
    "latex": "latex",
    "rst": "rst",
    "org": "org",
    "asciidoc": "asciidoc",
    "adoc": "asciidoc",
}
PANDOC_OUTPUTS = {
    "docx": "docx",
    "odt": "odt",
    "rtf": "rtf",
    "txt": "plain",
    "html": "html",
    "md": "markdown",
    "epub": "epub",
    "fb2": "fb2",
    "tex": "latex",
    "rst": "rst",
    "org": "org",
    "gfm": "gfm",
    "asciidoc": "asciidoc",
    "adoc": "asciidoc",
}
PANDOC_ONLY_INPUTS = {"md", "mdown", "mkd", "markdown", "gfm", "epub", "fb2", "tex", "latex", "rst", "org"}

app = FastAPI(title="Lumo Convert", docs_url=None, redoc_url=None)


class ConversionError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        self.message = message
        self.status_code = status_code


def extension_of(filename: str) -> str:
    name = re.split(r"[/\\]", filename or "")[ -1]
    return Path(name).suffix.lower().lstrip(".")


def family_of(extension: str) -> str | None:
    if extension in IMAGE_INPUTS:
        return "image"
    if extension in SHEET_INPUTS:
        return "spreadsheet"
    if extension in SLIDE_INPUTS:
        return "presentation"
    if extension in PDF_INPUTS:
        return "pdf"
    if extension in WORD_INPUTS:
        return "document"
    return None


def target_formats(extension: str) -> list[str]:
    family = family_of(extension)
    options = {
        "image": IMAGE_OUTPUTS,
        "document": WORD_OUTPUTS,
        "spreadsheet": SHEET_OUTPUTS,
        "presentation": SLIDE_OUTPUTS,
        "pdf": PDF_OUTPUTS,
    }.get(family, [])
    aliases = {"jpeg": "jpg", "htm": "html", "xhtml": "html", "markdown": "md", "mdown": "md", "mkd": "md", "latex": "tex", "tif": "tiff", "asciidoc": "adoc"}
    source_format = aliases.get(extension, extension)
    return [fmt for fmt in options if fmt != source_format]


def run_tool(command: list[str], timeout: int = CONVERSION_TIMEOUT_SECONDS) -> None:
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise ConversionError("服务器缺少所需的转换组件，请联系管理员。", 503) from exc
    except subprocess.TimeoutExpired as exc:
        raise ConversionError("转换耗时过长，请尝试较小的文件。", 504) from exc
    if result.returncode != 0:
        raise ConversionError("转换失败。请检查文件是否完整，以及所选格式是否兼容。")


def office_to_pdf(source: Path, extension: str, family: str, workdir: Path) -> Path:
    output_dir = workdir / "office-output"
    profile_dir = workdir / "lo-profile"
    output_dir.mkdir(exist_ok=True)
    profile_dir.mkdir(exist_ok=True)
    filters = {
        "document": "pdf:writer_pdf_Export",
        "spreadsheet": "pdf:calc_pdf_Export",
        "presentation": "pdf:impress_pdf_Export",
    }
    command = [
        "soffice", "--headless", "--nologo", "--nodefault", "--norestore", "--nolockcheck",
        f"-env:UserInstallation={profile_dir.as_uri()}", "--convert-to", filters[family],
        "--outdir", str(output_dir), str(source),
    ]
    run_tool(command)
    result = output_dir / f"{source.stem}.pdf"
    if not result.is_file() or result.stat().st_size == 0:
        raise ConversionError("无法生成 PDF。请确认原文件可以正常打开。")
    return result


def office_convert(source: Path, family: str, target: str, workdir: Path) -> Path:
    output_dir = workdir / "office-output"
    profile_dir = workdir / "lo-profile"
    output_dir.mkdir(exist_ok=True)
    profile_dir.mkdir(exist_ok=True)
    target_filter = target
    if target == "pdf":
        return office_to_pdf(source, extension_of(source.name), family, workdir)
    if target == "txt":
        target_filter = "txt:Text"
    command = [
        "soffice", "--headless", "--nologo", "--nodefault", "--norestore", "--nolockcheck",
        f"-env:UserInstallation={profile_dir.as_uri()}", "--convert-to", target_filter,
        "--outdir", str(output_dir), str(source),
    ]
    run_tool(command)
    result = output_dir / f"{source.stem}.{target}"
    if not result.is_file() or result.stat().st_size == 0:
        raise ConversionError("当前文件类型不支持所选的输出格式。")
    return result


def pandoc_convert(source: Path, source_ext: str, target: str, output: Path) -> Path:
    source_format = PANDOC_INPUTS.get(source_ext)
    target_format = PANDOC_OUTPUTS.get(target)
    if not source_format or not target_format:
        raise ConversionError("当前文件类型不支持所选的输出格式。")
    run_tool([
        "pandoc", "--from", source_format, "--to", target_format,
        "--wrap=none", "--output", str(output), str(source),
    ])
    if not output.is_file() or output.stat().st_size == 0:
        raise ConversionError("无法生成转换后的文件。")
    return output


def office_first_page_image(source: Path, family: str, target: str, workdir: Path) -> Path:
    pdf = office_to_pdf(source, extension_of(source.name), family, workdir)
    return pdf_first_page_image(pdf, target, workdir)


def pdf_first_page_image(source: Path, target: str, workdir: Path) -> Path:
    rendered = workdir / "first-page"
    run_tool(["pdftoppm", "-f", "1", "-l", "1", "-singlefile", "-r", "144", "-png", str(source), str(rendered)])
    png = rendered.with_suffix(".png")
    if not png.is_file() or png.stat().st_size == 0:
        raise ConversionError("无法读取 PDF 的第一页。")
    if target == "png":
        return png
    output = workdir / f"converted.{target}"
    command = [(shutil.which("magick") or "convert"), "-limit", "memory", "256MiB", "-limit", "map", "512MiB", str(png)]
    if target in {"jpg", "webp"}:
        command.extend(["-quality", "88"])
    command.append(str(output))
    run_tool(command)
    if not output.is_file() or output.stat().st_size == 0:
        raise ConversionError("无法生成目标图片。")
    return output


def image_convert(source: Path, source_ext: str, target: str, workdir: Path) -> Path:
    output = workdir / f"converted.{target}"
    read_path = str(source)
    if target not in {"gif", "tiff"}:
        read_path += "[0]"
    command = [
        (shutil.which("magick") or "convert"), "-limit", "memory", "256MiB", "-limit", "map", "512MiB",
        "-limit", "disk", "1024MiB", read_path, "-auto-orient", "-strip",
    ]
    if target in {"jpg", "webp"}:
        command.extend(["-quality", "88"])
    command.append(str(output))
    run_tool(command)
    if not output.is_file() or output.stat().st_size == 0:
        raise ConversionError("无法读取这张图片或生成目标格式。")
    return output


def document_convert(source: Path, source_ext: str, target: str, family: str, workdir: Path) -> Path:
    output = workdir / f"converted.{target}"
    if target in {"png", "jpg", "webp"}:
        if source_ext in PANDOC_ONLY_INPUTS:
            intermediate = workdir / "printable.docx"
            pandoc_convert(source, source_ext, "docx", intermediate)
            pdf = office_to_pdf(intermediate, "docx", "document", workdir)
            return pdf_first_page_image(pdf, target, workdir)
        return office_first_page_image(source, family, target, workdir)

    if target == "pdf":
        if source_ext in PANDOC_ONLY_INPUTS:
            intermediate = workdir / "printable.docx"
            pandoc_convert(source, source_ext, "docx", intermediate)
            return office_to_pdf(intermediate, "docx", "document", workdir)
        return office_to_pdf(source, source_ext, family, workdir)

    if target in PANDOC_OUTPUTS:
        if source_ext in PANDOC_INPUTS:
            return pandoc_convert(source, source_ext, target, output)
        intermediate = workdir / "office-source.docx"
        office_convert(source, family, "docx", workdir)
        office_output = workdir / "office-output" / f"{source.stem}.docx"
        if not office_output.is_file():
            raise ConversionError("无法读取此文档。")
        return pandoc_convert(office_output, "docx", target, output)

    return office_convert(source, family, target, workdir)


def safe_download_stem(filename: str) -> str:
    name = re.split(r"[/\\]", filename or "")[ -1]
    stem = Path(name).stem
    stem = re.sub(r"[^\w.-]+", "_", stem, flags=re.UNICODE).strip("._")
    return (stem or "converted")[:80]


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (APP_DIR / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/formats")
def formats(filename: str) -> dict[str, Any]:
    extension = extension_of(filename)
    family = family_of(extension)
    if not family:
        raise HTTPException(415, "暂不支持这种文件。请上传常见文档、表格、演示文稿或图片。")
    options = target_formats(extension)
    return {
        "extension": extension,
        "family": family,
        "targets": [{"format": fmt, "label": FORMAT_LABELS.get(fmt, fmt.upper())} for fmt in options],
    }


@app.post("/api/convert")
def convert(file: UploadFile = File(...), target_format: str = Form(...)) -> FileResponse:
    source_ext = extension_of(file.filename or "")
    family = family_of(source_ext)
    if not family:
        raise HTTPException(415, "暂不支持这种文件类型。")
    target = target_format.lower().strip().lstrip(".")
    if target not in target_formats(source_ext):
        raise HTTPException(400, "所选输出格式与此文件不兼容。")

    workdir = Path(tempfile.mkdtemp(prefix="lumo-convert-"))
    try:
        source_path = workdir / f"source.{source_ext}"
        total = 0
        with source_path.open("wb") as output_file:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                output_file.write(chunk)
        if total == 0:
            raise HTTPException(400, "文件内容为空。")

        CONVERSION_SLOTS.acquire()
        try:
            if family == "image":
                result_path = image_convert(source_path, source_ext, target, workdir)
            elif family == "pdf":
                if target == "txt":
                    result_path = workdir / "converted.txt"
                    run_tool(["pdftotext", "-layout", str(source_path), str(result_path)])
                else:
                    result_path = pdf_first_page_image(source_path, target, workdir)
            else:
                result_path = document_convert(source_path, source_ext, target, family, workdir)
        finally:
            CONVERSION_SLOTS.release()

        if not result_path.is_file() or result_path.stat().st_size == 0:
            raise ConversionError("转换没有生成有效文件。")
        download_name = f"{safe_download_stem(file.filename or 'converted')}.{target}"
        media_type = mimetypes.guess_type(download_name)[0] or "application/octet-stream"
        return FileResponse(
            result_path,
            media_type=media_type,
            filename=download_name,
            background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
        )
    except HTTPException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except ConversionError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(exc.status_code, exc.message) from exc
    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(500, "转换服务暂时不可用，请稍后再试。") from exc


def convert_path(source: Path, target: str, workdir: Path) -> Path:
    extension = extension_of(source.name)
    family = family_of(extension)
    with CONVERSION_SLOTS:
        if family == 'image':
            return image_convert(source, extension, target, workdir)
        if family == 'pdf':
            if target == 'txt':
                output = workdir / 'converted.txt'
                run_tool(['pdftotext', '-layout', str(source), str(output)])
                return output
            return pdf_first_page_image(source, target, workdir)
        return document_convert(source, extension, target, family, workdir)


from jobs import install
install(app, convert_path, extension_of, target_formats, safe_download_stem)
