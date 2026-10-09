<div align="center">
 
![header](https://capsule-render.vercel.app/api?type=transparent&color=0:4B5FBF,100:8B5FA8&height=180&section=header&text=ISD%20Luksuitpiti&fontSize=42&fontColor=cccccc&fontAlignY=35&desc=OCR%20Evaluation%20Pipeline%20For%20School%20of%20Information%20Technology&descAlignY=55&descSize=16)  
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Tesseract](https://img.shields.io/badge/Tesseract%20OCR-4B5FBF?style=for-the-badge&logo=google&logoColor=white)

![Semester](https://img.shields.io/badge/Semester-1%2F2569-9b59b6)
![Programs](https://img.shields.io/badge/Programs-AIT%20%7C%20IT%20%7C%20DSBA%20%7C%20BIT-2196f3)
![Language](https://img.shields.io/badge/Language-Python-2196f3)
![Status](https://img.shields.io/badge/Status-Active-4caf50)
 
</div>
# isd-2026-luksuitpiti: Curriculum Assistant & Intelligent OCR System
วิชา 06026240 การพัฒนาระบบอัจฉริยะ (Intelligent System Development)  
คณะเทคโนโลยีสารสนเทศ สถาบันเทคโนโลยีพระจอมเกล้าเจ้าคุณทหารลาดกระบัง (KMITL)

## สมาชิกกลุ่ม (Group Members - Luksuitpiti)
| ลำดับ | รหัสนักศึกษา | ชื่อ - นามสกุล | GitHub Username | สาขาวิชา |
|:---:|:---:|:---|:---|:---:|
| 1 | 67070098 | นายปวริศ ปัญสิงห์ | _drews. | DSBA |
| 2 | 67070141 | นายภูวิศ ทรายทอง | babysalmonnn | DSBA |
| 3 | 67070190 | นายสุวิจักขณ์ กุลฉัตลานนท์ | sv_jatm | DSBA |
| 4 | 67070307 | นายปิติ หยาง | pingsensei | DSBA |

---

## คู่มือการรัน Application สำหรับอาจารย์และผู้ตรวจประเมิน (Quick Start Guide)

โปรเจกต์นี้พัฒนาระบบสกัดข้อมูลเล่มหลักสูตร มคอ.2 (ครอบคลุมทั้ง 4 สาขาวิชา: DSBA, BIT, IT, AIT) เข้าสู่ฐานข้อมูลเชิงสัมพันธ์ SQLite และให้บริการเว็บแอปพลิเคชันถามตอบด้วย Text-to-SQL (NL2SQL) ร่วมกับ Local LLM (Ollama)

### 1. ความต้องการของระบบ (Prerequisites)
- **Python**: เวอร์ชัน 3.10 ขึ้นไป
- **Ollama**: ติดตั้งและเปิด Background Service:
  ```bash
  ollama serve
  ```
  จากนั้นดาวน์โหลดโมเดล LLM สำหรับ Text-to-SQL:
  ```bash
  ollama pull qwen3:4b
  ```

---

### 2. ขั้นตอนการติดตั้ง Dependencies
เปิด Terminal ในโฟลเดอร์โปรเจกต์ และติดตั้งไลบรารีที่จำเป็น:
```bash
pip install -r requirements.txt
```

---

### 3. การเตรียมฐานข้อมูลหลักสูตร (Database Setup)
> **หมายเหตุ**: โปรเจกต์มีฐานข้อมูล SQLite สำเร็จรูปที่ผ่านการสกัดครบทั้ง 263 รายวิชา (262 แผนการเรียน, 59 elective slots, 11 regulations, 26 prerequisites) และผ่านการตรวจสอบความสอดคล้อง (Consistency Verification) ครบ 7 กฎ 100% บันทึกไว้ที่ `work/lab8b_run/curriculum.db` (รวมทั้งฐานข้อมูลเดี่ยว 4 สาขาที่ `work/lab8b_run/{DSBA,BIT,IT,AIT}/curriculum.db`) เรียบร้อยแล้ว **สามารถข้ามไปขั้นตอนที่ 4 เพื่อเปิดรันเว็บแอปพลิเคชันได้ทันที**

หากต้องการสั่งรันกระบวนการสกัดใหม่จากเล่มหลักสูตร PDF ต้นฉบับ (Cold-Start Reproduction):

#### ก. สกัดข้อมูลรายวิชาด้วย Lab 7B (แผนการศึกษา + วิชาเลือกเฉพาะ ครบ 4 หลักสูตร):
```bash
python src/ocr_system/lab7b_curriculum.py -i data/input/fulldoc_dsba.pdf --pages 19-25,33-39 -g data/ground_truth/DSBA/DSBA_academic_plan_coop.json -p text -o lab7_final/output/DSBA --program DSBA
python src/ocr_system/lab7b_curriculum.py -i data/input/fulldoc_BIT.pdf --pages 24-25,31-35 -g data/ground_truth/BIT/BIT_academic_plan_coop.json -p text -o lab7_final/output/BIT --program BIT
python src/ocr_system/lab7b_curriculum.py -i data/input/fulldoc_it.pdf --pages 26-30,39-45 -g data/ground_truth/IT/IT_academic_plan_coop.json -p text -o lab7_final/output/IT --program IT
python src/ocr_system/lab7b_curriculum.py -i data/input/fulldoc_AIT.pdf --pages 21-26 -g data/ground_truth/AIT/AIT_academic_plan.json -p text -o lab7_final/output/AIT --program AIT
```

##### 📊 ตารางสรุปผลการสกัดและช่วงหน้าของแต่ละหลักสูตร (Extraction Benchmark & Page Coverage)

| หลักสูตร | ช่วงหน้าที่กำหนด (`--pages`) | เนื้อหาและโครงสร้างในช่วงหน้าดังกล่าว | เวลาที่ใช้ | จำนวนวิชาที่สกัดได้ | มีเลขหน้าอ้างอิงจริง | ความแม่นยำ (F1-Score) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **DSBA** | `19-25, 33-39` | แผนการศึกษาปกติ / สหกิจศึกษา (ปี 1–4) และกลุ่มวิชาเลือกเฉพาะด้าน | 2.5 วินาที | 90 วิชา | 79 วิชา | **95.6%** (P=0.956, R=0.956) |
| **IT** | `26-30, 39-45` | แผนการศึกษาปกติ (ปี 1–4) และแผนการศึกษาสหกิจศึกษา (ปี 1–4) | 1.6 วินาที | 110 วิชา | 104 วิชา | **96.3%** (P=0.946, R=0.981) |
| **BIT** | `24-25, 31-35` | โครงสร้างกลุ่มวิชาเลือก และแผนการศึกษาสหกิจศึกษา (ปี 1–4) | 1.3 วินาที | 58 วิชา | 51 วิชา | **92.6%** (P=0.966, R=0.889) |
| **AIT** | `21-26` | กลุ่มวิชาเลือกเฉพาะ (หน้า 21–22) และแผนการศึกษา ปี 1–4 (หน้า 23–26) | 1.1 วินาที | 57 วิชา | 50 วิชา | **96.5%** (P=0.965, R=0.965) |

##### 🔬 การประเมินผลไฟล์สกัดย้อนหลัง (Offline Evaluation via `--eval-only`):
หากมีไฟล์ `pred_text.json` อยู่แล้ว สามารถสั่งประเมินผลเทียบกับ Ground Truth ได้ทันทีโดยไม่ต้องสกัดใหม่:
```bash
# IT
python -m src.ocr_system.lab7b_curriculum --eval-only work/lab7b_run/IT/pred_text.json -g data/ground_truth/IT/IT_academic_plan_coop.json
# DSBA
python -m src.ocr_system.lab7b_curriculum --eval-only work/lab7b_run/DSBA/pred_text.json -g data/ground_truth/DSBA/DSBA_academic_plan_coop.json
# BIT
python -m src.ocr_system.lab7b_curriculum --eval-only work/lab7b_run/BIT/pred_text.json -g data/ground_truth/BIT/BIT_academic_plan_coop.json
# AIT
python -m src.ocr_system.lab7b_curriculum --eval-only work/lab7b_run/AIT/pred_text.json -g data/ground_truth/AIT/AIT_academic_plan.json
```
*ระบบจะคำนวณและบันทึกไฟล์สรุปผลอัตโนมัติ:*
- `comparison.csv`: ตารางคะแนน CER, WER (ตัดคำภาษาไทยด้วย PyThaiNLP `newmm`), Exact Match (เข้ารหัส UTF-8 BOM เปิดใน Excel ได้ทันที)
- `evaluation.json`: ข้อมูลความแม่นยำ Alignment (Precision, Recall, F1) และรายการวิชาที่โมเดลอ่านตก

> **หมายเหตุการวิเคราะห์ Alignment (กรณี IT ตก 2, เกิน 6)**:
> 1. **เกิน 4 วิชา (Duplicates)**: วิชา `06016428, 06016430, 06016439, 06016447` ปรากฏอยู่ในตารางวิชาเลือกทั้ง 2 หน้า โมเดลจึงสกัดออกมา 2 ครั้ง ในขณะที่เฉลยมีรายการละ 1 ครั้ง
> 2. **เกิน 2 วิชา / ตก 1 วิชา (Alternative Split)**: สหกิจศึกษา (`06016481` และ `06016482`) ในเฉลยเขียนรวบเป็น 1 แถวเดียวว่า `"06016481 หรือ 06016482"` แต่โมเดลสกัดแยกเป็น 2 แถวเดี่ยวที่ถูกต้องตามโครงสร้างฐานข้อมูล
> 3. **ตก 1 วิชา (Multiple Tracks)**: วิชา `06016418` เปิดสอน 2 แขนง ในเฉลยใส่ไว้ 2 แถว แต่โมเดลสกัดมา 1 แถว
> *(เมื่อนำเข้าสู่ฐานข้อมูล SQLite ใน Lab 8B ระบบมีฟังก์ชัน **Deduplication** ยุบวิชาซ้ำเหลือ 1 รายการ และจัดวิชาคู่สหกิจศึกษาเป็น **Alternative Slot (`alt_group`)** จึงทำให้ฐานข้อมูลสะอาด 100% และผ่านการตรวจครบ 7 กฎ)*


#### ก.2 สกัดข้อบังคับการศึกษา (ภาคผนวก ก) ด้วย Lab 7B (Typhoon-OCR 1.5-3B + Qwen3:4b):
> **หมายเหตุ**: ในเล่มหลักสูตร เนื้อหาภาคผนวก ก (ข้อบังคับ สจล. ว่าด้วยการศึกษาระดับปริญญาตรี พ.ศ. 2564) หน้า 94–101 เป็น**ภาพสแกน (Scanned Bitmap Images)** ที่ไม่มี Text Layer ดั้งเดิม จึงต้องใช้ Local Vision-Language Model (VLM) ในการถอดรหัสข้อความภาษาไทยและแปลงเป็น Structured Data:

```bash
# สกัดข้อบังคับการศึกษาจากเล่ม PDF (บันทึกผลลง work/lab7b_run/)
python src/ocr_system/lab7b_curriculum.py --extract-regulations

# หรือระบุพาธและหน้าที่ต้องการสกัดเอง:
python src/ocr_system/lab7b_curriculum.py --extract-regulations -i data/input/fulldoc_dsba.pdf --pages 94,96,97,98,99,101 -o work/lab7b_run
```
*ผลลัพธ์ที่ได้ (บันทึกใน `work/lab7b_run/`):*
- `intermediate_regulations_vlm.md`: ข้อความภาษาไทยสมบูรณ์จากหน้าสแกน 94, 96, 97, 98, 99, 101 ถอดรหัสด้วย `scb10x/typhoon-ocr1.5-3b`
- `regulations.json`: Structured Data ข้อบังคับ 11 รายการ (เกณฑ์การลงทะเบียน 9–22 หน่วยกิต, บทลงโทษการทุจริตสอบ, เกณฑ์ภาคทัณฑ์ GPA < 2.00, พ้นสภาพนักศึกษา, เกณฑ์เกียรตินิยมอันดับ 1 เหรียญทอง/อันดับ 1/อันดับ 2)

---

#### ข. แปลงและนำเข้าฐานข้อมูล SQLite ด้วย Lab 8B (Option 2: Full Separation Architecture):
```bash
# 1. สร้าง Schema กลาง
python src/ocr_system/lab8b_curriculum_db.py schema -o work/lab8b_run/schema

# 2. แปลงผลลัพธ์จาก Lab 7B เข้าสู่ Schema Lab 8B (Option 2)
python src/ocr_system/lab8b_curriculum_db.py import-lab7b -i lab7_final/output/DSBA/pred_text.json -o work/lab8b_run/DSBA/curriculum.json --program-id DSBA --program-name "วิทยาการข้อมูลและการวิเคราะห์เชิงธุรกิจ (สหกิจศึกษา)" --name-en "Data Science and Business Analytics (DSBA)" --total-credits 132 --years 4
python src/ocr_system/lab8b_curriculum_db.py import-lab7b -i lab7_final/output/BIT/pred_text.json -o work/lab8b_run/BIT/curriculum.json --program-id BIT --program-name "เทคโนโลยีสารสนเทศทางธุรกิจ (สหกิจศึกษา)" --name-en "Business Information Technology (BIT)" --total-credits 126 --years 4
python src/ocr_system/lab8b_curriculum_db.py import-lab7b -i lab7_final/output/IT/pred_text.json -o work/lab8b_run/IT/curriculum.json --program-id IT --program-name "เทคโนโลยีสารสนเทศ (สหกิจศึกษา)" --name-en "Information Technology (IT)" --total-credits 129 --years 4
python src/ocr_system/lab8b_curriculum_db.py import-lab7b -i lab7_final/output/AIT/pred_text.json -o work/lab8b_run/AIT/curriculum.json --program-id AIT --program-name "เทคโนโลยีปัญญาประดิษฐ์" --name-en "Artificial Intelligence Technology (AIT)" --total-credits 120 --years 4

# 3. โหลดข้อมูลรายวิชาเข้าฐานข้อมูลกลาง (Unified Database: 263 รายวิชา, 7 แผน)
python src/ocr_system/lab8b_curriculum_db.py load -i work/lab8b_run/DSBA/curriculum.json -d work/lab8b_run/curriculum.db --replace
python src/ocr_system/lab8b_curriculum_db.py load -i work/lab8b_run/BIT/curriculum.json -d work/lab8b_run/curriculum.db
python src/ocr_system/lab8b_curriculum_db.py load -i work/lab8b_run/IT/curriculum.json -d work/lab8b_run/curriculum.db
python src/ocr_system/lab8b_curriculum_db.py load -i work/lab8b_run/AIT/curriculum.json -d work/lab8b_run/curriculum.db

# 4. โหลดข้อบังคับการศึกษา (Regulations) เข้าตาราง regulation
python src/ocr_system/lab8b_curriculum_db.py load-regulations -i work/lab7b_run/regulations.json -d work/lab8b_run/curriculum.db

# (ทางเลือก) โหลดฐานข้อมูลเดี่ยวแยกแต่ละสาขาวิชา (Isolated Program Databases)
# python src/ocr_system/lab8b_curriculum_db.py load -i work/lab8b_run/DSBA/curriculum.json -d work/lab8b_run/DSBA/curriculum.db --replace
# python src/ocr_system/lab8b_curriculum_db.py load -i work/lab8b_run/BIT/curriculum.json -d work/lab8b_run/BIT/curriculum.db --replace
# python src/ocr_system/lab8b_curriculum_db.py load -i work/lab8b_run/IT/curriculum.json -d work/lab8b_run/IT/curriculum.db --replace
# python src/ocr_system/lab8b_curriculum_db.py load -i work/lab8b_run/AIT/curriculum.json -d work/lab8b_run/AIT/curriculum.db --replace
```

#### ค. ตรวจสอบความถูกต้องของฐานข้อมูล (Consistency Verification 7 กฎ):
```bash
python src/ocr_system/lab8b_curriculum_db.py verify -d work/lab8b_run/curriculum.db -o work/lab8b_run/verify.json
```
**ผลการตรวจสอบ (ผ่านครบ 7 จาก 7 ข้อ 100%):**
```text
  [ผ่าน  ] CHK1  หน่วยกิตรวมของแผน = หน่วยกิตที่หลักสูตรประกาศ
           AIT_SINGLE: 120/120 | BIT_COOP: 126/126 | BIT_NON_COOP: 126/126 | DSBA_COOP: 132/132 | DSBA_NON_COOP: 132/132 | IT_COOP: 129/129 | IT_NON_COOP: 129/129
  [ผ่าน  ] CHK2  ทุกรหัสวิชาในแผน มีคำอธิบายรายวิชา (ครบทุกรหัส 263 วิชา)
  [ผ่าน  ] CHK3  รหัสวิชาเป็นตัวเลข 8 หลักทุกรายการ
  [ผ่าน  ] CHK4  หน่วยกิตในแผน ตรงกับคำอธิบายรายวิชา
  [ผ่าน  ] CHK5  วิชาบังคับก่อน อยู่ภาคเรียนก่อนวิชาที่อ้างถึง
  [ผ่าน  ] CHK6  ไม่มีวิชาซ้ำในภาคเรียนเดียวกัน
  [ผ่าน  ] CHK7  หน่วยกิตต่อภาคเรียนอยู่ระหว่าง 9–22 หน่วยกิต
```

#### ง. การประเมินผลชุดคำถามทดสอบ Text-to-SQL (NL2SQL Benchmark):
ระบบผ่านการประเมินผลชุดคำถาม Gold Questions รวม 180 คำถาม (โครงสร้างหลักสูตร, แผนการเรียน, วิชาเลือก, วิชาบังคับก่อน และข้อบังคับการศึกษา):
```bash
# รันการประเมินผล Text-to-SQL อัตโนมัติบนฐานข้อมูลกลาง
python src/ocr_system/lab8b_curriculum_db.py eval -d work/lab8b_run/curriculum.db -q work/lab8b_run/gold_questions.json -o work/lab8b_run/eval_result.json --model qwen3:4b
```
**สรุปผลการประเมิน (Evaluation Metrics):**
- **SQL Syntax Validity**: **100.0%** (180/180 คำถามสร้าง SQL ที่ถูกต้องตามไวยากรณ์ SQLite)
- **Answer Correctness (Unified Database)**: **95.0%** (171/180 คำถาม)
- **Per-Program Correctness (Isolated Databases)**:
  - **BIT**: **100.0%** (45/45 ข้อ)
  - **IT**: **100.0%** (45/45 ข้อ)
  - **DSBA**: **91.1%** (41/45 ข้อ)
  - **AIT**: **88.9%** (40/45 ข้อ)
  - *เฉลี่ยรวม 4 สาขาวิชา: **95.0%** (171/180 ข้อ)*

---

### 4. ขั้นตอนการสั่งรัน Web Application (FastAPI + Modern Web UI)
สั่งรันเว็บเซิร์ฟเวอร์ด้วยคำสั่ง:
```bash
python -m uvicorn lab10_fastapi.curriculum_app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

### 5. การเปิดใช้งานหน้าเว็บผ่าน Web Browser
เมื่อเซิร์ฟเวอร์เปิดทำงานแล้ว สามารถเปิดเบราว์เซอร์และเข้าไปที่:
1. **หน้าถามตอบหลักสูตร AI (Assistant Chat UI)**:
   - URL: [http://127.0.0.1:8000/](http://127.0.0.1:8000/) หรือ [http://127.0.0.1:8000/static/index.html](http://127.0.0.1:8000/static/index.html)
   - ฟีเจอร์: ถามตอบภาษาธรรมชาติเกี่ยวกับโครงสร้างหลักสูตร แผนการเรียน และข้อบังคับการศึกษา พร้อมระบบแสดง SQL และตารางข้อมูล
   - **ระบบ Grounded Citation Badge**: แสดงป้ายเลขหน้าอ้างอิงจริง `[อ้างอิงหน้า x]` วางเคียงข้างป้าย `[Success]` เหนือกล่องคำตอบอย่างเป็นระเบียบ (เช่น รายวิชาอ้างอิงหน้า 17, ข้อบังคับอ้างอิงหน้า 98 ข้อ 25.2.2, โครงสร้างหลักสูตรอ้างอิงหมวดที่ 3)
2. **หน้าโครงสร้างหลักสูตรและรายวิชาทั้งหมด (Course Catalog & Regulations)**:
   - URL: [http://127.0.0.1:8000/courses](http://127.0.0.1:8000/courses) หรือ [http://127.0.0.1:8000/static/courses.html](http://127.0.0.1:8000/static/courses.html)
   - ฟีเจอร์: ตรวจสอบรายวิชาทั้งหมด 263 วิชา ค้นหารหัส/ชื่อวิชา ตรวจสอบวิชาบังคับก่อน (Prerequisites) และดูข้อบังคับการศึกษา สจล.
3. **หน้า Interactive API Documentation (Swagger UI)**:
   - URL: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - ฟีเจอร์: ทดสอบเรียกใช้งาน API Endpoint ทุกเส้นได้โดยตรง

---

### 6. ตัวอย่างคำถามทดสอบการทำงานของระบบ (Test Queries)
- **คำถามเชิงโครงสร้าง**:
  - `หลักสูตร DSBA มีกี่หน่วยกิต` $\rightarrow$ ตอบ `132` (`[อ้างอิง: หมวดที่ 3]`)
  - `วิชา 06026216 คือวิชาอะไร` $\rightarrow$ ตอบ `ปัญญาประดิษฐ์` (`[อ้างอิงหน้า 17]`)
  - `วิชา 06026241 ต้องเรียนวิชาใดมาก่อน`
- **คำถามเชิงความสัมพันธ์และแผนการศึกษา**:
  - `ปี 1 เทอม 1 เรียนกี่หน่วยกิต` $\rightarrow$ ตอบ `18` (`[อ้างอิง: หมวดที่ 3]`)
  - `ปี 2 เทอม 1 สาขา DSBA เรียนวิชาอะไรบ้าง`
  - `หลักสูตร IT มีวิชากี่ตัว`
- **คำถามเชิงข้อบังคับการศึกษา (Regulations)**:
  - `เกียรตินิยมอันดับ 1 ต้องได้เกรดเท่าไร` $\rightarrow$ ตอบ `3.5` (`[อ้างอิงหน้า 98]`)
  - `ทุจริตในการสอบจะถูกลงโทษอย่างไร` $\rightarrow$ (`[อ้างอิงหน้า 101]`)
  - `ลงทะเบียนเรียนภาคปกติได้สูงสุดกี่หน่วยกิต` $\rightarrow$ ตอบ `22` (`[อ้างอิงหน้า 94]`)

---

# Thai-English OCR System (Lab 1 - Lab 6)

## Project Structure

```text
ocr_system/
├── README.md
├── requirements.txt
├── pyproject.toml
├── data/
│   ├── input/                 # ใส่ไฟล์ภาพหรือ PDF ที่ต้องการ OCR
│   ├── ground_truth/          # ไฟล์เฉลยสำหรับ evaluate
│   └── QA/                    # โฟลเดอร์สำหรับทดสอบ QA
├── outputs/                   # ผลลัพธ์ OCR และ evaluation
└── src/
    └── ocr_system/
        ├── cli.py             # command line interface
        ├── config.py          # config หลักของระบบ
        ├── document_loader.py # โหลดภาพ / แปลง PDF เป็นภาพ
        ├── preprocessing.py   # resize, denoise, contrast, deskew, threshold
        ├── pipeline.py        # OCR pipeline หลัก
        ├── evaluation.py      # CER, WER, exact match
        ├── field_extraction.py# ดึง field เช่น email, date, id, phone
        ├── schemas.py         # dataclass ของผลลัพธ์
        ├── engine_factory.py  # เลือก OCR engine
        ├── engines/
        │   ├── base.py
        │   ├── paddle_engine.py
        │   ├── tesseract_engine.py
        │   ├── trocr_engine.py
        │   └── ensemble_engine.py
        └── utils/
            └── io.py
```

---

## ใช้งานผ่าน VS Code 

แนะนำให้ใช้ **VS Code** เพราะเปิดดูโครงสร้างไฟล์ แก้โค้ด และรันคำสั่งใน Terminal ได้ในที่เดียว
---
## วิธีเปิดโปรเจกต์ใน VS Code
1. แตกไฟล์ `ocr_system.zip`
2. จะได้โฟลเดอร์ชื่อ `ocr_system`
3. เปิด VS Code
4. ไปที่เมนู
```text
File > Open Folder
```

5. เลือกโฟลเดอร์ `ocr_system`
6. เปิด Terminal ใน VS Code
```text
Terminal > New Terminal
```
หลังจากนี้ให้พิมพ์คำสั่งต่าง ๆ ใน Terminal ของ VS Code ได้เลย

---

## Installation
แนะนำใช้ Python 3.10 ขึ้นไป
เช็กเวอร์ชัน Python ก่อน:

```bash
python --version
```
หรือบางเครื่องอาจต้องใช้:
```bash
py --version
```
ถ้าเวอร์ชันเป็น Python 3.10, 3.11 หรือ 3.12 สามารถใช้ได้

---

## สร้าง Virtual Environment
Virtual Environment คือพื้นที่แยกสำหรับติดตั้ง package ของโปรเจกต์นี้โดยเฉพาะ เพื่อไม่ให้ชนกับโปรเจกต์อื่น
ให้เข้าไปในโฟลเดอร์โปรเจกต์ก่อน:
```bash
cd ocr_system
```
จากนั้นสร้าง environment:
```bash
python -m venv .venv
```

ถ้าใช้ Windows แล้วคำสั่ง `python` ไม่ได้ ให้ลองใช้:
```bash
py -m venv .venv
```

---

## เปิดใช้งาน Virtual Environment

### Windows CMD
```bash
.venv\Scripts\activate
```

### Windows PowerShell
```bash
.venv\Scripts\Activate.ps1
```

ถ้า PowerShell ขึ้น error เรื่อง policy ให้รัน:
```bash
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

แล้วลอง activate ใหม่อีกครั้ง

### macOS / Linux
```bash
source .venv/bin/activate
```
ถ้าสำเร็จ จะเห็นชื่อ environment ขึ้นต้นบรรทัดประมาณนี้:
```text
(.venv) C:\...\ocr_system>
```

---

## ติดตั้ง Python Packages
หลังจาก activate `.venv` แล้ว ให้ติดตั้ง package ทั้งหมด:
```bash
pip install -r requirements.txt
```

จากนั้นติดตั้งโปรเจกต์แบบ editable:
```bash
pip install -e .
```

คำสั่งนี้ทำให้สามารถเรียกใช้งานโปรเจกต์ด้วยรูปแบบนี้ได้:
```bash
python -m ocr_system.cli
```

---

## Install Tesseract Engine
ในโปรเจกต์นี้มี OCR หลายตัว เช่น PaddleOCR, Tesseract และ TrOCR
แต่สำหรับ Tesseract ต้องติดตั้งโปรแกรม Tesseract OCR แยกต่างหาก เพราะ `pytesseract` เป็นแค่ Python package ที่ใช้เรียกโปรแกรม Tesseract เท่านั้น

---

## ติดตั้ง Tesseract บน Windows
ให้ติดตั้ง Tesseract OCR จาก UB Mannheim build
ระหว่างติดตั้ง ให้เลือกภาษา:
```text
English
Thai
```

หลังติดตั้งเสร็จ ให้เปิด CMD หรือ VS Code Terminal ใหม่ แล้วตรวจสอบ:
```bash
tesseract --version
```

จากนั้นตรวจสอบภาษาที่ติดตั้ง:
```bash
tesseract --list-langs
```
ควรเห็นอย่างน้อย:
```text
eng
tha
```
ถ้าไม่เห็น `tha` แปลว่ายังไม่ได้ติดตั้งภาษาไทย

---

## ติดตั้ง Tesseract บน Ubuntu / Debian
```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-tha poppler-utils
```
---

## ติดตั้ง Tesseract บน macOS
```bash
brew install tesseract poppler
brew install tesseract-lang
```
หมายเหตุ: `poppler` จำเป็นสำหรับแปลง PDF เป็นภาพผ่าน `pdf2image`

---

## เตรียมไฟล์สำหรับทดสอบ OCR
นำไฟล์เอกสารไปวางในโฟลเดอร์นี้:
```text
data/input/
```

ตัวอย่าง:
```text
data/input/sample.pdf
data/input/sample.jpg
data/input/sample.png
```

รองรับทั้ง:
```text
PDF หลายหน้า
JPG
PNG
TIFF
BMP
```

---

## Usage
### 1. OCR ด้วย Ensemble
Ensemble คือการใช้หลาย OCR engine ช่วยกัน แล้วเลือกผลลัพธ์ที่เหมาะสมที่สุด
เหมาะสำหรับเอกสารที่มีทั้งภาษาไทยและอังกฤษปนกัน

```bash
python -m ocr_system.cli ocr data/input/sample.pdf --engine ensemble
```

หลังรันเสร็จ ผลลัพธ์จะอยู่ในโฟลเดอร์:
```text
outputs/
```

จะได้ไฟล์ประมาณนี้:
```text
outputs/sample_ocr.json
outputs/sample_ocr.txt
outputs/sample_fields.json
outputs/pages/
```

ความหมายของไฟล์:
```text
sample_ocr.json     ผล OCR แบบละเอียด เช่น text, confidence, page
sample_ocr.txt      ข้อความ OCR รวมทั้งหมด อ่านง่าย
sample_fields.json  field ที่ระบบพยายาม extract เช่น วันที่ ชื่อ รหัส
outputs/pages/      ภาพแต่ละหน้าที่แปลงจาก PDF
```

---

## 2. OCR ด้วย PaddleOCR
เหมาะกับเอกสารทั่วไป โดยเฉพาะภาษาไทยและอังกฤษปนกัน
```bash
python -m ocr_system.cli ocr data/input/sample.jpg --engine paddle --paddle-lang th
```
ถ้าเอกสารเป็นอังกฤษล้วน อาจลองใช้:
```bash
python -m ocr_system.cli ocr data/input/sample.jpg --engine paddle --paddle-lang en
```
---
## 3. OCR ด้วย Tesseract ไทย + อังกฤษ
เหมาะกับเอกสาร scan ที่ตัวหนังสือชัด หรือเอกสารราชการ/ฟอร์มที่ layout ไม่ซับซ้อนมาก
```bash
python -m ocr_system.cli ocr data/input/sample.jpg --engine tesseract --languages tha+eng
```

ถ้าเป็นอังกฤษอย่างเดียว:
```bash
python -m ocr_system.cli ocr data/input/sample.jpg --engine tesseract --languages eng
```

ถ้าเป็นไทยอย่างเดียว:
```bash
python -m ocr_system.cli ocr data/input/sample.jpg --engine tesseract --languages tha
```

---

## 4. OCR ด้วย TrOCR
TrOCR เป็นโมเดล OCR จาก Transformer
ในโปรเจกต์นี้ใช้เป็น fallback สำหรับข้อความสั้น ๆ หรือภาพที่ crop เป็นบรรทัดแล้ว
```bash
python -m ocr_system.cli ocr data/input/sample.jpg --engine trocr --device cpu
```
ถ้ามี GPU และติดตั้ง PyTorch แบบ CUDA แล้ว สามารถใช้:
```bash
python -m ocr_system.cli ocr data/input/sample.jpg --engine trocr --device cuda
```
หมายเหตุ: TrOCR ในโปรเจกต์นี้ยังไม่เหมาะกับเอกสารยาวทั้งหน้า แนะนำใช้ PaddleOCR หรือ Tesseract เป็นหลัก

---
## Evaluation
Evaluation คือการวัดว่า OCR อ่านถูกแค่ไหน โดยเทียบกับข้อความจริง หรือ Ground Truth
สร้างไฟล์ ground truth เช่น:
```text
data/ground_truth/example_ground_truth.json
```

ตัวอย่างเนื้อหา:
```json
{
  "sample.pdf": "ข้อความจริงทั้งหมดในเอกสาร sample.pdf",
  "sample.jpg": "ข้อความจริงในเอกสาร sample.jpg"
}
```

จากนั้นรัน OCR ก่อน:
```bash
python -m ocr_system.cli ocr data/input/sample.pdf --engine ensemble
```
แล้ว evaluate:
```bash
python -m ocr_system.cli evaluate data/ground_truth/example_ground_truth.json outputs/sample_ocr.json
```

Metric ที่ได้:

```text
cer           Character Error Rate ยิ่งต่ำยิ่งดี
wer           Word Error Rate ยิ่งต่ำยิ่งดี
exact_match   ข้อความตรงทั้งหมดหรือไม่
```

ตัวอย่างการอ่านผล:
```text
CER = 0.05 หมายถึงผิดประมาณ 5% ระดับตัวอักษร
WER = 0.12 หมายถึงผิดประมาณ 12% ระดับคำ
exact_match = false หมายถึงยังไม่ตรง 100%
```

> **ข้อแนะนำ:** หากหน้าเอกสารมีข้อความอื่นๆ ปนอยู่มาก (เช่น หัวกระดาษ, คำบรรยาย) ซึ่งไม่มีใน Ground Truth จะทำให้ค่า CER/WER สูงเกินจริง แนะนำให้ใช้คำสั่ง `filter-gt` เพื่อกรองเนื้อหาและประเมินผลเฉพาะรหัสวิชา (Course-level Evaluation) ดูวิธีได้ในหัวข้อ "คำสั่งที่ใช้บ่อย"

---

## คำสั่งที่ใช้บ่อย
OCR ไฟล์ PDF ด้วยระบบรวม:
```bash
python -m ocr_system.cli ocr data/input/sample.pdf --engine ensemble
```

OCR รูปภาพด้วย PaddleOCR:
```bash
python -m ocr_system.cli ocr data/input/sample.jpg --engine paddle --paddle-lang th
```

OCR รูปภาพด้วย Tesseract:
```bash
python -m ocr_system.cli ocr data/input/sample.jpg --engine tesseract --languages tha+eng
```

### การประเมินผล (Evaluation) มี 2 แบบให้เลือกใช้

**แบบที่ 1: ตรวจว่าหารหัสวิชาเจอครบไหม (Code Recall) ⭐ แนะนำสำหรับเอกสารหลักสูตร**
วัดความแม่นยำเป็นเปอร์เซ็นต์ว่าระบบ OCR สามารถหารหัสวิชาเจอถูกต้องกี่ตัว โดยจะต้องใช้ 2 ไฟล์คือ 1) ไฟล์เฉลย (Ground Truth) และ 2) ไฟล์ OCR ที่ถูกสกัดข้อความแล้ว (ใช้คำสั่ง `filter-gt` สร้างไฟล์นี้ขึ้นมาก่อน)
```bash
# 1. กรองข้อความเอาเฉพาะรหัสวิชา (จะได้ไฟล์ _filtered.json)
python -m ocr_system.cli filter-gt outputs/fulldoc_AIT_ocr.json data/ground_truth/AIT/AIT_academic_plan.json

# 2. ประเมินผลระดับ Course-level (ดูค่า code_recall)
python -m ocr_system.cli evaluate data/ground_truth/AIT/AIT_academic_plan.json outputs/fulldoc_AIT_ocr_filtered.json
```

**แบบที่ 2: ตรวจความผิดพลาดระดับตัวอักษรของหน้ากระดาษ (CER / WER)**
วัดว่าตัวอักษรบนหน้ากระดาษอ่านผิดกี่เปอร์เซ็นต์ (อ้างอิงเฉพาะหน้าที่มีใน Ground Truth) โดยใช้ 2 ไฟล์คือ 1) ไฟล์เฉลย และ 2) ไฟล์ OCR ดิบ (`_ocr.json`)
```bash
python -m ocr_system.cli evaluate data/ground_truth/AIT/AIT_academic_plan.json outputs/fulldoc_AIT_ocr.json
```
*(หมายเหตุ: หากหน้าเอกสารมีข้อความอื่นที่ไม่ใช่วิชาปนอยู่ เช่น หัวกระดาษ ค่า CER/WER จะสูงกว่าความเป็นจริง)*

---

## Recommended Engine

สำหรับเอกสารไทย+อังกฤษปนกัน แนะนำเริ่มจาก:
```bash
python -m ocr_system.cli ocr data/input/sample.pdf --engine ensemble --languages tha+eng --paddle-lang th --save-debug-images
```

ถ้าเอกสารเป็นอังกฤษเกือบทั้งหมด:
```bash
python -m ocr_system.cli ocr data/input/sample.pdf --engine paddle --paddle-lang en
```

ถ้า Tesseract อ่านไทยเพี้ยน ให้ลอง OCR แบบไม่ preprocess:
```bash
python -m ocr_system.cli ocr data/input/sample.jpg --engine tesseract --no-preprocess
```

---

## Output JSON Format
```json
{
  "source_path": "data/input/sample.pdf",
  "engine": "ensemble",
  "text": "--- Page 1 ---\n...",
  "pages": [
    {
      "page": 1,
      "text": "...",
      "lines": [
        {
          "text": "ข้อความที่ OCR อ่านได้",
          "confidence": 0.95,
          "box": [[0, 0], [100, 0], [100, 30], [0, 30]],
          "engine": "paddle",
          "page": 1
        }
      ],
      "image_path": "outputs/pages/sample_page_001.jpg"
    }
  ]
}
```

---

## Lab 11: Front-End Development & API Contract

### โครงสร้างไฟล์ Frontend
แยกไฟล์ตาม Best Practice (สไลด์หน้า 7 และ 28):
```text
lab10_fastapi/curriculum_app/static/
├── index.html   # โครงสร้างหน้าเว็บหลัก
├── style.css    # จัดรูปแบบสไตล์, เลย์เอาต์ และ 4 สถานะของระบบ AI
└── app.js       # ตัวควบคุมตรรกะ, async fetch และ 4 สถานะของระบบ AI
```

### การจัดการ 4 สถานะ UI (AI System UX)
1. **Idle**: คำแนะนำการใช้งานพร้อมปุ่มชิปตัวอย่างคำถาม
2. **Loading**: แสดง Spinner และข้อความกำลังประมวลผล พร้อม `disabled` ปุ่มเพื่อป้องกันการกดซ้ำ
3. **Success**: แสดงคำตอบภาษาธรรมชาติจาก AI พร้อมรายละเอียด SQL และตารางข้อมูล (ปลอดภัยจาก XSS ด้วย `textContent`)
4. **Error**: แสดงกล่องเตือนสีแดง แจ้งรายละเอียดข้อผิดพลาดและข้อแนะนำสิ่งที่ผู้ใช้ควรดำเนินการแก้ไข

### API Contract สรุป
| Endpoint | Method | Request Body / Param | Response Success | Response Error |
| :--- | :---: | :--- | :--- | :--- |
| `/api/ask` | POST | `{"question": "string"}` | `200` (`question`, `sql`, `rows`, `answer`, `sources`) | `422` (Invalid/SQL Error), `503` (Ollama/DB offline) |
| `/api/courses` | GET | `search`, `program_id`, `limit`, `offset` | `200` (List of CourseResponse + `programs`) | `503` (DB offline) |
| `/api/courses` | POST | `CourseCreate` (พร้อม `plan_id` Dynamic Check) | `201` (CourseResponse + `plan_id`) | `422` (ขาด `plan_id` ในสาขาหลายแผน), `409` (รหัสซ้ำ) |
| `/api/courses/{code}/prerequisites` | GET | `code`: รหัสวิชา 8 หลัก | `200` (`code`, `name_th`, `requires`, `required_by`) | `404` (ไม่พบรายวิชา), `503` (DB offline) |
| `/api/study-plans` | GET | `program_id`, `plan_id` | `200` (List of StudyPlan: `plan_type` = coop/no_coop/single) | `503` (DB offline) |
| `/api/elective-slots` | GET | `plan_id`, `year`, `semester` | `200` (List of ElectiveSlotResponse) | `503` (DB offline) |
| `/api/plan` | GET | `program_id`, `plan_id`, `year`, `semester` | `200` (List of PlanItemResponse จาก `v_plan`) | `503` (DB offline) |
| `/api/plan/summary` | GET | `program_id`, `plan_id`, `year`, `semester` | `200` (List of PlanSummaryResponse จาก `v_semester_credits`) | `503` (DB offline) |
| `/api/regulations` | GET | `category`, `search`, `limit` | `200` (List of RegulationResponse) | `503` (DB offline) |
| `/api/health` | GET | - | `200` (`status`, `database_ready`, `ollama_ready`, `model`) | `200` (Status degraded if not ready) |

> ดูรายละเอียดสัญญา API Contract และตัวอย่าง payload ฉบับสมบูรณ์ได้ที่ [lab10_fastapi/curriculum_app/README.md](lab10_fastapi/curriculum_app/README.md)

