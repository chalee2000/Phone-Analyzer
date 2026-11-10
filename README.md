# Phone Analysis v4

ระบบสกัดและวิเคราะห์พยานหลักฐานจากโทรศัพท์มือถือ **Android** และ **iPhone (iOS)** สำหรับ Windows
พร้อมหน้าจอใหม่ทั้งหมด รองรับภาษาไทย / English และโหมดสว่าง / มืด

![เชื่อมต่ออุปกรณ์](docs/screenshots/1-connect.jpg)

| | |
|---|---|
| ![ข้อมูลเครื่อง](docs/screenshots/3-device.jpg) | ![ประวัติการโทร](docs/screenshots/4-calls.jpg) |
| ![SMS](docs/screenshots/5-sms.jpg) | ![รูปภาพ](docs/screenshots/6-photos.jpg) |
| ![วินิจฉัยการเชื่อมต่อ](docs/screenshots/7-diagnostics.jpg) | ![iPhone โหมดมืด](docs/screenshots/8-iphone-dark.jpg) |

**วิเคราะห์และรายงาน**

| | |
|---|---|
| ![ผังความเชื่อมโยงเครือข่าย](docs/screenshots/10-network.jpg) | ![ไทม์ไลน์เหตุการณ์](docs/screenshots/11-timeline.jpg) |
| ![วิเคราะห์การติดต่อและ CDR](docs/screenshots/12-comms.jpg) | ![สร้างรายงาน](docs/screenshots/13-report.jpg) |
| ![ชุดข้อมูลของรายงาน](docs/screenshots/14-report-dataset.jpg) | ![รายงานเสร็จพร้อมค่าแฮช](docs/screenshots/15-report-done.jpg) |

![ตัวอย่างรายงาน PDF](docs/screenshots/16-report-pdf.jpg)

**นำเข้าข้อความ Messenger**

| | |
|---|---|
| ![นำเข้า Messenger](docs/screenshots/17-messenger-import.jpg) | ![แชต Messenger](docs/screenshots/18-messenger-chats.jpg) |

**แชต LINE จาก iPhone พร้อมรูป**

![แชต LINE พร้อมรูป](docs/screenshots/19-line-chats.jpg)

## ความสามารถ

| หมวด | Android (ADB, ไม่ต้อง root) | iPhone (backup) |
|---|---|---|
| ข้อมูลเครื่อง | ยี่ห้อ รุ่น Android build serial แบตเตอรี่ พื้นที่ บัญชี | รุ่น iOS serial IMEI เบอร์ แบตเตอรี่ พื้นที่ |
| ประวัติการโทร / รายชื่อ / SMS | `content query` ถ้าเครื่องปฏิเสธ ใช้แอปตัวช่วยชั่วคราว (Android 10+) | CallHistory, AddressBook, sms.db (รวม iMessage) |
| แชต | ต้อง root (Messenger: นำเข้าจากไฟล์ Facebook ด้านล่าง) | WhatsApp, LINE (ข้อความทุกประเภท + รูป / วิดีโอ / เสียงที่อยู่ในเครื่อง) |
| ประวัติเว็บ / บันทึก | ต้อง root / ไม่มีในระบบ | Safari, Apple Notes |
| บันทึกเสียง | ไฟล์จาก Recorder / MIUI / Call | Voice Memos |
| Wi-Fi / SIM | `cmd wifi`, siminfo (SIM ที่เคยใส่) | wifi plist, ICCID / IMSI |
| รูปภาพ | DCIM / Pictures พร้อม EXIF + GPS | Camera Roll พร้อม EXIF + GPS (รวม HEIC) |
| แอป | `dumpsys package` | installation_proxy |

* **ส่งออกด่วน**: Excel (ทุกหมวด + ค่าแฮช), รูปภาพเป็น Word (พร้อมวันที่ถ่าย พิกัด SHA-256)
* **คดี**: ทุกการสกัดถูกเก็บในโฟลเดอร์คดี (`Documents\Phone Analysis Cases`) พร้อม SQLite, `manifest.json` (SHA-256 ทุกไฟล์) และ `audit.log` บันทึกทุกคำสั่งที่ส่งไปยังเครื่อง
* **วินิจฉัยการเชื่อมต่อ**: ภาพเคลื่อนไหวสอนเปิด USB debugging แยกตามยี่ห้อ (Samsung, Xiaomi, OPPO, realme, vivo, HUAWEI, HONOR, Pixel) และ iPhone พร้อมตรวจสถานะ ADB / ไดรเวอร์ / Apple Mobile Device Service จริง
* **โหมดสาธิต**: อุปกรณ์จำลอง Android และ iPhone พร้อมข้อมูลภาษาไทยสังเคราะห์ ใช้ฝึกอบรมหรือทดสอบได้โดยไม่ต้องมีเครื่องจริง (`--demo` หรือเมนู เพิ่มเติม → โหมดสาธิต)

### วิเคราะห์ (ทุกเครื่องในคดีเดียวกัน)

* **ผังความเชื่อมโยงเครือข่าย** (แท็บ เครือข่าย): บุคคล เบอร์โทร ห้องแชต Wi-Fi สถานที่ บัญชี จากทุกเครื่อง + CDR, ไฮไลต์ผู้ที่พบในหลายเครื่อง, จัดกลุ่ม (Louvain), ตัวชี้วัด degree / betweenness, หาเส้นทาง, เพิ่มบุคคล/ยานพาหนะ/บัญชีธนาคารและเส้นเชื่อมเอง, บันทึกผัง, ส่งออก **i2 Analyst's Notebook (.anx)**, GraphML, Excel, PNG
* **ไทม์ไลน์เหตุการณ์** (แท็บ ไทม์ไลน์): 4 ช่อง บุคคล / วัตถุ / สถานที่ / เหตุการณ์, กราฟภาพรวมรายวัน, กรองตามเครื่องและหมวด, ทำเครื่องหมายเหตุการณ์สำคัญ, ผู้ตรวจเพิ่มเหตุการณ์เอง, ส่งออก Excel / PDF
* **วิเคราะห์การติดต่อ + CDR** (แท็บ วิเคราะห์การติดต่อ): คิวรีสำเร็จรูป (กลางคืน สายไม่ได้รับ สายสั้น/ยาว เบอร์ไม่บันทึกชื่อ พบหลายเครื่อง ฯลฯ), แผนที่ย้อนเหตุการณ์พร้อมพัดเสาสัญญาณตามทิศ (แผนที่ขอบเขตจังหวัดแบบออฟไลน์ หรือ OSM), โปรไฟล์ผู้ติดต่อพร้อม heatmap วัน × ชั่วโมง, นำเข้า CDR (CSV / Excel หัวคอลัมน์ไทยหรืออังกฤษ ปี พ.ศ. ได้)

### LINE บน iPhone (จาก backup)

* ข้อความทุกประเภท: ข้อความ, รูป, วิดีโอ, ข้อความเสียง (พร้อมความยาว), การโทร / วิดีโอคอล (พร้อมระยะเวลา), สติกเกอร์, ผู้ติดต่อ, ไฟล์, ตำแหน่ง (พร้อมพิกัด)
* ชื่อห้องถูกต้อง: แชตส่วนตัวใช้ชื่อที่บันทึกไว้, กลุ่มใช้ชื่อกลุ่ม, ห้องหลายคนใช้ชื่อคนในห้อง
* อ่านไฟล์ `-wal` ของฐานข้อมูลด้วย จึงได้ข้อความล่าสุดที่ยังไม่ถูกเขียนลงไฟล์หลัก
* รูป วิดีโอ และเสียงที่อยู่ใน `Message Attachments` ถูกคัดลอกเข้าคดีพร้อม SHA-256 แสดงในฟองแชต และรูปเข้าแท็บรูปภาพแยกอัลบั้ม `LINE: <ห้อง>`
* ข้อจำกัด: ได้เฉพาะสื่อที่เคยเปิดหรือดาวน์โหลดบนเครื่อง (ข้อความอื่นยังมีป้าย เช่น [รูปภาพ]); ต้องเป็น backup ที่มีข้อมูล LINE; Android ยังต้อง root

### นำเข้าข้อความ Messenger (แท็บ แชต → นำเข้า Messenger)

Messenger เก็บข้อความในพื้นที่ส่วนตัวของแอป จึงดึงจากเครื่องที่ไม่ได้ root ไม่ได้ ให้นำเข้าจากไฟล์ที่ดาวน์โหลดจากบัญชีแทน:

* **ดาวน์โหลดข้อมูลของคุณ (Facebook)**: ศูนย์บัญชี → ข้อมูลและการอนุญาตของคุณ → ดาวน์โหลดข้อมูลของคุณ → เลือก "ข้อความ" รูปแบบ **JSON** — เลือก zip ทุกส่วนพร้อมกันได้ หรือเลือกไฟล์ `.json` / โฟลเดอร์ที่แตกแล้ว
* **แชตเข้ารหัส (E2EE)**: ในแอป Messenger → การตั้งค่า → ความเป็นส่วนตัวและความปลอดภัย → แชตที่เข้ารหัสตั้งแต่ต้นทางถึงปลายทาง → พื้นที่จัดเก็บข้อความ → ดาวน์โหลดข้อมูลที่จัดเก็บแบบปลอดภัย
* แก้ภาษาไทยที่เพี้ยนในไฟล์ของ Facebook อัตโนมัติ, หาเจ้าของบัญชีให้ (เปลี่ยนได้), รวมไฟล์หลายส่วนและตัดข้อความซ้ำ
* ได้ข้อความ การโทร ข้อความที่ยกเลิกการส่ง สติกเกอร์ ลิงก์ ไฟล์แนบ reaction และคำขอข้อความ; รูปที่แนบเข้าแท็บรูปภาพพร้อมภาพย่อ
* ค่า SHA-256 ของไฟล์ต้นทางบันทึกใน audit log, ไฟล์ข้อความ JSON และสื่อที่อ้างถึงถูกคัดลอกเข้าคดีพร้อมค่าแฮช
* ทุกการนำเข้าเป็นแหล่งข้อมูลหนึ่งในคดี จึงเข้าผังเครือข่าย ไทม์ไลน์ วิเคราะห์การติดต่อ และรายงานโดยอัตโนมัติ
* มีปุ่ม "ไฟล์ตัวอย่าง" ไว้ฝึกใช้งาน

### รายงานผลการตรวจพิสูจน์ (ปุ่ม PDF / รายงานคดี)

หน้าต่างสร้างรายงาน 6 ขั้น: **ทั่วไป → ข้อมูลคดี → ชุดข้อมูล → ความปลอดภัย → รูปแบบ → สรุป**

* รูปแบบ: **PDF** (ปก สารบัญพร้อม bookmark เลขหน้า "หน้า X / Y" ผังเครือข่าย รูปย่อ ค่าแฮช audit log ช่องลงนาม), **Word** (แก้ไขต่อได้), **Excel**, **HTML** ไฟล์เดียว (ค้นหา / เรียงตารางได้), **แพ็กเกจ ZIP** (PDF + Excel + HTML + `manifest.json` + `SHA256SUMS.txt`)
* ข้อมูลคดี: เลขคดี ชื่อคดี ประเภทความผิด เลขของกลาง ผู้ตรวจพิสูจน์ พนักงานสอบสวน หน่วยงาน สังกัด สถานที่ตรวจ หมายเหตุ — บันทึกไว้กับคดีอัตโนมัติ
* ชุดข้อมูล: เลือกเครื่อง หมวด ช่วงวันที่ และส่วนวิเคราะห์ (ผังความเชื่อมโยง ความเชื่อมโยงข้ามเครื่อง ผู้ติดต่อบ่อย Top N เหตุการณ์ที่ทำเครื่องหมาย)
* ความปลอดภัย: รหัสผ่าน PDF (ห้ามคัดลอก / แก้ไข), ชั้นความลับ ปกปิด / ลับ / ลับมาก / ลับที่สุด (แถบสีแดงทุกหน้า + ลายน้ำ), ไฟล์ `.sha256` และบันทึกค่า SHA-256 ของรายงานลง audit log ของคดีทุกครั้ง
* รูปแบบ: ไทย / English, ปี พ.ศ. / ค.ศ., เรียงใหม่ → เก่า หรือ เก่า → ใหม่, แนวนอน / แนวตั้ง, จำกัดจำนวนแถวต่อหมวด

ยังไม่มี (ปุ่มแสดง “เร็ว ๆ นี้”): เปิด LINK, ฐานข้อมูลเบอร์โทร

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
  case/workspace.py  งานวิเคราะห์ของผู้ตรวจ (บันทึกบนผัง, รายการไทม์ไลน์, bookmark, ผังที่บันทึก)
  analysis/        ผังเครือข่าย (networkx), ไทม์ไลน์, การติดต่อ
  cdr.py           นำเข้า CDR (CSV / Excel)
  messenger.py     นำเข้า Messenger จากไฟล์ Facebook (Download Your Information / E2EE)
  export/          Excel / PDF / Word แบบด่วน, i2 ANX / GraphML
  report/          รายงานผลการตรวจพิสูจน์ (PDF / Word / Excel / HTML / ZIP)
  demo.py          อุปกรณ์จำลอง + CDR ตัวอย่าง
frontend/          React 19 + TypeScript + Tailwind 4 (Vite)
android-agent/     แอปตัวช่วย Android (Kotlin) — build ใน GitHub Actions
resources/         ฟอนต์ Sarabun (OFL), ไอคอน
spni.spec          PyInstaller
```

---

## English summary

Phone Analysis v4 is a Windows desktop tool (Python + pywebview + React) for logical extraction of
Android phones over ADB and iPhones through iTunes-format backups. It stores every extraction in a case
folder with SHA-256 hashes and an audit log of every command sent to the device. Across all devices in a
case it offers a link chart (cross-device entities, communities, i2 ANX / GraphML export), a swimlane event
timeline, and call & contact analysis with CDR import and a playback map of cell-site sectors. A six-step
report wizard produces forensic reports as PDF (password, classification banner and watermark, contents,
link chart, hashes, audit log, signature block), Word, Excel, searchable HTML or a ZIP package with a
manifest and SHA256SUMS; every report's hash is written to the case audit log. An animated, brand-specific
connection guide helps examiners enable USB debugging. Facebook Messenger chats, which a phone without root cannot
expose, are imported from the account's "Download Your Information" JSON export and the secure-storage download of
end-to-end encrypted chats, with Thai text repaired, attached photos, and the source files' SHA-256 in the audit log. Demo devices with synthetic Thai data allow training without a phone. Run `python -m spni --demo`
after building the UI, or see *Development* above. The GitHub Actions workflow runs the tests, builds the
Android helper app and produces the Windows build.
