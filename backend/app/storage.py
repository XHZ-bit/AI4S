"""Atomic, non-overwriting publication of original files."""

import os
import tempfile
from pathlib import Path


def save_original(path: Path, raw: bytes):
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("A different original already exists")
        return
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".upload-", suffix=".tmp", delete=False
        ) as output:
            temp = Path(output.name)
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        try:
            if os.name == "nt":
                # Windows rename is atomic and refuses an existing destination.
                # POSIX rename would overwrite, so keep link publication there.
                os.rename(temp, path)
            else:
                os.link(temp, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ValueError("A different original already exists")
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
