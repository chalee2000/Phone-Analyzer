"""Read Android device identity, build, battery and storage over ADB."""

from __future__ import annotations

import re

from ..models import DeviceInfo
from .adb import Transport

_PROP = re.compile(r"^\[(?P<k>[^\]]+)\]: \[(?P<v>.*)\]\s*$")

MARKET_NAME_PROPS = (
    "ro.product.marketname",
    "ro.product.vendor.marketname",
    "ro.product.odm.marketname",
    "ro.config.marketing_name",
    "ro.vendor.oplus.market.name",
    "ro.vivo.market.name",
)

BATTERY_STATUS = {"1": "unknown", "2": "charging", "3": "discharging", "4": "not_charging", "5": "full"}

# Properties shown in the "more details" table when present.
EXTRA_PROPS = (
    "ro.build.display.id",
    "ro.build.type",
    "ro.build.tags",
    "ro.build.date",
    "ro.boot.verifiedbootstate",
    "ro.boot.flash.locked",
    "ro.crypto.state",
    "ro.crypto.type",
    "ro.miui.ui.version.name",
    "ro.build.version.oneui",
    "ro.build.version.emui",
    "ro.build.version.opporom",
    "gsm.version.baseband",
    "gsm.sim.operator.alpha",
    "gsm.sim.state",
    "persist.sys.locale",
)


def parse_getprop(output: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in output.splitlines():
        m = _PROP.match(line.strip())
        if m:
            props[m["k"]] = m["v"]
    return props


def parse_battery(output: str) -> tuple[int | None, str]:
    level, status, powered = None, "", False
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("level:"):
            try:
                level = int(line.split(":", 1)[1])
            except ValueError:
                pass
        elif line.startswith("status:"):
            status = BATTERY_STATUS.get(line.split(":", 1)[1].strip(), "")
        elif line.endswith("powered: true"):
            powered = True
    if not status:
        status = "charging" if powered else "unplugged"
    return level, status


def parse_df(output: str) -> tuple[int | None, int | None]:
    """``df -k /data`` → (total bytes, free bytes)."""
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and parts[1].isdigit():
            return int(parts[1]) * 1024, int(parts[3]) * 1024
    return None, None


def parse_accounts(output: str) -> list[str]:
    accounts = []
    for m in re.finditer(r"Account \{name=([^,]+), type=([^}]+)\}", output):
        item = f"{m[1]} ({m[2]})"
        if item not in accounts:
            accounts.append(item)
    return accounts


def parse_parcel_string(output: str) -> str:
    """Decode the UTF-16 string returned by ``service call iphonesubinfo``."""
    chars = "".join(re.findall(r"'([^']*)'", output))
    return chars.replace(".", "").strip()


def read_imei(t: Transport, sdk: int) -> tuple[str, str]:
    """IMEI is readable over ADB only on Android 9 and older."""
    if sdk >= 29:
        return "", "android_10_plus"
    for code in (1, 4):
        try:
            value = parse_parcel_string(t.shell(f"service call iphonesubinfo {code} s16 com.android.shell", timeout=10))
        except Exception:
            continue
        if re.fullmatch(r"\d{14,16}", value):
            return value, ""
    return "", "permission_denied"


def read_device_info(t: Transport) -> DeviceInfo:
    props = parse_getprop(t.shell("getprop", timeout=20))
    sdk = int(props.get("ro.build.version.sdk", "0") or 0)
    market = next((props[p] for p in MARKET_NAME_PROPS if props.get(p)), "")
    brand = props.get("ro.product.brand", "").strip()
    if brand.islower():
        brand = brand.capitalize()  # "samsung" → "Samsung"
    info = DeviceInfo(
        platform="android",
        serial=props.get("ro.serialno") or props.get("ro.boot.serialno") or t.serial,
        brand=brand,
        model=props.get("ro.product.model", ""),
        market_name=market,
        product=props.get("ro.product.name", ""),
        device_name=props.get("ro.product.device", ""),
        os_version=props.get("ro.build.version.release", ""),
        build_id=props.get("ro.build.id", ""),
        security_patch=props.get("ro.build.version.security_patch", ""),
        fingerprint=props.get("ro.build.fingerprint", ""),
        cpu_abi=props.get("ro.product.cpu.abi", ""),
        carrier=props.get("gsm.operator.alpha", "").strip(",") or props.get("gsm.sim.operator.alpha", "").strip(","),
        timezone=props.get("persist.sys.timezone", ""),
    )
    info.extra = {k: props[k] for k in EXTRA_PROPS if props.get(k)}
    info.extra["ro.build.version.sdk"] = str(sdk)

    try:
        info.battery_level, info.battery_status = parse_battery(t.shell("dumpsys battery", timeout=15))
    except Exception:
        pass
    try:
        info.storage_total, info.storage_free = parse_df(t.shell("df -k /data", timeout=15))
    except Exception:
        pass
    try:
        mac = t.shell("cat /sys/class/net/wlan0/address 2>/dev/null", timeout=5).strip()
        if re.fullmatch(r"[0-9a-fA-F:]{17}", mac):
            info.wifi_mac = mac
    except Exception:
        pass
    try:
        name = t.shell("settings get secure bluetooth_name", timeout=5).strip()
        if name and name != "null":
            info.bluetooth_name = name
    except Exception:
        pass
    try:
        info.accounts = parse_accounts(t.shell("dumpsys account", timeout=20))
    except Exception:
        pass
    info.imei, reason = read_imei(t, sdk)
    if reason:
        info.restricted["imei"] = reason
    return info
