"""Create an iOS backup (iTunes / Finder format) and read files from it.

Apple only includes call history, Safari history, Wi-Fi networks and health
data in *encrypted* backups. When the device does not encrypt backups yet and
the examiner allowed it, a temporary backup password is set before the backup
and removed again afterwards. The temporary password is written to the audit
log so the raw backup stays verifiable.
"""

from __future__ import annotations

import plistlib
import secrets
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class BackupPasswordRequired(Exception):
    """The device already encrypts backups with a password the examiner must supply."""


@dataclass
class BackupResult:
    directory: Path  # <dest>/<udid>
    encrypted: bool
    password: str
    temporary_password: bool


async def make_backup(
    lockdown,
    dest: Path,
    progress: Callable[[float], None],
    audit: Callable[[str, str], None],
    password: str = "",
    allow_temporary_encryption: bool = False,
) -> BackupResult:
    from pymobiledevice3.services.mobilebackup2 import Mobilebackup2Service

    svc = Mobilebackup2Service(lockdown)
    dest.mkdir(parents=True, exist_ok=True)
    encrypted = await svc.get_will_encrypt()
    temporary = False
    if encrypted:
        if not password:
            raise BackupPasswordRequired()
        audit("ios.backup.encrypted", "device encrypts backups; examiner supplied the password")
    elif allow_temporary_encryption:
        password = "SPNI-" + secrets.token_hex(6)
        audit("ios.backup.temp_password.set", f"temporary backup password: {password}")
        await svc.change_password(dest, new=password)
        encrypted = temporary = True
    try:
        audit("ios.backup.start", f"full backup → {dest}")
        await svc.backup(full=True, backup_directory=dest, progress_callback=lambda p: progress(float(p) / 100.0))
        audit("ios.backup.finish", "ok")
    finally:
        if temporary:
            try:
                await svc.change_password(dest, old=password)
                audit("ios.backup.temp_password.removed", "backup encryption restored to off")
            except Exception as exc:  # report loudly: the device setting was changed
                audit("ios.backup.temp_password.remove_failed", repr(exc))
    return BackupResult(directory=dest / lockdown.udid, encrypted=encrypted, password=password, temporary_password=temporary)


# ── readers ─────────────────────────────────────────────────────────────
class BackupReader:
    """Read files from a backup by (domain, relativePath)."""

    def __init__(self, directory: Path, work: Path) -> None:
        self.directory = directory
        self.work = work
        self.work.mkdir(parents=True, exist_ok=True)
        self.manifest = self._open_manifest()

    def _open_manifest(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.directory / "Manifest.db")
        db.row_factory = sqlite3.Row
        return db

    def query(self, where: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.manifest.execute(
            f"SELECT fileID, domain, relativePath, flags, file FROM Files WHERE flags = 1 AND ({where})", params
        ).fetchall()

    def file_info(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            plist = plistlib.loads(row["file"])
            objects = plist.get("$objects", [])
            meta = objects[1] if len(objects) > 1 and isinstance(objects[1], dict) else {}
            return {"size": meta.get("Size"), "mtime": meta.get("LastModified"), "birth": meta.get("Birth")}
        except Exception:
            return {}

    def extract_row(self, row: sqlite3.Row, dest: Path) -> Path | None:
        src = self.directory / row["fileID"][:2] / row["fileID"]
        if not src.is_file():
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    def get(self, domain: str, relative_path: str) -> Path | None:
        rows = self.query("domain = ? AND relativePath = ?", (domain, relative_path))
        if not rows:
            return None
        dest = self.work / domain / relative_path
        if dest.is_file():
            return dest
        path = self.extract_row(rows[0], dest)
        if path is not None:
            # SQLite write-ahead logs hold recent, not yet checkpointed rows.
            for suffix in ("-wal", "-shm"):
                extra = self.query("domain = ? AND relativePath = ?", (domain, relative_path + suffix))
                if extra:
                    self.extract_row(extra[0], Path(str(dest) + suffix))
        return path

    def find(self, domain_like: str, path_like: str) -> list[sqlite3.Row]:
        return self.query("domain LIKE ? AND relativePath LIKE ?", (domain_like, path_like))

    def close(self) -> None:
        self.manifest.close()


class EncryptedBackupReader(BackupReader):
    def __init__(self, directory: Path, work: Path, password: str) -> None:
        from iphone_backup_decrypt import EncryptedBackup

        self.backup = EncryptedBackup(backup_directory=str(directory), passphrase=password)
        self.backup.test_decryption()
        super().__init__(directory, work)

    def _open_manifest(self) -> sqlite3.Connection:
        decrypted = self.work / "Manifest.decrypted.db"
        self.backup.save_manifest_file(str(decrypted))
        db = sqlite3.connect(decrypted)
        db.row_factory = sqlite3.Row
        return db

    def extract_row(self, row: sqlite3.Row, dest: Path) -> Path | None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.backup.extract_file(relative_path=row["relativePath"], domain_like=row["domain"], output_filename=str(dest))
        except Exception:
            return None
        return dest if dest.is_file() else None


def open_reader(result: BackupResult, work: Path) -> BackupReader:
    if result.encrypted:
        return EncryptedBackupReader(result.directory, work, result.password)
    return BackupReader(result.directory, work)
