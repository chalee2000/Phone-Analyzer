"""Connection diagnostics: reading Windows tool output and the iPhone checklist."""

from spni import diagnostics

RUNNING = """
SERVICE_NAME: Apple Mobile Device Service
        TYPE               : 10  WIN32_OWN_PROCESS
        STATE              : 4  RUNNING
                                (STOPPABLE, NOT_PAUSABLE, IGNORES_SHUTDOWN)
        WIN32_EXIT_CODE    : 0  (0x0)
"""
STOPPED_TRANSLATED = """
SERVICE_NAME: Apple Mobile Device Service
        TYP                : 10  WIN32_OWN_PROCESS
        STATUS             : 1  STOPPED
"""
MISSING = "[SC] EnumQueryServicesStatus:OpenService FAILED 1060:\n\nThe specified service does not exist as an installed service.\n"
PNP_APPLE = r"""Instance ID:                USB\VID_05AC&PID_12A8\00008110001A2B3C4D5E
Device Description:         Apple Mobile Device USB Composite Device
Instance ID:                USB\VID_046D&PID_C52B\5&2B1D4A3C&0&2
"""
PNP_OTHER = r"""Instance ID:                USB\VID_046D&PID_C52B\5&2B1D4A3C&0&2
Device Description:         USB Composite Device
"""


def test_service_states_from_sc_output():
    assert diagnostics.apple_service_state(RUNNING) == "running"
    assert diagnostics.apple_service_state(STOPPED_TRANSLATED) == "stopped"  # the label is translated, the state is not
    assert diagnostics.apple_service_state(MISSING) == "missing"
    assert diagnostics.apple_service_state("") == "unknown"


def test_apple_usb_from_pnputil():
    assert diagnostics.apple_usb_seen(PNP_APPLE) is True
    assert diagnostics.apple_usb_seen(PNP_OTHER) is False
    assert diagnostics.apple_usb_seen("Microsoft PnP Utility\nInvalid option /connected") is None  # old Windows


def _ios(monkeypatch, outputs, usbmux=False):
    from spni.ios import device

    monkeypatch.setattr(diagnostics.sys, "platform", "win32")
    monkeypatch.setattr(diagnostics, "_run", lambda cmd, timeout=8: outputs.get(cmd[0] + ":" + cmd[-1], ""))
    monkeypatch.setattr(device, "usbmux_available", lambda: usbmux)
    monkeypatch.setattr(device, "list_devices", lambda: [])
    return {c["id"]: c for c in diagnostics.ios_checks()}


def test_ios_checklist_offers_the_right_fix(monkeypatch):
    stopped = _ios(monkeypatch, {"pnputil:/connected": PNP_APPLE, "sc:Apple Mobile Device Service": STOPPED_TRANSLATED})
    assert stopped["apple_usb"]["status"] == "ok"
    assert stopped["apple_service_stopped"]["fix"] == "start_apple_service"
    assert stopped["usbmux"]["status"] == "fail"

    missing = _ios(monkeypatch, {"pnputil:/connected": PNP_OTHER, "sc:Apple Mobile Device Service": MISSING,
                                 "sc:AppleMobileDeviceService": MISSING})
    assert missing["apple_usb_missing"]["status"] == "fail"  # Windows does not see the iPhone on the cable
    assert missing["apple_service_missing"]["fix"] == "install_apple_devices"

    store_name = _ios(monkeypatch, {"sc:Apple Mobile Device Service": MISSING, "sc:AppleMobileDeviceService": RUNNING}, usbmux=True)
    assert store_name["apple_service"]["status"] == "ok" and store_name["apple_service"]["detail"] == "AppleMobileDeviceService"
    assert "apple_usb" not in store_name and "apple_usb_missing" not in store_name  # pnputil gave nothing: no claim
