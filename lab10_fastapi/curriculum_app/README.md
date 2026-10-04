# Curriculum Application

แอปนี้รับคำถาม → ให้ Qwen สร้าง SQL → อ่าน SQLite → ส่งกลับทั้งคำตอบ, SQL และ rows

## เอาไฟล์ไปวางที่ไหน

วางโฟลเดอร์ `curriculum_app` ไว้ภายใน `ocr_system/lab10_fastapi/` และรักษาโครงสร้างนี้:

```text
ocr_system/
├── lab10_fastapi/
│   ├── __init__.py
│   └── curriculum_app/       ← ไฟล์ Lab 10 ของกลุ่มนี้
├── src/ocr_system/
│   └── lab8b_curriculum_db.py ← โค้ด Lab 8B
└── work/lab8b_run/
    └── curriculum.db            ← ฐานข้อมูล
```

ห้ามย้าย `main.py` ออกจาก `curriculum_app` และให้รันคำสั่งจากโฟลเดอร์ `ocr_system`

ให้รันจากรากโปรเจกต์ `ocr_system` ใน VS Code Terminal:

```bash
python -m pip install -r lab10_fastapi/curriculum_app/requirements.txt
ollama pull qwen3:4b
python -m uvicorn lab10_fastapi.curriculum_app.main:app --reload --port 8000
```

เปิด [http://127.0.0.1:8000/](http://127.0.0.1:8000/) หรือ [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

ก่อนรันต้องมี:

- `lab10_fastapi/curriculum_app/.env`
- `work/lab8b_run/curriculum.db`
- `src/ocr_system/lab8b_curriculum_db.py`

ถ้าแจกเฉพาะกลุ่ม Curriculum ให้ก็อปโฟลเดอร์นี้ พร้อม Lab 8B และไฟล์ DB ตามตำแหน่งข้างต้น

---

## Lab 11: Front-End Development & API Contract

ตามข้อกำหนดของ Lab 11 ส่วนติดต่อผู้ใช้ (Frontend) ถูกแยกไฟล์ตามมาตรฐาน Best Practices และมีการกำหนดสัญญาเชื่อมต่อ API (API Contract) พร้อมรองรับ 4 สถานะของระบบ AI อย่างสมบูรณ์:

### 1. โครงสร้างไฟล์ Frontend (แยกตาม Best Practice)
```text
curriculum_app/static/
├── index.html   # โครงสร้างหน้าเว็บหลัก โหลด external CSS & JS
├── style.css    # ออกแบบและจัดรูปแบบเลย์เอาต์, ฟอนต์ Google Sans/Kanit, 4 สถานะ UI
└── app.js       # ควบคุมตรรกะ, จัดการ Event, async fetch และ 4 สถานะ UI
```

### 2. การควบคุมสถานะหน้าเว็บ 4 สถานะ (AI UI 4 States)
ตามหลักการออกแบบ UX ของระบบ AI ใน Lab 11 หน้าเว็บรองรับสถานะดังนี้:
1. **Idle (พร้อมใช้งาน)**:
   - แสดงข้อความแนะนำวิธีใช้งาน และปุ่มชิปตัวอย่างคำถามที่สามารถคลิกเพื่อกรอกอัตโนมัติ
   - ปุ่มส่งคำถามพร้อมใช้งาน
2. **Loading (รอโมเดลประมวลผล)**:
   - แสดง Spinner แบบหมุนนุ่มนวล พร้อมข้อความแจ้งสถานะว่ากำลังแปลง SQL และอ่าน SQLite
   - ปิดปุ่ม (disabled) เพื่อป้องกันไม่ให้ผู้ใช้กดส่งซ้ำขณะกำลังรอคำตอบ
3. **Success (ประมวลผลสำเร็จ)**:
   - แสดงผลลัพธ์คำตอบภาษาธรรมชาติจาก AI พร้อม Badge สีเขียว `Success`
   - ปลอดภัยจาก XSS ด้วยการเรนเดอร์ข้อความผ่าน `textContent`
   - มี Collapsible ส่วนแสดงคำสั่ง SQL ที่ใช้ และผลลัพธ์ Rows ที่ดึงมาจากฐานข้อมูลจริง
4. **Error (เกิดข้อผิดพลาด)**:
   - แสดงกล่องแจ้งเตือนสีแดง พร้อม Badge สีแดง `Error`
   - ระบุสาเหตุของข้อผิดพลาดชัดเจน และแสดงข้อความคำแนะนำสิ่งที่ผู้ใช้ควรทำต่อไป (Actionable advice)

---

### 3. API Contract Specification (สัญญาข้อตกลงการเชื่อมต่อ API)

ตกลง 5 องค์ประกอบหลักตามมาตรฐานสไลด์ Lab 11:

#### 3.1 Endpoint: ถาม-ตอบข้อมูลหลักสูตร (Text-to-SQL AI)
- **Endpoint**: `/api/ask`
- **Method**: `POST`
- **Request Headers**: `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "question": "หลักสูตรนี้มีหน่วยกิตรวมทั้งหมดเท่าไร"
  }
  ```
  | Field | Type | Required | Description |
  | :--- | :--- | :---: | :--- |
  | `question` | string | Yes | ข้อความคำถามภาษาธรรมชาติ เช่น ถามหน่วยกิต รายวิชา หรือเงื่อนไข |

- **Response: สำเร็จ (200 OK)**:
  ```json
  {
    "question": "หลักสูตรนี้มีหน่วยกิตรวมทั้งหมดเท่าไร",
    "sql": "SELECT total_credits FROM programs WHERE id = 'BIT';",
    "rows": [
      {
        "total_credits": 128
      }
    ],
    "answer": "หลักสูตรนี้มีหน่วยกิตรวมทั้งหมด 128 หน่วยกิต"
  }
  ```
  | Field | Type | Description |
  | :--- | :--- | :--- |
  | `question` | string | คำถามเดิมที่ส่งเข้ามา |
  | `sql` | string | คำสั่ง SQL ที่โมเดล Qwen3 สร้างขึ้น |
  | `rows` | array[object] | ข้อมูลดิบที่ได้จากการคิวรี SQLite แบบ read-only |
  | `answer` | string | คำตอบภาษาธรรมชาติที่โมเดลสรุปจาก rows |

- **Response: ข้อผิดพลาด (Error)**:
  ```json
  {
    "detail": "ติดต่อ Ollama ไม่ได้"
  }
  ```
  | HTTP Status | เหตุการณ์ | วิธีแก้ไข / สิ่งที่ผู้ใช้ต้องทำ |
  | :--- | :--- | :--- |
  | `422 Unprocessable Entity` | คำถามไม่สามารถแปลงเป็น SQL ที่ถูกต้องได้ หรือคิวรีผิดพลาด | ปรับปรุงคำถามให้กระชับและเจาะจงขึ้น |
  | `503 Service Unavailable` | ไม่พบไฟล์ `curriculum.db` หรือติดต่อ Ollama `qwen3:4b` ไม่ได้ | ตรวจสอบว่าได้รัน Ollama หรือตรวจสอบสถานะที่ `/api/health` |

---

#### 3.2 Endpoint: ตรวจสอบเงื่อนไขวิชาบังคับก่อน (Prerequisite Graph)
- **Endpoint**: `/api/courses/{code}/prerequisites`
- **Method**: `GET`
- **Path Parameter**:
  | Parameter | Type | Required | Description |
  | :--- | :--- | :---: | :--- |
  | `code` | string (8 digits) | Yes | รหัสวิชา 8 หลัก เช่น `06026201` |

- **Response: สำเร็จ (200 OK)**:
  ```json
  {
    "code": "06026201",
    "name_th": "การเขียนโปรแกรมเชิงวัตถุ",
    "name_en": "Object-Oriented Programming",
    "credits": 3,
    "requires": [
      {
        "code": "06026200",
        "name_th": "การเขียนโปรแกรมคอมพิวเตอร์เบื้องต้น",
        "name_en": "Computer Programming Fundamentals",
        "credits": 3,
        "kind": "pre"
      }
    ],
    "required_by": [
      {
        "code": "06026205",
        "name_th": "โครงสร้างข้อมูลและขั้นตอนวิธี",
        "name_en": "Data Structures and Algorithms",
        "credits": 3,
        "kind": "pre"
      }
    ]
  }
  ```

- **Response: ข้อผิดพลาด (404 Not Found)**:
  ```json
  {
    "detail": "ไม่พบข้อมูลรายวิชา 00000000"
  }
  ```

---

#### 3.3 Endpoint: ตรวจสอบความพร้อมของระบบ (Health Check)
- **Endpoint**: `/api/health`
- **Method**: `GET`
- **Response: 200 OK**:
  ```json
  {
    "status": "ok",
    "database": "work/lab8b_run/curriculum.db",
    "database_ready": true,
    "model": "qwen3:4b",
    "ollama_ready": true,
    "lab8b_module": "/.../src/ocr_system/lab8b_curriculum_db.py"
  }
  ```

---

## คำถามที่พบบ่อย

### เปิดเว็บแล้วขึ้น `ERR_CONNECTION_REFUSED`

FastAPI ยังไม่ได้รัน ให้รันคำสั่ง Uvicorn ด้านบนและเปิด Terminal ค้างไว้

### ขึ้น `No module named fastapi`

ยังไม่ได้ activate venv หรือยังไม่ได้ติดตั้ง `requirements.txt`

### ขึ้น `ไม่พบฐานข้อมูล`

ตรวจว่ามี `work/lab8b_run/curriculum.db` และค่า `CURRICULUM_DB_PATH` ใน `.env` ถูกต้อง

### เปิดหน้าเว็บได้แต่ถามไม่ได้

เปิด `/api/health` แล้วตรวจว่า `database_ready` และ `ollama_ready` เป็น `true`
