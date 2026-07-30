import json
import glob

merged_gt = {}

# กำหนด Path ที่เก็บไฟล์ Ground Truth ทั้งหมด
for file_name in glob.glob("data/ground_truth/*.json"):
    with open(file_name, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # ตรวจสอบและรวมข้อมูล (ปรับโครงสร้างตามไฟล์จริง)
        if isinstance(data, dict):
            merged_gt.update(data)

# บันทึกเป็นไฟล์ใหม่เพื่อนำไปใช้รัน CLI
with open("data/ground_truth/merged_ground_truth.json", 'w', encoding='utf-8') as f:
    json.dump(merged_gt, f, ensure_ascii=False, indent=4)