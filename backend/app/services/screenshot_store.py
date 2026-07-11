"""Filesystem storage helpers for device-uploaded screenshots.

Layout::

    {settings.screenshots_dir}/{family_id}/{device_id}/{uuid4.hex}.jpg

The relative path stored in the DB is
``{family_id}/{device_id}/{uuid4.hex}.jpg`` so that the absolute location
remains resolvable when the root moves between deploys. ``uuid4.hex`` is the
only segment that varies — it is generated server-side, never read from the
upload, so there is no path-traversal vector regardless of what the agent
sends.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from app.core.config import get_settings

# Permissions for newly-created leaf directories. 0o750 = rwx for owner,
# rx for group, none for others — fine on a single-user Linux host. Windows
# ignores mode bits.
_DIR_MODE = 0o750


def _root() -> Path:
    return Path(get_settings().screenshots_dir)


def _ensure_dir(path: Path) -> None:
    """mkdir -p with a sane mode. exist_ok keeps this idempotent."""
    path.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)


def _safe_ext(content_type: str | None, payload: bytes) -> str:
    """Pick a file extension based on the magic bytes; never trust the
    caller-supplied content-type alone."""
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    # Default to .bin so the bytes are preserved; the route guards against
    # unknown formats upstream, so we shouldn't normally reach this.
    return ".bin"


async def save_jpeg(
    family_id: int, device_pk: int, payload: bytes
) -> tuple[str, str, int]:
    """Persist ``payload`` under the screenshots dir.

    Returns ``(relative_path, sha256_hex, bytes_size)`` for the caller to
    record on the ``Screenshot`` row.
    """
    ext = _safe_ext(None, payload)
    rel_dir = Path(str(family_id)) / str(device_pk)
    abs_dir = _root() / rel_dir
    _ensure_dir(abs_dir)

    name = f"{uuid.uuid4().hex}{ext}"
    rel_path = str(rel_dir / name)
    abs_path = _root() / rel_path

    sha_hex = hashlib.sha256(payload).hexdigest()
    size = len(payload)

    # write+fsync would be nicer but Python's open() doesn't fsync on close
    # cross-platform; the cost/benefit isn't worth it for this throughput.
    with open(abs_path, "wb") as f:
        f.write(payload)

    return rel_path, sha_hex, size


async def open_jpeg(relative_path: str) -> bytes:
    """Read back a previously-stored screenshot.

    ``relative_path`` must already be in the form we wrote — that means no
    leading slash, no ``..``, no absolute path. Anything that fails the
    shape check is treated as a 404-equivalent: the caller raises HTTPException.
    """
    # Defensive normalisation: reject anything that isn't a clean relative
    # path. This blocks both classic traversal (``../../etc/passwd``) and
    # absolute paths from a tampered DB row.
    p = Path(relative_path)
    if p.is_absolute():
        raise ValueError("storage_path must be relative")
    if any(part == ".." for part in p.parts):
        raise ValueError("storage_path must not contain .. segments")

    abs_path = (_root() / p).resolve()
    root_resolved = _root().resolve()
    # Belt-and-braces containment: even if a path slipped past the checks
    # above, refuse to read anything outside the configured root.
    try:
        abs_path.relative_to(root_resolved)
    except ValueError as e:
        raise ValueError("storage_path escapes screenshots root") from e

    if not abs_path.is_file():
        raise FileNotFoundError(relative_path)

    with open(abs_path, "rb") as f:
        return f.read()
