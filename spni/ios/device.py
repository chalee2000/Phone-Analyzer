"""iPhone / iPad access through usbmuxd (Apple Mobile Device Service on Windows)."""

from __future__ import annotations

import asyncio
from typing import Any

from ..models import DeviceInfo, SimCard
from ..util import normalize_phone

PRODUCT_NAMES = {
    "iPhone10,1": "iPhone 8", "iPhone10,4": "iPhone 8", "iPhone10,2": "iPhone 8 Plus", "iPhone10,5": "iPhone 8 Plus",
    "iPhone10,3": "iPhone X", "iPhone10,6": "iPhone X", "iPhone11,2": "iPhone XS", "iPhone11,4": "iPhone XS Max",
    "iPhone11,6": "iPhone XS Max", "iPhone11,8": "iPhone XR", "iPhone12,1": "iPhone 11", "iPhone12,3": "iPhone 11 Pro",
    "iPhone12,5": "iPhone 11 Pro Max", "iPhone12,8": "iPhone SE (2nd gen)", "iPhone13,1": "iPhone 12 mini",
    "iPhone13,2": "iPhone 12", "iPhone13,3": "iPhone 12 Pro", "iPhone13,4": "iPhone 12 Pro Max",
    "iPhone14,4": "iPhone 13 mini", "iPhone14,5": "iPhone 13", "iPhone14,2": "iPhone 13 Pro",
    "iPhone14,3": "iPhone 13 Pro Max", "iPhone14,6": "iPhone SE (3rd gen)", "iPhone14,7": "iPhone 14",
    "iPhone14,8": "iPhone 14 Plus", "iPhone15,2": "iPhone 14 Pro", "iPhone15,3": "iPhone 14 Pro Max",
    "iPhone15,4": "iPhone 15", "iPhone15,5": "iPhone 15 Plus", "iPhone16,1": "iPhone 15 Pro",
    "iPhone16,2": "iPhone 15 Pro Max", "iPhone17,3": "iPhone 16", "iPhone17,4": "iPhone 16 Plus",
    "iPhone17,1": "iPhone 16 Pro", "iPhone17,2": "iPhone 16 Pro Max", "iPhone17,5": "iPhone 16e",
    "iPhone18,3": "iPhone 17", "iPhone18,1": "iPhone 17 Pro", "iPhone18,2": "iPhone 17 Pro Max",
    "iPhone18,4": "iPhone Air",
}

CARRIERS = {"52001": "AIS", "52003": "AIS", "52004": "TrueMove H", "52005": "dtac", "52018": "dtac", "52015": "NT", "52047": "NT"}


def marketing_name(product_type: str) -> str:
    return PRODUCT_NAMES.get(product_type, product_type)


def run(coro):
    """Run a coroutine from a worker thread (pywebview API calls run in threads)."""
    return asyncio.run(coro)


async def _list_devices() -> list[dict[str, Any]]:
    from pymobiledevice3 import usbmux
    from pymobiledevice3.exceptions import NotPairedError, PasswordRequiredError
    from pymobiledevice3.lockdown import create_using_usbmux

    out = []
    for dev in await usbmux.list_devices():
        if not dev.is_usb:
            continue
        entry = {"id": f"ios:{dev.serial}", "platform": "ios", "serial": dev.serial, "state": "ready",
                 "brand": "Apple", "model": "iPhone", "name": ""}
        try:
            lockdown = await create_using_usbmux(serial=dev.serial, autopair=False)
            try:
                entry["model"] = marketing_name(await lockdown.get_value(key="ProductType") or "")
                entry["name"] = await lockdown.get_value(key="DeviceName") or ""
                if not await lockdown.validate_pairing():
                    entry["state"] = "not_trusted"
            finally:
                await lockdown.close()
        except (NotPairedError,):
            entry["state"] = "not_trusted"
        except PasswordRequiredError:
            entry["state"] = "locked"
        except Exception:
            entry["state"] = "not_trusted"
        out.append(entry)
    return out


def list_devices() -> list[dict[str, Any]]:
    try:
        return run(_list_devices())
    except Exception:
        return []  # usbmuxd not running (Apple Mobile Device Service missing)


def usbmux_available() -> bool:
    async def probe():
        from pymobiledevice3 import usbmux

        await usbmux.list_devices()

    try:
        run(probe())
        return True
    except Exception:
        return False


async def connect(serial: str, pair_timeout: float = 60):
    """Open a lockdown session, pairing if needed (the user taps "Trust")."""
    from pymobiledevice3.lockdown import create_using_usbmux

    return await create_using_usbmux(serial=serial, autopair=True, pair_timeout=pair_timeout)


async def read_info(lockdown) -> tuple[DeviceInfo, list[SimCard], dict[str, Any]]:
    values: dict[str, Any] = await lockdown.get_value() or {}

    async def domain(name: str) -> dict[str, Any]:
        try:
            return await lockdown.get_value(domain=name) or {}
        except Exception:
            return {}

    battery = await domain("com.apple.mobile.battery")
    disk = await domain("com.apple.disk_usage")
    product_type = values.get("ProductType", "")
    info = DeviceInfo(
        platform="ios",
        serial=values.get("SerialNumber", "") or values.get("UniqueDeviceID", ""),
        brand="Apple",
        model=product_type,
        market_name=marketing_name(product_type),
        product=values.get("HardwareModel", ""),
        device_name=values.get("DeviceName", ""),
        os_version=values.get("ProductVersion", ""),
        build_id=values.get("BuildVersion", ""),
        cpu_abi=values.get("CPUArchitecture", ""),
        imei=values.get("InternationalMobileEquipmentIdentity", "") or "",
        imei2=values.get("InternationalMobileEquipmentIdentity2", "") or "",
        phone_number=normalize_phone(values.get("PhoneNumber", "")),
        timezone=values.get("TimeZone", ""),
        battery_level=battery.get("BatteryCurrentCapacity"),
        battery_status="charging" if battery.get("BatteryIsCharging") else "unplugged",
        storage_total=disk.get("TotalDiskCapacity"),
        storage_free=disk.get("AmountDataAvailable") or disk.get("TotalDataAvailable"),
        wifi_mac=values.get("WiFiAddress", ""),
        bluetooth_mac=values.get("BluetoothAddress", ""),
    )
    for key in ("UniqueDeviceID", "ModelNumber", "RegionInfo", "ActivationState", "MobileEquipmentIdentifier",
                "BasebandVersion", "FirmwareVersion", "PasswordProtected"):
        if values.get(key) not in (None, ""):
            info.extra[key] = str(values[key])

    sims: list[SimCard] = []
    bundles = values.get("CarrierBundleInfoArray") or []
    for i, b in enumerate(bundles):
        mccmnc = f"{b.get('MCC', '')}{b.get('MNC', '')}"
        sims.append(SimCard(
            slot=f"SIM {i + 1}",
            iccid=b.get("IntegratedCircuitCardIdentity", "") or "",
            imsi=b.get("InternationalMobileSubscriberIdentity", "") or "",
            carrier=CARRIERS.get(mccmnc, b.get("CFBundleIdentifier", "").split(".")[-1]),
            country="TH" if str(b.get("MCC", "")) == "520" else str(b.get("MCC", "")),
            active=True,
        ))
    if not sims and values.get("IntegratedCircuitCardIdentity"):
        imsi = values.get("InternationalMobileSubscriberIdentity", "") or ""
        sims.append(SimCard(slot="SIM 1", iccid=values["IntegratedCircuitCardIdentity"], imsi=imsi,
                            number=info.phone_number, carrier=CARRIERS.get(imsi[:5], ""), active=True))
    if sims and info.phone_number and not sims[0].number:
        sims[0].number = info.phone_number
    if sims:
        info.carrier = sims[0].carrier
    return info, sims, values


async def list_apps(lockdown) -> dict[str, dict[str, Any]]:
    from pymobiledevice3.services.installation_proxy import InstallationProxyService

    async with InstallationProxyService(lockdown=lockdown) as svc:
        return await svc.get_apps(application_type="User")
