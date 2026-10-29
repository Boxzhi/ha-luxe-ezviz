"""Provision the pinned official EZUIKit npm package for the production integration.

Only source code is shipped in this repository. SDK files are downloaded from the
official npm tarball and verified against immutable Git blob IDs and file sizes
from the official EZUIKit v9.0.24 source tag before installation.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
from pathlib import Path
import shutil
import tarfile
import tempfile
from urllib.request import Request, urlopen

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
_MANIFEST = Path(__file__).with_name("sdk_hashes.json")
_MAX_TARBALL_BYTES = 64 * 1024 * 1024
_MAX_FILE_BYTES = 20 * 1024 * 1024


def _spec() -> dict:
    return json.loads(_MANIFEST.read_text("utf-8"))


def sdk_directory(hass: HomeAssistant) -> Path:
    # Separate cache from the production integration and from every SDK version.
    version = str(_spec()["version"])
    return Path(hass.config.path("luxe_ezviz_sdk", version))


def _matches(data: bytes, expected: str | dict) -> bool:
    # Legacy manifests use SHA256. The v9.0.24 test manifest pins official Git blobs,
    # which also works for binary WASM files without text decoding.
    if isinstance(expected, str):
        return hashlib.sha256(data).hexdigest() == expected
    size = expected.get("size")
    git_blob_sha = expected.get("git_blob_sha")
    if not isinstance(size, int) or len(data) != size or not isinstance(git_blob_sha, str):
        return False
    header = b"blob " + str(len(data)).encode("ascii") + bytes((0,))
    return hashlib.sha1(header + data).hexdigest() == git_blob_sha


def _verified_sdk_folder(folder: Path, expected: dict[str, str | dict]) -> bool:
    for name, fingerprint in expected.items():
        path = folder / name
        if not path.is_file():
            return False
        try:
            data = path.read_bytes()
        except OSError:
            return False
        if not _matches(data, fingerprint):
            return False
    return True


def _install_sdk(dest: Path, archive_bytes: bytes | None = None) -> None:
    spec = _spec()
    expected: dict[str, str | dict] = spec["files"]
    if _verified_sdk_folder(dest, expected):
        return
    if archive_bytes is None:
        req = Request(spec["source"], headers={"User-Agent": "Luxe-EZVIZ/1.1.2"})
        with urlopen(req, timeout=45) as response:
            archive_bytes = response.read(_MAX_TARBALL_BYTES + 1)
    if len(archive_bytes) > _MAX_TARBALL_BYTES:
        raise ValueError("Official SDK archive exceeds allowed size")

    # Only extract explicitly pinned regular files; never unpack arbitrary paths.
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ezviz-sdk-", dir=dest.parent) as stage_dir:
        stage = Path(stage_dir)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tf:
            members = {member.name: member for member in tf.getmembers() if member.isfile()}
            for name, fingerprint in expected.items():
                member = members.get("package/" + name)
                if member is None:
                    raise ValueError(f"Official SDK archive missing {name}")
                if member.size > _MAX_FILE_BYTES:
                    raise ValueError(f"Unexpected SDK file size for {name}")
                source = tf.extractfile(member)
                if source is None:
                    raise ValueError(f"Could not read SDK file {name}")
                data = source.read()
                if not _matches(data, fingerprint):
                    raise ValueError(f"Official SDK fingerprint mismatch for {name}")
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

        if not _verified_sdk_folder(stage, expected):
            raise ValueError("SDK verification failed after staging")

        # Publish only after every file has passed verification; retain rollback on error.
        backup = dest.with_name(dest.name + "-backup")
        if backup.exists():
            shutil.rmtree(backup)
        if dest.exists():
            dest.rename(backup)
        try:
            shutil.copytree(stage, dest)
            if not _verified_sdk_folder(dest, expected):
                raise ValueError("SDK verification failed after installation")
        except Exception:
            if dest.exists():
                shutil.rmtree(dest)
            if backup.exists():
                backup.rename(dest)
            raise
        if backup.exists():
            shutil.rmtree(backup)


async def async_prepare_sdk(hass: HomeAssistant) -> bool:
    version = str(_spec()["version"])
    try:
        await hass.async_add_executor_job(_install_sdk, sdk_directory(hass))
    except Exception as err:
        _LOGGER.error(
            "EZUIKit %s SDK provisioning failed: %s. Check access to the official npm registry.",
            version,
            err,
        )
        return False
    return True
