# Phone Analysis v4

ระบบสกัดและวิเคราะห์พยานหลักฐานจากโทรศัพท์มือถือ **Android** และ **iPhone (iOS)** สำหรับ Windows
พร้อมหน้าจอใหม่ทั้งหมด รองรับภาษาไทย / English และโหมดสว่าง / มืด

![เชื่อมต่ออุปกรณ์](docs/screenshots/1-connect.jpg)

| | |
|---|---|
| ![ข้อมูลเครื่อง](docs/screenshots/3-device.jpg) | ![ประวัติการโทร](docs/screenshots/4-calls.jpg) |
| ![SMS](docs/screenshots/5-sms.jpg) | ![รูปภาพ](docs/screenshots/6-photos.jpg) |
| ![วินิจฉัยการเชื่อมต่อ](docs/screenshots/7-diagnostics.jpg) | ![iPhone โหมดมืด](docs/screenshots/8-iphone-dark.jpg) |

## ความสามารถ

| หมวด | Android (ADB, ไม่ต้อง root) | iPhone (backup) |
|---|---|---|
| ข้อมูลเครื่อง | ยี่ห้อ รุ่น Android build serial แบตเตอรี่ พื้นที่ บัญชี | รุ่น iOS serial IMEI เบอร์ แบตเตอรี่ พื้นที่ |
| ประวัติการโทร / รายชื่อ / SMS | `content query` ถ้าเครื่องปฏิเสธ ใช้แอปตัวช่วยชั่วคราว (Android 10+) | CallHistory, AddressBook, sms.db (รวม iMessage) |
| แชต | ต้อง root | WhatsApp, LINE (best-effort) |
| ประวัติเว็บ / บันทึก | ต้อง root / ไม่มีในระบบ | Safari, Apple Notes |
| บันทึกเสียง | ไฟล์จาก Recorder / MIUI / Call | Voice Memos |
| Wi-Fi / SIM | `cmd wifi`, siminfo (SIM ที่เคยใส่) | wifi plist, ICCID / IMSI |
| รูปภาพ | DCIM / Pictures พร้อม EXIF + GPS | Camera Roll พร้อม EXIF + GPS (รวม HEIC) |
| แอป | `dumpsys package` | installation_proxy |

* **รายงาน**: Excel (ทุกหมวด + ค่าแฮช), PDF ภาษาไทย (ฟอนต์ Sarabun), รูปภาพเป็น Word (พร้อมวันที่ถ่าย พิกัด SHA-256)
* **คดี**: ทุกการสกัดถูกเก็บในโฟลเดอร์คดี (`Documents\Phone Analysis Cases`) พร้อม SQLite, `manifest.json` (SHA-256 ทุกไฟล์) และ `audit.log` บันทึกทุกคำสั่งที่ส่งไปยังเครื่อง
* **วินิจฉัยการเชื่อมต่อ**: ภาพเคลื่อนไหวสอนเปิด USB debugging แยกตามยี่ห้อ (Samsung, Xiaomi, OPPO, realme, vivo, HUAWEI, HONOR, Pixel) และ iPhone พร้อมตรวจสถานะ ADB / ไดรเวอร์ / Apple Mobile Device Service จริง
* **โหมดสาธิต**: อุปกรณ์จำลอง Android และ iPhone พร้อมข้อมูลภาษาไทยสังเคราะห์ ใช้ฝึกอบรมหรือทดสอบได้โดยไม่ต้องมีเครื่องจริง (`--demo` หรือเมนู เพิ่มเติม → โหมดสาธิต)
* รอบถัดไป: ไทม์ไลน์ ส่งออก i2 ผังความเชื่อมโยง เชื่อมโยงข้ามเครื่อง วิเคราะห์ CDR ฐานข้อมูลเบอร์โทร (ปุ่มแสดง “เร็ว ๆ นี้”)

## หลักการด้านพยานหลักฐาน

* ใช้กับอุปกรณ์ที่ได้รับอนุญาตตามกฎหมายเท่านั้น และเป็นการสกัดเชิงตรรกะ (logical) ที่เครื่องต้องปลดล็อก / อนุญาต USB debugging / กด “เชื่อถือ”
* ไฟล์ทุกไฟล์ที่ได้มาจะถูกคำนวณ SHA-256 ทันที และเก็บแยก ข้อมูลดิบ (`raw/`) กับข้อมูลที่ parse แล้ว
* **แอปตัวช่วย Android** และ **รหัส backup ชั่วคราวของ iPhone** จะใช้เมื่อผู้ตรวจเปิดตัวเลือกเท่านั้น ทุกขั้นตอนถูกบันทึก และคืนสภาพเครื่องทันทีหลังใช้ (ถอนการติดตั้งแอป / ปลดรหัส backup)
* ข้อมูลที่ระบบไม่อนุญาตให้อ่าน (เช่น IMEI บน Android 10+, แชต LINE บน Android) จะแสดงเหตุผลชัดเจน ไม่แสดงเป็นค่าว่าง

## ติดตั้งบนเครื่อง Windows

ดาวน์โหลดไฟล์ที่ build แล้วจาก GitHub Actions (artifact `Phone-Analysis-windows`) แล้วเปิด `Phone Analysis.exe`

* **Android**: ไม่ต้องติดตั้งเพิ่ม (มี adb ในตัว) หากเครื่องไม่ขึ้น ให้ติดตั้งไดรเวอร์ USB ของยี่ห้อนั้น
* **iPhone**: ติดตั้ง **Apple Devices** (Microsoft Store) หรือ **iTunes** เพื่อให้มี Apple Mobile Device Service
* ต้องมี Microsoft Edge WebView2 Runtime (มีอยู่แล้วใน Windows 10/11)

หรือ build เองบน Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

## พัฒนา (Development)

```bash
uv venv && . .venv/bin/activate          # หรือ python -m venv .venv
pip install -e ".[dev]"
cd frontend && npm ci && cd ..
```

รันแบบหน้าต่างโปรแกรม (pywebview):

```bash
cd frontend && npm run build && cd ..
python -m spni --demo
```

รันใน browser (hot reload) — เปิด 2 terminal:

```bash
python -m spni.devserver --demo
```

```bash
cd frontend && npm run dev
```

แล้วเปิด http://localhost:5173

ทดสอบ:

```bash
pytest
```

```bash
cd frontend && npm run build
```

## โครงสร้าง

```
spni/              Python backend
  api.py           API ที่หน้าจอเรียก (pywebview js_api / devserver)
  android/         ADB, content query parser, ข้อมูลเครื่อง, แอปตัวช่วย
  ios/             usbmux/lockdown, backup (เข้ารหัสชั่วคราว), parsers
  case/store.py    โฟลเดอร์คดี + SQLite + SHA-256 + audit log
  export/          Excel / PDF / Word
  demo.py          อุปกรณ์จำลอง
frontend/          React 19 + TypeScript + Tailwind 4 (Vite)
android-agent/     แอปตัวช่วย Android (Kotlin) — build ใน GitHub Actions
resources/         ฟอนต์ Sarabun (OFL), ไอคอน
spni.spec          PyInstaller
```

---

## English summary

Phone Analysis v4 is a Windows desktop tool (Python + pywebview + React) for logical extraction of
Android phones over ADB and iPhones through iTunes-format backups. It stores every extraction in a case
folder with SHA-256 hashes and an audit log of every command sent to the device, and exports Excel, Thai
PDF and photos-to-Word reports. An animated, brand-specific connection guide helps examiners enable USB
debugging. Demo devices with synthetic Thai data allow training without a phone. Run `python -m spni --demo`
after building the UI, or see *Development* above. The GitHub Actions workflow runs the tests, builds the
Android helper app and produces the Windows build.
