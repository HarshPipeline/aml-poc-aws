"""Local originals for investigator viewing. S3 can replace this later."""

from pathlib import Path

from .config import ROOT

EVIDENCE_ROOT = Path(__file__).resolve().parent / "fixtures" / "evidence"
RUNTIME = ROOT / "runtime" / "documents"

MEDIA = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".txt": "text/plain",
}


def _suffix(name):
    return Path(name or "").suffix.lower()


def media_type(name):
    return MEDIA.get(_suffix(name), "application/octet-stream")


def save_upload(document_id, filename, content):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    path = RUNTIME / f"{document_id}{_suffix(filename)}"
    path.write_bytes(content)
    return path


def seeded_path(document_id):
    from .packets import SEEDED, _stable_id

    for packet in SEEDED:
        for item in packet["files"]:
            if _stable_id(item["relative"]) == document_id:
                path = EVIDENCE_ROOT / item["relative"]
                return path if path.is_file() else None
    return None


def locate(document):
    relative = document.get("source_relative")
    if relative:
        path = EVIDENCE_ROOT / relative
        if path.is_file():
            return path
    found = seeded_path(document.get("document_id", ""))
    if found:
        return found
    stored = RUNTIME / f"{document['document_id']}{_suffix(document.get('file_name'))}"
    return stored if stored.is_file() else None


def viewable(document):
    return locate(document) is not None
