"""Install the pinned official EZUIKit npm package on the user's HA host.

Third-party SDK bytes are intentionally NOT included in this repository.
This module downloads from npm and verifies EVERY used file against known
SHA256 hashes recorded from the user's previously working v9.0.5 package.
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
_MANIFEST = Path(__file__).with_name('sdk_hashes.json')
_MAX_TARBALL_BYTES = 64 * 1024 * 1024

def sdk_directory(hass: HomeAssistant) -> Path:
    # User-controlled data path, not managed/overwritten by HACS.
    return Path(hass.config.path('luxe_ezviz_sdk', '9.0.5'))

def _verified_sdk_folder(folder: Path, expected: dict[str,str]) -> bool:
    for name, digest in expected.items():
        path = folder / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return False
    return True

def _install_sdk(dest: Path, archive_bytes: bytes | None = None) -> None:
    spec = json.loads(_MANIFEST.read_text('utf-8'))
    expected: dict[str,str] = spec['files']
    if _verified_sdk_folder(dest, expected):
        return
    if archive_bytes is None:
        req = Request(spec['source'], headers={'User-Agent':'Luxe-EZVIZ-HACS/1.0'})
        with urlopen(req, timeout=45) as response:
            archive_bytes = response.read(_MAX_TARBALL_BYTES + 1)
    if len(archive_bytes)>_MAX_TARBALL_BYTES:
        raise ValueError('Official SDK archive exceeds allowed size')
    # Do not unpack arbitrary paths from a remote archive; only copy the
    # 14 expected regular files and verify all hashes before any publish.
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.ezviz-sdk-',dir=dest.parent) as stage_dir:
        stage = Path(stage_dir)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as tf:
            members={member.name:member for member in tf.getmembers() if member.isfile()}
            for name, digest in expected.items():
                member=members.get('package/'+name)
                if member is None:
                    raise ValueError(f'Official SDK archive missing {name}')
                if member.size>20*1024*1024:
                    raise ValueError(f'Unexpected SDK file size for {name}')
                source=tf.extractfile(member)
                if source is None:
                    raise ValueError(f'Could not read SDK file {name}')
                data=source.read()
                if hashlib.sha256(data).hexdigest()!=digest:
                    raise ValueError(f'Checksum mismatch for SDK resource {name}')
                path=stage/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(data)
        if not _verified_sdk_folder(stage, expected):
            raise ValueError('SDK verification failed after staging')
        # Replacing the cache only after a fully verified staging set.
        backup=dest.with_name(dest.name+'-backup')
        if backup.exists(): shutil.rmtree(backup)
        if dest.exists(): dest.rename(backup)
        try:
            shutil.copytree(stage,dest)
            if not _verified_sdk_folder(dest, expected):
                raise ValueError('SDK verification failed after installation')
        except Exception:
            if dest.exists(): shutil.rmtree(dest)
            if backup.exists(): backup.rename(dest)
            raise
        if backup.exists(): shutil.rmtree(backup)

async def async_prepare_sdk(hass: HomeAssistant) -> bool:
    try:
        await hass.async_add_executor_job(_install_sdk,sdk_directory(hass))
    except Exception as err:
        _LOGGER.error('EZUIKit 9.0.5 provisioning failed: %s. Check access to the official npm registry; no third-party SDK is shipped in HACS.',err)
        return False
    return True
