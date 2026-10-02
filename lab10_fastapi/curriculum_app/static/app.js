/**
 * Curriculum Assistant Client Application (Lab 11)
 * ควบคุมสถานะ UI 4 ขั้นตอน: Idle, Loading, Success, Error
 * ปฏิบัติตามแนวทาง Best Practice:
 * - ใช้ async/await และ try/catch พร้อมตรวจสอบ response.ok
 * - ควบคุมผ่าน State และ Class แทนการแก้ inline styles ทีละบรรทัด
 * - ใช้ textContent สำหรับข้อความจากโมเดลเพื่อป้องกัน XSS
 */

// นิยาม 4 สถานะของระบบ AI UI ตาม Lab 11
const UI_STATE = {
  IDLE: "idle",
  LOADING: "loading",
  SUCCESS: "success",
  ERROR: "error",
};

/**
 * จัดการสถานะ UI ของส่วนถาม-ตอบ AI (Text-to-SQL)
 * @param {string} state - สถานะปัจจุบัน (idle, loading, success, error)
 * @param {object} payload - ข้อมูลประกอบสถานะ (answer, sql, rows, errorMsg, errorAction)
 */
function setAskState(state, payload = {}) {
  const btn = document.getElementById("ask-btn");
  const idleBox = document.getElementById("ask-idle-box");
  const loadingBox = document.getElementById("ask-loading-box");
  const successBox = document.getElementById("ask-success-box");
  const errorBox = document.getElementById("ask-error-box");

  // ซ่อนทุกกล่องก่อนเปลี่ยนสถานะ
  idleBox.style.display = "none";
  loadingBox.style.display = "none";
  successBox.style.display = "none";
  errorBox.style.display = "none";

  switch (state) {
    case UI_STATE.IDLE:
      idleBox.style.display = "flex";
      btn.disabled = false;
      btn.textContent = "ส่งคำถาม";
      break;

    case UI_STATE.LOADING:
      loadingBox.style.display = "flex";
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner"></span> กำลังคิด...`;
      break;

    case UI_STATE.SUCCESS:
      successBox.style.display = "block";
      btn.disabled = false;
      btn.textContent = "ส่งคำถาม";

      // แสดงคำตอบอย่างปลอดภัยด้วย textContent (ป้องกัน XSS ตามสไลด์หน้า 18)
      document.getElementById("answer-text").textContent =
        payload.answer || "ไม่มีข้อความตอบกลับ";
      document.getElementById("answer-sql").textContent = payload.sql || "-";
      document.getElementById("answer-rows").textContent = payload.rows
        ? JSON.stringify(payload.rows, null, 2)
        : "-";
      break;

    case UI_STATE.ERROR:
      errorBox.style.display = "block";
      btn.disabled = false;
      btn.textContent = "ส่งคำถาม";

      document.getElementById("ask-error-msg").textContent =
        payload.errorMsg || "เกิดข้อผิดพลาดในการประมวลผล";
      document.getElementById("ask-error-action").textContent =
        payload.errorAction ||
        "คำแนะนำ: ตรวจสอบว่าได้รัน Ollama และ uvicorn เรียบร้อยแล้ว หรือลองปรับคำถามให้กระชับขึ้น";
      break;
  }
}

/**
 * ตัวช่วยเลือกคำถามตัวอย่างจากชิป
 */
function setQuestion(questionText) {
  const textarea = document.getElementById("question");
  textarea.value = questionText;
  textarea.focus();
}

/**
 * ส่งคำถามไปยัง AI Text-to-SQL API (/api/ask)
 */
async function handleAskSubmit(event) {
  event.preventDefault();
  const questionInput = document.getElementById("question");
  const question = questionInput.value.trim();

  if (!question) {
    setAskState(UI_STATE.ERROR, {
      errorMsg: "กรุณาพิมพ์คำถามก่อนส่ง",
      errorAction: "คำแนะนำ: สามารถคลิกคำถามตัวอย่างด้านบนเพื่อเริ่มต้นได้",
    });
    return;
  }

  // เข้าสู่สถานะ Loading
  setAskState(UI_STATE.LOADING);

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    const data = await response.json();

    // fetch ถือว่าสำเร็จแม้ HTTP status 4xx/5xx จึงต้องเช็ก response.ok ตามสไลด์หน้า 14
    if (!response.ok) {
      throw new Error(data.detail || `HTTP Error ${response.status}`);
    }

    // เข้าสู่สถานะ Success
    setAskState(UI_STATE.SUCCESS, {
      answer: data.answer,
      sql: data.sql,
      rows: data.rows,
    });
  } catch (error) {
    // เข้าสู่สถานะ Error พร้อมบอกสิ่งที่เกิดขึ้นและคำแนะนำในการแก้ไข
    setAskState(UI_STATE.ERROR, {
      errorMsg: error.message,
      errorAction:
        "คำแนะนำ: ตรวจสอบว่า Ollama โมเดล qwen3:4b และฐานข้อมูล curriculum.db พร้อมใช้งาน หรือเปิดเช็คที่ /api/health",
    });
  }
}

/**
 * ค้นหาเงื่อนไขวิชาบังคับก่อน (Prerequisite Graph)
 * @param {string} code - รหัสวิชา 8 หลัก
 */
async function fetchPrereq(code) {
  const resultDiv = document.getElementById("prereq-result");
  const btn = document.getElementById("prereq-btn");

  if (!code) return;

  // 1. Loading State
  resultDiv.innerHTML = `
    <div class="state-box-loading">
      <span class="spinner"></span>
      <span>กำลังตรวจสอบเงื่อนไขวิชา ${escapeHtml(code)}...</span>
    </div>
  `;
  btn.disabled = true;

  try {
    const response = await fetch(`/api/courses/${encodeURIComponent(code)}/prerequisites`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || `ไม่พบข้อมูลรายวิชา ${code}`);
    }

    // 2. Success State
    const courseTitle = `${escapeHtml(data.code)} — ${escapeHtml(
      data.name_th || data.name_en || "-"
    )} ${data.credits != null ? `(${data.credits} หน่วยกิต)` : ""}`;

    let html = `<div class="prereq-course-header" style="background: none !important; border: none !important; padding: 0 !important; font-size: 15px; font-weight: 600; color: var(--text-main); margin-bottom: 16px;">${courseTitle}</div>`;

    // 1. Requires (วิชาที่ต้องเรียนมาก่อน)
    html += `
      <div class="prereq-group">
        <div class="prereq-group-title">1. วิชาที่ต้องเรียนมาก่อน (Requires)</div>`;
    if (data.requires && data.requires.length > 0) {
      html +=
        `<ul class="course-list">` +
        data.requires
          .map(
            (c) => `
          <li class="course-item">
            <div>
              <a href="javascript:void(0)" onclick="searchPrereq('${escapeHtml(c.code)}')">${escapeHtml(c.code)}</a>
              <span style="margin-left: 6px;">${escapeHtml(c.name_th || c.name_en || "")}</span>
              ${
                c.credits != null
                  ? `<span style="color: var(--text-muted); font-size: 12px;">(${c.credits} นก.)</span>`
                  : ""
              }
            </div>
            <span class="tag ${escapeHtml(c.kind)}">${escapeHtml(c.kind.toUpperCase())}</span>
          </li>
        `
          )
          .join("") +
        `</ul>`;
    } else {
      html += `<div class="empty-state">ไม่มีเงื่อนไขวิชาบังคับก่อน</div>`;
    }
    html += `</div>`;

    // 2. Required By (เป็นวิชาบังคับก่อนของ)
    html += `
      <div class="prereq-group">
        <div class="prereq-group-title">2. เป็นวิชาบังคับก่อนของ (Required By)</div>`;
    if (data.required_by && data.required_by.length > 0) {
      html +=
        `<ul class="course-list">` +
        data.required_by
          .map(
            (c) => `
          <li class="course-item">
            <div>
              <a href="javascript:void(0)" onclick="searchPrereq('${escapeHtml(c.code)}')">${escapeHtml(c.code)}</a>
              <span style="margin-left: 6px;">${escapeHtml(c.name_th || c.name_en || "")}</span>
              ${
                c.credits != null
                  ? `<span style="color: var(--text-muted); font-size: 12px;">(${c.credits} นก.)</span>`
                  : ""
              }
            </div>
            <span class="tag ${escapeHtml(c.kind)}">${escapeHtml(c.kind.toUpperCase())}</span>
          </li>
        `
          )
          .join("") +
        `</ul>`;
    } else {
      html += `<div class="empty-state">ไม่มีวิชาที่ต้องใช้วิชานี้เป็นวิชาบังคับก่อน</div>`;
    }
    html += `</div>`;

    resultDiv.innerHTML = html;
  } catch (error) {
    // 3. Error State
    resultDiv.innerHTML = `
      <div class="state-box-error">
        <div class="error-title">⚠️ ไม่สามารถดึงข้อมูลเงื่อนไขวิชาได้</div>
        <div class="error-message">${escapeHtml(error.message)}</div>
        <div class="error-action">คำแนะนำ: ตรวจสอบความถูกต้องของรหัสวิชา (ต้องเป็นตัวเลข 8 หลัก เช่น 06026201)</div>
      </div>
    `;
  } finally {
    btn.disabled = false;
  }
}

/**
 * ตัวช่วย escape ข้อความ HTML
 */
function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function searchPrereq(code) {
  const input = document.getElementById("course-code");
  if (input) {
    input.value = code;
    fetchPrereq(code);
  }
}

// ตั้งค่า Event Listeners เมื่อ DOM พร้อมทำงาน
document.addEventListener("DOMContentLoaded", () => {
  const askForm = document.getElementById("ask-form");
  const questionInput = document.getElementById("question");
  const prereqForm = document.getElementById("prereq-form");

  if (askForm) {
    askForm.addEventListener("submit", handleAskSubmit);
  }

  // รองรับคีย์ลัด Ctrl + Enter / Cmd + Enter
  if (questionInput) {
    questionInput.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        askForm.requestSubmit();
      }
    });
  }

  if (prereqForm) {
    prereqForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const code = document.getElementById("course-code").value.trim();
      fetchPrereq(code);
    });
  }

  // เริ่มต้นที่สถานะ Idle
  setAskState(UI_STATE.IDLE);
});
