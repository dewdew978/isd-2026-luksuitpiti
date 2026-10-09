# Lab 9: Intelligent System Evaluation & Overfitting Framework
วิชา 06026240 การพัฒนาระบบอัจฉริยะ (Intelligent System Development)  
คณะเทคโนโลยีสารสนเทศ สถาบันเทคโนโลยีพระจอมเกล้าเจ้าคุณทหารลาดกระบัง (KMITL)  
**กลุ่ม: Luksuitpiti** (DSBA)

---

##  ที่มาและหลักการประเมินผล (Evaluation Framework)

โฟลเดอร์ `lab9/` นี้ถูกสร้างขึ้นเพื่อรวบรวมสคริปต์ประเมินผลจากทุกแล็บ (Lab 1–8B และ 10) เข้าเป็นชุดทดสอบอัตโนมัติ (Automated Evaluation Suite) โดยวัดประสิทธิภาพแยกตาม 4 ขั้นตอนของระบบ: **สกัด $\rightarrow$ ตรวจ Schema $\rightarrow$ ค้นคืน $\rightarrow$ ตอบ**

---

##  โครงสร้างไฟล์ใน `lab9/`

```text
lab9/
├── README.md                      # คู่มือและคำอธิบายระบบประเมินผล
├── run_all_eval.py                # Master Runner: รันรวดเดียวครบ 4 ขั้นตอน
│
├── step1_eval_extraction.py       # ขั้นที่ 1: การสกัด (Field-level P/R/F1)
├── step2_eval_schema.py           # ขั้นที่ 2: ตรวจสอบ Schema & ความสอดคล้อง 7 กฎ (CHK1–CHK7)
├── step3_eval_nl2sql.py           # ขั้นที่ 3: ค้นคืน NL to SQL (Valid SQL Rate, Execution Accuracy)
├── step4_eval_groundedness.py     # ขั้นที่ 4: ตอบ & อ้างอิง (Groundedness, Citation Coverage, EM)
│
└── reports/                       # ผลการประเมินที่ถูกสร้างขึ้นอัตโนมัติ (JSON Metrics)
    ├── step1_extraction_metrics.json
    ├── step2_schema_verification.json
    ├── step3_nl2sql_benchmark.json
    └── step4_groundedness_metrics.json
```

---

##  วิธีการรันประเมินผล (Quick Start)

### 1. รันประเมินผลรวดเดียวทั้งระบบ (แนะนำ):
```bash
python lab9/run_all_eval.py
```
*(ระบบจะประเมินทั้ง 4 ขั้นตอน และแสดงผลสรุปบนหน้าจอทันที)*

### 2. รันประเมินผลแยกรายขั้นตอน:
```bash
# ขั้นที่ 1: วัดความแม่นยำของการสกัดและ OCR (Lab 7B)
python lab9/step1_eval_extraction.py

# ขั้นที่ 2: ตรวจความถูกต้องของ Schema และความสอดคล้อง 7 กฎ (Lab 8B)
python lab9/step2_eval_schema.py

# ขั้นที่ 3: วัดความแม่นยำ Text-to-SQL (รันสดผ่าน Ollama แบบ Real-time เป็นค่าเริ่มต้น)
python lab9/step3_eval_nl2sql.py             # รันสดครบทุกข้อ
python lab9/step3_eval_nl2sql.py --limit 10  # รันสดตัวอย่าง 10 ข้อ
python lab9/step3_eval_nl2sql.py --cached    # ใช้ผลลัพธ์ที่เคยบันทึกไว้

# ขั้นที่ 4: ตรวจสอบความซื่อสัตย์ต่อฐานข้อมูลและการอ้างอิงเลขหน้าจริง (Groundedness & Citation)
python lab9/step4_eval_groundedness.py            # ประเมินผลสดอัตโนมัติ (ดึงผลสดจาก Step 3 ทันที)
python lab9/step4_eval_groundedness.py --live     # รันถามและประเมินคำตอบภาษาไทยสดผ่าน Ollama
python lab9/step4_eval_groundedness.py --cached   # ใช้ผลลัพธ์ baseline เดิม
```

---

##  สรุปผลการประเมิน (Evaluation Metrics Summary)

| ขั้นตอนของระบบ | Metric ที่ใช้วัด | ความหมายในบริบทของระบบหลักสูตร | ผลลัพธ์ที่ได้ |
| :--- | :--- | :--- | :---: |
| **1. การสกัด (Extraction)** | **Field-level Recall** | สกัดรหัสวิชาครบ ไม่ตกหล่นไปจากฐานข้อมูล | **99.0%** (313/316 รายวิชา) |
| | **Field-level Precision** | ตรวจจับเฉพาะวิชาจริง สกัดได้แม่นยำ | **97.2%** |
| | **F1-Score** | ความแม่นยำสมดุลระดับรายวิชา | **98.1%** |
| **2. ตรวจสอบ Schema** | **Schema Pass Rate** | ข้อมูลผ่าน Pydantic และตาราง Option 2: Full Separation | **100.0%** |
| | **Consistency Pass Rate** | ผ่านกฎความสอดคล้อง **7 จาก 7 ข้อ (CHK1–CHK7)** | **100.0% (7/7 ข้อ)** |
| **3. ค้นคืน (NL to SQL)** | **Valid SQL Rate** | สัดส่วนคำสั่ง SQL ที่สร้างขึ้นแล้วรันผ่านได้ ไวยากรณ์ถูกต้อง | **100.0%** (180/180 คำถาม) |
| | **Execution Accuracy (SQL)** | รัน SQL แล้วได้ผลลัพธ์ตรงกับเฉลย | **95.0%** (171/180 คำถาม) |
| **4. ตอบ & อ้างอิง** | **Faithfulness / Groundedness** | คำตอบตรงตามผลลัพธ์ SQL ในฐานข้อมูลจริง | **95.0%** (171/180 ข้อ) |
| | **Exact Match (EM)** | คำตอบตรงเฉลยสำหรับค่าเดี่ยว (หน่วยกิต, รหัสวิชา) | **94.7%** (162/171 ข้อ) |
| | **Course Citation Coverage** | สัดส่วนวิชาที่มีเลขหน้าจริงจากเล่ม มคอ.2 กำกับอยู่ในระบบ | **99.6%** (262/263 รายวิชา) |
| | **Regulation Citation Cov** | สัดส่วนข้อบังคับที่มีเลขหน้าสแกนจริงจากภาคผนวก ก | **100.0%** (11/11 ข้อบังคับ) |

---

##  กลยุทธ์การป้องกัน Overfitting (Generalization Strategy)

1. **หลีกเลี่ยง Memorization**: ไม่เขียนโค้ดดักจับคำถามเฉพาะ (No hardcoded answers) แต่แยกข้อเท็จจริงไปจัดเก็บใน **Relational SQLite Database (Option 2)**
2. **Schema-Grounded Prompting**: ส่งเฉพาะโครงสร้าง Schema ตารางและคีย์เชื่อมโยงไปยัง Prompt เพื่อให้ LLM แปลงคำถามทั่วไปหรือคำถาม Unseen เป็นคำสั่ง SQL ได้อย่างยืดหยุ่น
3. **ควบคุมความแปรปรวน (Inference Hyperparameters)**:
   - `temperature = 0.1`: ลดความสุ่มของคำตอบ ให้ผลลัพธ์มีความเสถียร
   - `repeat_penalty = 1.2`: ป้องกันการพูดซ้ำวนลูป
   - `top_k = 40`: คัดกรองโทเคนที่มีความน่าจะเป็นสูง
