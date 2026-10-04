/**
 * Course Management Client Application (Lab 11 standard)
 * จัดการหน้าเพิ่มรายวิชา (POST /api/courses) และค้นหารายวิชา (GET /api/courses)
 * รองรับการซิงค์ข้อมูลกับฐานข้อมูล SQLite และ AI แบบ Real-time
 */

// โหลดข้อมูลภาพรวมหลักสูตรเมื่อเปิดหน้าเว็บ
async function loadProgramInfo() {
  const badge = document.getElementById("program-badge");
  try {
    const res = await fetch("/api/program");
    if (!res.ok) throw new Error("ไม่สามารถโหลดข้อมูลหลักสูตร");
    const prog = await res.json();
    const id = prog.program_id || "DSBA";
    const credits = prog.total_credits || 135;
    const years = prog.years || 4;
    badge.textContent = `หลักสูตร ${id} • ${credits} หน่วยกิต (${years} ปี)`;
  } catch (err) {
    badge.textContent = "หลักสูตร DSBA • 135 หน่วยกิต";
  }
}

// โหลดและค้นหารายวิชา
let searchDebounceTimeout = null;

async function loadCourses(search = "") {
  const container = document.getElementById("courses-list");
  const countBadge = document.getElementById("courses-count-badge");

  try {
    const url = `/api/courses?search=${encodeURIComponent(search.trim())}&limit=100`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("โหลดรายวิชาไม่สำเร็จ");
    const courses = await res.json();

    countBadge.textContent = `${courses.length} วิชา`;

    if (!courses || courses.length === 0) {
      container.innerHTML = `
        <div class="py-8 text-center text-xs text-slate-400">
          ไม่พบรายวิชาที่ตรงกับคำค้นหา
        </div>
      `;
      return;
    }

    container.innerHTML = "";
    courses.forEach((c) => {
      const row = document.createElement("div");
      row.className = "py-3 flex items-start justify-between gap-3 hover:bg-slate-50/80 px-2 rounded-xl transition";

      // ข้อมูลด้านซ้าย: รหัส และ ชื่อวิชา
      const left = document.createElement("div");
      left.className = "min-w-0 flex-1";

      const titleLine = document.createElement("div");
      titleLine.className = "flex items-center gap-2 flex-wrap mb-0.5";

      const codeSpan = document.createElement("span");
      codeSpan.className = "px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-xs font-mono font-medium text-slate-800";
      codeSpan.textContent = c.code;

      const nameThSpan = document.createElement("span");
      nameThSpan.className = "text-xs font-semibold text-slate-900";
      nameThSpan.textContent = c.name_th || "-";

      titleLine.appendChild(codeSpan);
      titleLine.appendChild(nameThSpan);

      if (c.name_en) {
        const nameEnDiv = document.createElement("div");
        nameEnDiv.className = "text-[11px] text-slate-400 tracking-wide font-sans";
        nameEnDiv.textContent = c.name_en;
        left.appendChild(titleLine);
        left.appendChild(nameEnDiv);
      } else {
        left.appendChild(titleLine);
      }

      // ข้อมูลด้านขวา: หน่วยกิต และ ชั่วโมง
      const right = document.createElement("div");
      right.className = "flex items-center gap-2 flex-shrink-0 text-right";

      const creditsSpan = document.createElement("span");
      creditsSpan.className = "text-xs font-medium text-slate-700";
      creditsSpan.textContent = `${c.credits} หน่วยกิต`;

      const hoursSpan = document.createElement("span");
      hoursSpan.className = "text-[11px] text-slate-400 font-mono hidden sm:inline";
      hoursSpan.textContent = `(${c.lecture_h ?? 0}-${c.lab_h ?? 0}-${c.self_h ?? 0})`;

      const checkLink = document.createElement("a");
      checkLink.href = `/?check=${encodeURIComponent(c.code)}`;
      checkLink.className = "px-2 py-1 rounded-lg border border-slate-200 hover:border-slate-400 text-[11px] text-slate-600 hover:text-slate-900 bg-white transition";
      checkLink.textContent = "เงื่อนไข";

      right.appendChild(creditsSpan);
      right.appendChild(hoursSpan);
      right.appendChild(checkLink);

      row.appendChild(left);
      row.appendChild(right);
      container.appendChild(row);
    });
  } catch (err) {
    container.innerHTML = `
      <div class="py-6 text-center text-xs text-red-500">
        เกิดข้อผิดพลาดในการโหลดรายวิชา
      </div>
    `;
  }
}

// จัดการการส่งฟอร์มเพิ่มวิชาใหม่ (POST /api/courses)
async function handleCreateCourse(event) {
  event.preventDefault();

  const btn = document.getElementById("save-course-btn");
  const loadingBox = document.getElementById("create-loading-box");
  const successBox = document.getElementById("create-success-box");
  const errorBox = document.getElementById("create-error-box");
  const successMsg = document.getElementById("create-success-msg");
  const errorTitle = document.getElementById("create-error-title");
  const errorMsg = document.getElementById("create-error-msg");

  // Reset feedback
  loadingBox.classList.remove("hidden");
  successBox.classList.add("hidden");
  errorBox.classList.add("hidden");
  btn.disabled = true;

  const form = event.target;
  const payload = {
    code: form.code.value.trim(),
    name_th: form.name_th.value.trim(),
    name_en: form.name_en.value.trim() || null,
    credits: parseInt(form.credits.value, 10),
    lecture_h: form.lecture_h.value ? parseInt(form.lecture_h.value, 10) : null,
    lab_h: form.lab_h.value ? parseInt(form.lab_h.value, 10) : null,
    self_h: form.self_h.value ? parseInt(form.self_h.value, 10) : null,
    description_th: form.description_th.value.trim() || null,
  };

  try {
    const res = await fetch("/api/courses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    loadingBox.classList.add("hidden");
    btn.disabled = false;

    if (res.status === 201) {
      // เพิ่มสำเร็จ
      successMsg.textContent = `เพิ่มวิชา ${data.code} (${data.name_th}) จำนวน ${data.credits} หน่วยกิต เข้าฐานข้อมูล SQLite เรียบร้อยแล้ว`;
      successBox.classList.remove("hidden");

      // รีเซ็ตฟอร์ม
      form.reset();
      form.credits.value = 3;
      form.lecture_h.value = 2;
      form.lab_h.value = 2;
      form.self_h.value = 5;

      // โหลดรายการวิชาใหม่เพื่อให้เห็นวิชาที่เพิ่งเพิ่มทันที
      loadCourses();
    } else if (res.status === 409) {
      errorTitle.textContent = "รหัสวิชาซ้ำ";
      errorMsg.textContent = data.detail || "รหัสวิชานี้มีอยู่แล้วในฐานข้อมูลหลักสูตร";
      errorBox.classList.remove("hidden");
    } else if (res.status === 422) {
      errorTitle.textContent = "ข้อมูลไม่ถูกต้องตามเกณฑ์";
      errorMsg.textContent = "กรุณาตรวจสอบว่ารหัสวิชาเป็นตัวเลข 8 หลัก และจำนวนหน่วยกิตอยู่ระหว่าง 0 ถึง 12";
      errorBox.classList.remove("hidden");
    } else {
      errorTitle.textContent = "เกิดข้อผิดพลาดในการบันทึก";
      errorMsg.textContent = data.detail || "เซิร์ฟเวอร์ปฏิเสธคำขอ";
      errorBox.classList.remove("hidden");
    }
  } catch (err) {
    loadingBox.classList.add("hidden");
    btn.disabled = false;
    errorTitle.textContent = "การเชื่อมต่อขัดข้อง";
    errorMsg.textContent = "ไม่สามารถติดต่อ API ได้ กรุณาตรวจสอบว่าเซิร์ฟเวอร์ FastAPI กำลังทำงานอยู่";
    errorBox.classList.remove("hidden");
  }
}

// เชื่อมต่อ Event Listeners เมื่อ DOM พร้อม
document.addEventListener("DOMContentLoaded", () => {
  loadProgramInfo();
  loadCourses();

  const searchInput = document.getElementById("search-courses-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      clearTimeout(searchDebounceTimeout);
      searchDebounceTimeout = setTimeout(() => {
        loadCourses(e.target.value);
      }, 250);
    });
  }

  const form = document.getElementById("create-course-form");
  if (form) {
    form.addEventListener("submit", handleCreateCourse);
  }
});
