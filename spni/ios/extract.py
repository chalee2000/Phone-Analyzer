"""iOS logical extraction: lockdown values + full backup + database parsing."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from ..extract import BaseExtractor, ExtractionContext
from ..media import IMAGE_EXTS
from ..models import App, DeviceInfo, Unavailable
from . import device, parsers
from .backup import BackupReader, BackupResult, make_backup, open_reader

BACKUP_KINDS = {"calls", "contacts", "sms", "chats", "web", "notes", "voice", "wifi", "photos"}
ENCRYPTED_ONLY = {"calls", "web", "wifi"}


class IOSExtractor(BaseExtractor):
    platform = "ios"
    method = "itunes-backup"

    def __init__(self, serial: str) -> None:
        self.serial = serial

    def device_info(self) -> DeviceInfo:
        async def go():
            lockdown = await device.connect(self.serial)
            try:
                info, _, _ = await device.read_info(lockdown)
                try:
                    enc = await lockdown.get_value(domain="com.apple.mobile.backup", key="WillEncrypt")
                    info.extra["backup_encrypted"] = "1" if enc else "0"
                except Exception:
                    pass
                return info
            finally:
                await lockdown.close()

        return device.run(go())

    async def _device_phase(self, ctx: ExtractionContext):
        lockdown = await device.connect(self.serial)
        try:
            ctx.stage("ios_info")
            info, sims, _ = await device.read_info(lockdown)
            apps = {}
            if ctx.wants("apps"):
                try:
                    apps = await device.list_apps(lockdown)
                except Exception as exc:
                    ctx.audit("ios.apps.error", repr(exc))
            result = None
            if BACKUP_KINDS & set(ctx.kinds):
                def progress(p: float) -> None:
                    ctx.check_cancel()
                    ctx.stage("backup", p)

                ctx.stage("backup", 0.0)
                result = await make_backup(
                    lockdown,
                    ctx.extraction.raw_dir / "backup",
                    progress=progress,
                    audit=ctx.audit,
                    password=ctx.options.get("ios_backup_password", ""),
                    allow_temporary_encryption=bool(ctx.options.get("ios_allow_temp_encryption")),
                )
            return info, sims, apps, result
        finally:
            await lockdown.close()

    def run(self, ctx: ExtractionContext) -> DeviceInfo | None:
        info, sims, apps, result = device.run(self._device_phase(ctx))
        if ctx.wants("sim"):
            ctx.begin("sim")
            ctx.save("sim", sims)
        if ctx.wants("apps"):
            ctx.begin("apps")
            ctx.save("apps", self._apps(apps))
        if result is None:
            return info
        self._hash_backup(ctx, result)
        reader = open_reader(result, ctx.extraction.raw_dir / "decoded")
        try:
            self._parse(ctx, reader, result)
        finally:
            reader.close()
        return info

    # ── helpers ───────────────────────────────────────────────────────────
    def _hash_backup(self, ctx: ExtractionContext, result: BackupResult) -> None:
        ctx.stage("hashing", 0.0)
        files = [p for p in result.directory.rglob("*") if p.is_file()]
        ctx.extraction.register_many(
            ((p, f"backup:{p.relative_to(result.directory).as_posix()}") for p in files),
            progress=lambda f: ctx.stage("hashing", f),
        )
        ctx.audit("ios.backup.hashed", f"{len(files)} files; encrypted={result.encrypted}")

    def _apps(self, apps: dict) -> list[App]:
        out = []
        for bundle, meta in apps.items():
            out.append(App(
                package=bundle,
                name=meta.get("CFBundleDisplayName") or meta.get("CFBundleName") or bundle,
                version=str(meta.get("CFBundleShortVersionString") or meta.get("CFBundleVersion") or ""),
                system=meta.get("ApplicationType") == "System",
                installer="App Store" if meta.get("ApplicationType") == "User" else "",
            ))
        out.sort(key=lambda a: a.name.lower())
        return out

    def _missing(self, ctx: ExtractionContext, kind: str, result: BackupResult) -> None:
        if kind in ENCRYPTED_ONLY and not result.encrypted:
            ctx.unavailable(kind, Unavailable.REQUIRES_ENCRYPTED_BACKUP.value)
        else:
            ctx.unavailable(kind, Unavailable.NOT_IN_BACKUP.value)

    def _parse(self, ctx: ExtractionContext, reader: BackupReader, result: BackupResult) -> None:
        names: dict[str, str] = {}

        def run(kind: str, fn):
            if not ctx.wants(kind):
                return
            ctx.begin(kind)
            try:
                records = fn()
            except Exception as exc:
                ctx.error(kind, exc)
                return
            if records is None:
                self._missing(ctx, kind, result)
            else:
                ctx.save(kind, records)

        def contacts():
            path = reader.get(*parsers.ADDRESSBOOK_DB)
            if not path:
                return None
            items = parsers.parse_addressbook(path)
            names.update(parsers.contact_index(items))
            return items

        def from_db(spec, parse):
            path = reader.get(*spec)
            return parse(path) if path else None

        run("contacts", contacts)
        run("calls", lambda: from_db(parsers.CALLS_DB, lambda p: parsers.parse_calls(p, names)))
        run("sms", lambda: from_db(parsers.SMS_DB, lambda p: parsers.parse_sms(p, names)))
        run("chats", lambda: self._chats(reader))
        run("web", lambda: from_db(parsers.SAFARI_DB, parsers.parse_safari))
        run("notes", lambda: from_db(parsers.NOTES_DB, parsers.parse_notes))
        run("wifi", lambda: self._wifi(reader))
        run("voice", lambda: self._voice(ctx, reader))
        run("photos", lambda: self._photos(ctx, reader))

    def _chats(self, reader: BackupReader):
        found = False
        messages = []
        path = reader.get(*parsers.WHATSAPP_DB)
        if path:
            found = True
            messages += parsers.parse_whatsapp(path)
        for row in reader.find("%line%", "%Line.sqlite"):
            local = reader.extract_row(row, reader.work / row["domain"] / row["relativePath"])
            if local:
                found = True
                messages += parsers.parse_line(local)
        if not found:
            return None
        messages.sort(key=lambda m: m.timestamp or 0, reverse=True)
        return messages

    def _wifi(self, reader: BackupReader):
        rows = reader.find("%", "%com.apple.wifi-networks.plist") or reader.find("%", "%com.apple.wifi.plist")
        if not rows:
            return None
        local = reader.extract_row(rows[0], reader.work / rows[0]["domain"] / rows[0]["relativePath"])
        return parsers.parse_wifi_plist(local) if local else None

    def _voice(self, ctx: ExtractionContext, reader: BackupReader):
        rows = reader.find("%", "%Recordings/%.m4a")
        if not rows:
            return []
        titles: dict = {}
        for db_row in reader.find("%", "%Recordings/%Recordings.db"):
            local = reader.extract_row(db_row, reader.work / db_row["domain"] / db_row["relativePath"])
            if local:
                try:
                    titles.update(parsers.parse_voice_titles(local))
                except Exception:
                    pass
        memos = []
        for i, row in enumerate(rows):
            ctx.progress("voice", i / len(rows), count=i)
            name = PurePosixPath(row["relativePath"]).name
            local = reader.extract_row(row, ctx.extraction.media_dir / "voice" / name)
            if not local:
                continue
            meta = reader.file_info(row)
            mtime = int(meta["mtime"]) if meta.get("mtime") else None
            if mtime:
                os.utime(local, (mtime, mtime))
            digest = ctx.register(local, f"{row['domain']}/{row['relativePath']}")
            memos.append(parsers.voice_record(local, ctx.extraction.rel(local), digest, titles.get(name, {}), mtime * 1000 if mtime else None))
        memos.sort(key=lambda m: m.created or 0, reverse=True)
        return memos

    def _photos(self, ctx: ExtractionContext, reader: BackupReader):
        rows = [r for r in reader.find("CameraRollDomain", "Media/DCIM/%") if Path(r["relativePath"]).suffix.lower() in IMAGE_EXTS]
        limit = int(ctx.options.get("max_photos") or 0)
        if limit:
            rows = rows[-limit:]
        photos = []
        for i, row in enumerate(rows):
            ctx.progress("photos", i / max(1, len(rows)), count=i)
            rel = PurePosixPath(row["relativePath"])
            local = reader.extract_row(row, ctx.extraction.media_dir / "photos" / rel.parent.name / rel.name)
            if not local:
                continue
            meta = reader.file_info(row)
            mtime = int(meta["mtime"]) if meta.get("mtime") else None
            if mtime:
                os.utime(local, (mtime, mtime))
            photos.append(ctx.photo_record(local, f"/private/var/mobile/{rel}", album=rel.parent.name, modified=mtime * 1000 if mtime else None))
        photos.sort(key=lambda p: p.taken or 0, reverse=True)
        return photos
