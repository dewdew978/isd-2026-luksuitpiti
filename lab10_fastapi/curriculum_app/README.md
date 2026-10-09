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
├── index.html   # หน้าหลัก AI Assistant โหลด external CSS & JS
├── style.css    # ออกแบบและจัดรูปแบบเลย์เอาต์, ฟอนต์ Google Sans/Kanit, 4 สถานะ UI
├── app.js       # ควบคุมตรรกะ AI Chat, จัดการ Event, async fetch และ 4 สถานะ UI
├── courses.html # หน้าแคตตาล็อกรายวิชา (263 วิชา), แผนการศึกษา และข้อบังคับ สจล.
└── courses.js   # ควบคุมตรรกะค้นหา/กรองวิชา, แผนการศึกษา, วิชาบังคับก่อน และข้อบังคับ
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

ระบบกำหนดสัญญาเชื่อมต่อ API ครบถ้วนตามมาตรฐาน RESTful และสอดคล้องกับสถาปัตยกรรม Relational Database (Option 2 Full Separation):

---

#### 3.1 Endpoint: ถาม-ตอบข้อมูลหลักสูตร (Text-to-SQL AI)
- **Endpoint**: `/api/ask`
- **Method**: `POST`
- **Request Headers**: `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "question": "หลักสูตร IT มีกี่หน่วยกิต"
  }
  ```
  | Field | Type | Required | Description |
  | :--- | :--- | :---: | :--- |
  | `question` | string | Yes | ข้อความคำถามภาษาธรรมชาติ (ความยาว 2–500 ตัวอักษร) |

- **Response: สำเร็จ (200 OK)**:
  ```json
  {
    "question": "หลักสูตร IT มีกี่หน่วยกิต",
    "sql": "SELECT total_credits FROM program WHERE program_id LIKE 'IT%' LIMIT 1",
    "rows": [
      {
        "total_credits": 129
      }
    ],
    "answer": "หลักสูตร IT มีหน่วยกิตรวมทั้งหมด 129 หน่วยกิต",
    "sources": [
      {
        "type": "program",
        "title": "เล่มหลักสูตร",
        "printed_pages": "หมวดที่ 3",
        "pdf_pages": null
      }
    ]
  }
  ```
  | Field | Type | Description |
  | :--- | :--- | :--- |
  | `question` | string | คำถามเดิมที่ส่งเข้ามา |
  | `sql` | string | คำสั่ง SQL ที่โมเดล Qwen3 สร้างขึ้น |
  | `rows` | array[object] | ข้อมูลดิบที่ได้จากการคิวรี SQLite แบบ read-only |
  | `answer` | string | คำตอบภาษาธรรมชาติที่โมเดลสังเคราะห์จาก rows โดยปราศจาก Hallucination |
  | `sources` | array[object] | แหล่งอ้างอิงหลักฐาน (เลขหน้า มคอ.2, เลขข้อบังคับ, หมวดหลักสูตร) |

- **Response: ข้อผิดพลาด (Error)**:
  | HTTP Status | เหตุการณ์ | รูปแบบ Response | วิธีแก้ไข / สิ่งที่ผู้ใช้ต้องทำ |
  | :--- | :--- | :--- | :--- |
  | `422 Unprocessable Entity` | คำถามไม่สามารถแปลงเป็น SQL ที่ถูกต้อง หรือคิวรีขัดข้อง | `{"detail": "ข้อความอธิบายความผิดพลาด"}` | ปรับปรุงคำถามให้กระชับและเจาะจงขึ้น |
  | `503 Service Unavailable` | ไม่พบไฟล์ `curriculum.db` หรือติดต่อ Ollama `qwen3:4b` ไม่ได้ | `{"detail": "ติดต่อ Ollama ไม่ได้"}` | ตรวจสอบสถานะ Ollama หรือเช็คที่ `/api/health` |

---

#### 3.2 Endpoint: รายการรายวิชาและค้นหา (Course Catalog & Search)
- **Endpoint**: `/api/courses`
- **Method**: `GET`
- **Query Parameters**:
  | Parameter | Type | Required | Description |
  | :--- | :--- | :---: | :--- |
  | `search` | string | No | คำค้นหารหัสวิชา หรือชื่อวิชาไทย/อังกฤษ |
  | `program_id` | string | No | รหัสสาขาวิชา เช่น `DSBA`, `BIT`, `IT`, `AIT` |
  | `limit` | integer | No | จำนวนแถวสูงสุด (ค่าเริ่มต้น 50, สูงสุด 100) |
  | `offset` | integer | No | ตำแหน่งแถวเริ่มต้น (Pagination) |

- **Response: 200 OK**:
  ```json
  [
    {
      "code": "06016315",
      "name_th": "การจัดการข้อมูลและความรู้",
      "name_en": "Data and Knowledge Management",
      "credits": 3,
      "lecture_h": 3,
      "lab_h": 0,
      "self_h": 6,
      "description_th": "แนวคิดพื้นฐาน...",
      "printed_pages": "18",
      "pdf_pages": "18",
      "programs": ["DSBA", "IT"]
    }
  ]
  ```

---

#### 3.3 Endpoint: เพิ่มรายวิชาใหม่ (Course Creation with Dynamic Plan Resolution)
- **Endpoint**: `/api/courses`
- **Method**: `POST`
- **Request Body**:
  ```json
  {
    "code": "06019999",
    "name_th": "วิชาหัวข้อพิเศษทางไอที",
    "name_en": "Special Topics in IT",
    "credits": 3,
    "lecture_h": 3,
    "lab_h": 0,
    "self_h": 6,
    "program_id": "IT",
    "plan_id": "IT_COOP",
    "year": 4,
    "semester": 1
  }
  ```
  | Field | Type | Required | Description |
  | :--- | :--- | :---: | :--- |
  | `code` | string (8 digits) | Yes | รหัสวิชา 8 หลักตามมาตรฐาน สจล. |
  | `name_th` | string | Yes | ชื่อวิชาภาษาไทย |
  | `name_en` | string | No | ชื่อวิชาภาษาอังกฤษ |
  | `credits` | integer (0-12) | Yes | จำนวนหน่วยกิต |
  | `program_id` | string | No | รหัสหลักสูตร เช่น `IT`, `DSBA`, `BIT`, `AIT` |
  | `plan_id` | string | No | รหัสแผนการศึกษา เช่น `IT_COOP`, `IT_NON_COOP` (หากไม่ระบุจะใช้แผนปกติ `NON_COOP` อัตโนมัติ) |
  | `year` | integer (1-8) | Conditional | ชั้นปีที่จัดสอน (บังคับระบุเมื่อมีการระบุ `program_id`) |
  | `semester` | integer (1-3) | Conditional | ภาคการศึกษาที่จัดสอน (บังคับระบุเมื่อมีการระบุ `program_id`) |

- **กติกา Dynamic Plan Resolution**:
  * **กรณีระบุ `plan_id`**: ระบบจะตรวจสอบความถูกต้องเทียบกับแผนที่มีอยู่จริงในฐานข้อมูลเสมอ แม้เป็นหลักสูตรที่มีแผนเดียวอย่าง `AIT` หากระบุผิดแผน ระบบจะปฏิเสธด้วย `422 Unprocessable Entity`
  * **กรณีไม่ระบุ `plan_id`**:
    - หลักสูตรที่มีแผนเดียว (`AIT`): ระบบจะเลือก `AIT_SINGLE` ให้อัตโนมัติ
    - หลักสูตรที่มีหลายแผน (`DSBA`, `BIT`, `IT`): ระบบจะกำหนดเป็นแผนปกติ (`NON_COOP`) เป็นค่าเริ่มต้นอย่างปลอดภัย
  * **หน้าเว็บ UI (`/courses`)**: มี Dropdown แสดงตัวเลือกแผนการศึกษาที่สัมพันธ์กับสาขาที่เลือก เพื่อให้ผู้ใช้เลือกแผนได้โดยตรง

- **Response: สำเร็จ (201 Created)**:
  คืนค่าข้อมูลรายวิชาที่สร้าง พร้อมฟิลด์ `plan_id` ที่ถูกผูกจริง และ `programs`
- **Response: ข้อผิดพลาด**:
  | HTTP Status | เหตุการณ์ | Response Example |
  | :--- | :--- | :--- |
  | `422 Unprocessable Entity` | ระบุ `plan_id` ไม่ตรงกับสาขา หรือระบุ `program_id` แต่ไม่ระบุ `year`/`semester` | `{"detail": "plan_id 'AIT_COOP' ไม่ถูกต้องสำหรับหลักสูตร AIT (แผนที่เป็นไปได้: AIT_SINGLE)"}` |
  | `409 Conflict` | รหัสวิชานี้มีอยู่แล้วในฐานข้อมูล | `{"detail": "รหัสวิชานี้มีอยู่แล้ว"}` |

---

#### 3.4 Endpoint: ตรวจสอบเงื่อนไขวิชาบังคับก่อน (Prerequisite Graph)
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
        "kind": "pre",
        "credits": 3
      }
    ],
    "prerequisites": [
      {
        "code": "06026200",
        "name_th": "การเขียนโปรแกรมคอมพิวเตอร์เบื้องต้น",
        "name_en": "Computer Programming Fundamentals",
        "kind": "pre",
        "credits": 3
      }
    ],
    "required_by": [
      {
        "code": "06026205",
        "name_th": "โครงสร้างข้อมูลและขั้นตอนวิธี",
        "name_en": "Data Structures and Algorithms",
        "kind": "pre",
        "credits": 3
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

#### 3.5 Endpoint: แผนการศึกษา (Study Plans)
- **Endpoint**: `/api/study-plans`
- **Method**: `GET`
- **Query Parameters**:
  | Parameter | Type | Required | Description |
  | :--- | :--- | :---: | :--- |
  | `program_id` | string | No | กรองตามรหัสหลักสูตร เช่น `IT`, `DSBA` |
  | `plan_id` | string | No | กรองตามรหัสแผน เช่น `IT_COOP`, `IT_NON_COOP` |

- **Response: 200 OK**:
  ```json
  [
    {
      "plan_id": "IT_COOP",
      "program_id": "IT",
      "name_th": "แผนสหกิจศึกษา",
      "name_en": "Cooperative Education Plan",
      "plan_type": "coop"
    },
    {
      "plan_id": "IT_NON_COOP",
      "program_id": "IT",
      "name_th": "แผนการศึกษาปกติ",
      "name_en": "Regular Plan",
      "plan_type": "no_coop"
    }
  ]
  ```

---

#### 3.6 Endpoint: รายวิชาตามแผนการศึกษา (Study Plan Items)
- **Endpoint**: `/api/plan`
- **Method**: `GET`
- **Query Parameters**: `year`, `semester`, `program_id`, `plan_id`
- **Response: 200 OK**:
  ```json
  [
    {
      "plan_id": "IT_COOP",
      "plan_type": "coop",
      "program_id": "IT",
      "year": 1,
      "semester": 1,
      "code": "06016101",
      "name_th": "คณิตศาสตร์ดีสครีตสำหรับไอที",
      "credits": 3,
      "lecture_h": 3,
      "lab_h": 0,
      "self_h": 6,
      "is_elective_slot": 0
    }
  ]
  ```

---

#### 3.7 Endpoint: สรุปหน่วยกิตรายภาคเรียน (Semester Credits Summary)
- **Endpoint**: `/api/plan/summary`
- **Method**: `GET`
- **Query Parameters**: `year`, `semester`, `program_id`, `plan_id`
- **Response: 200 OK**:
  ```json
  [
    {
      "plan_id": "IT_COOP",
      "program_id": "IT",
      "year": 1,
      "semester": 1,
      "credits": 18,
      "n_courses": 6
    }
  ]
  ```

---

#### 3.8 Endpoint: สล็อตวิชาเลือก (Elective Slots)
- **Endpoint**: `/api/elective-slots`
- **Method**: `GET`
- **Query Parameters**: `plan_id`, `year`, `semester`
- **Response: 200 OK**:
  ```json
  [
    {
      "id": 1,
      "plan_id": "IT_COOP",
      "year": 3,
      "semester": 1,
      "slot_name_th": "วิชาเลือกเสรี",
      "slot_name_en": "Free Elective",
      "credits": 3,
      "credit_options": "3",
      "note": null
    }
  ]
  ```

---

#### 3.9 Endpoint: ค้นหาข้อบังคับและกฎระเบียบสถาบัน (Regulations & Policies)
- **Endpoint**: `/api/regulations`
- **Method**: `GET`
- **Query Parameters**:
  | Parameter | Type | Required | Description |
  | :--- | :--- | :---: | :--- |
  | `category` | string | No | หมวดหมู่ เช่น `เกณฑ์เกียรตินิยม`, `เกณฑ์ภาคทัณฑ์`, `เกณฑ์การทุจริตในการสอบ`, `เกณฑ์การลงทะเบียน` |
  | `search` | string | No | คำค้นหาในหัวข้อ หรือบทลงโทษ |
  | `limit` | integer | No | จำนวนแถวสูงสุด (ค่าเริ่มต้น 50) |

- **Response: 200 OK**:
  ```json
  [
    {
      "id": 1,
      "program_id": null,
      "category": "เกณฑ์เกียรตินิยม",
      "topic": "เกียรตินิยมอันดับ 1 เหรียญทอง",
      "condition_desc": "ได้แต้มเฉลี่ยสะสมไม่ต่ำกว่า 3.75...",
      "min_gpa": 3.75,
      "max_gpa": null,
      "penalty_action": null,
      "article_no": "ข้อ 25.2.1",
      "source_page": 98
    }
  ]
  ```

---

#### 3.10 Endpoint: ตรวจสอบความพร้อมของระบบ (Health Check)
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

#### 3.11 Endpoint: สรุปภาพรวมสถิติรายวิชาและหน่วยกิต (Curriculum Statistics)
- **Endpoint**: `/api/stats`
- **Method**: `GET`
- **Query Parameters**:
  | Parameter | Type | Required | Description |
  | :--- | :--- | :---: | :--- |
  | `program_id` | string | No | รหัสหลักสูตร เช่น `DSBA`, `BIT`, `IT`, `AIT` (หากไม่ระบุจะสรุปภาพรวมทั้งหมด) |

- **Response: 200 OK**:
  ```json
  {
    "program_id": "DSBA",
    "program_name_th": "หลักสูตรวิทยาศาสตรบัณฑิต สาขาวิชาวิทยาการข้อมูลและการวิเคราะห์เชิงธุรกิจ",
    "program_total_credits": 132,
    "total_courses": 34,
    "total_credits": 99,
    "total_lecture_hours": 80,
    "total_lab_hours": 45,
    "total_self_hours": 174
  }
  ```
  *หมายเหตุ*: ฟิลด์ `program_total_credits` แสดงหน่วยกิตรวมตามที่หลักสูตรประกาศ (เช่น DSBA = 132 หน่วยกิต) ส่วน `total_courses` และ `total_credits` เป็นสถิติของชุดรายวิชาบังคับไม่ซ้ำในระบบ โดยไม่นับข้อมูลข้ามแผนซ้ำซ้อน

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
