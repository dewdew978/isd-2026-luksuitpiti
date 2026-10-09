/**
 * Course Management & Study Plan Client Application
 * รองรับการดูแผนการศึกษา (Study Plan) ทั้งแบบสหกิจ/ไม่สหกิจ (Option 2: Full Separation)
 * แสดงวิชาเลือก (Elective Slots), การค้นหารายวิชา, และการเพิ่มรายวิชาใหม่
 */

const PAGE_SIZE = 50;
let searchDebounceTimeout = null;
let currentProgram = "";
let currentSearch = "";
let currentOffset = 0;
let totalLoadedCount = 0;

// State สำหรับหน้าแผนการศึกษา
let activePlanProgram = "DSBA";
let activePlanId = "";
let programsCache = {};

// ==============================================================================
//  ส่วนที่ 1 — แท็บและโหมดการแสดงผล (Tab Switching)
// ==============================================================================

function switchTab(tabName) {
  const dirBtn = document.getElementById("tab-directory-btn");
  const addBtn = document.getElementById("tab-add-btn");

  const secDir = document.getElementById("section-directory");
  const secAdd = document.getElementById("section-add");

  const allBtns = [dirBtn, addBtn];
  allBtns.forEach((b) => {
    if (b) {
      b.className = "px-4 py-2 text-xs sm:text-sm font-medium rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition flex items-center gap-1.5";
    }
  });

  if (secDir) secDir.classList.add("hidden");
  if (secAdd) secAdd.classList.add("hidden");

  if (tabName === "directory") {
    if (dirBtn) dirBtn.className = "px-4 py-2 text-xs sm:text-sm font-semibold rounded-xl bg-slate-900 text-white transition shadow-xs flex items-center gap-1.5";
    if (secDir) secDir.classList.remove("hidden");
  } else if (tabName === "add") {
    if (addBtn) addBtn.className = "px-4 py-2 text-xs sm:text-sm font-semibold rounded-xl bg-slate-900 text-white transition shadow-xs flex items-center gap-1.5";
    if (secAdd) secAdd.classList.remove("hidden");
  }
}

// ==============================================================================
//  ส่วนที่ 2 — แผนการศึกษา (Study Plans & Elective Slots)
// ==============================================================================

async function loadProgramsMetadata() {
  try {
    const res = await fetch("/api/programs");
    if (!res.ok) return;
    const list = await res.json();
    list.forEach((p) => {
      programsCache[p.program_id] = p;
    });
  } catch (err) {
    console.error("Failed to load programs metadata", err);
  }
}

async function loadStudyPlansForProgram(progId) {
  activePlanProgram = progId;
  const container = document.getElementById("plan-selector-container");
  const summaryTitle = document.getElementById("plan-info-title");
  const summarySub = document.getElementById("plan-info-subtitle");
  const creditsBadge = document.getElementById("plan-total-credits-badge");
  const typeBadge = document.getElementById("plan-type-badge");
  const semestersContainer = document.getElementById("plan-semesters-container");

  if (container) {
    container.innerHTML = `<span class="text-xs text-slate-400">กำลังโหลดแผนการศึกษา...</span>`;
  }

  try {
    const res = await fetch(`/api/study-plans?program_id=${encodeURIComponent(progId)}`);
    if (!res.ok) throw new Error("โหลดแผนการศึกษาไม่สำเร็จ");
    const plans = await res.json();

    if (!plans || plans.length === 0) {
      if (container) container.innerHTML = `<span class="text-xs text-slate-400">ไม่พบแผนการศึกษาสำหรับสาขานี้</span>`;
      return;
    }

    if (container) {
      container.innerHTML = "";
      plans.forEach((p, idx) => {
        const btn = document.createElement("button");
        btn.type = "button";
        const isActive = (idx === 0);
        btn.className = `chip ${isActive ? "active" : ""}`;
        btn.setAttribute("data-plan-id", p.plan_id);
        btn.textContent = `${p.name_th} (${p.plan_type === "coop" ? "สหกิจ" : p.plan_type === "no_coop" ? "ไม่สหกิจ" : "ปกติ"})`;
        btn.onclick = () => selectPlan(p.plan_id, plans);
        container.appendChild(btn);
      });
    }

    // เลือกแผนแรกเป็นค่าเริ่มต้น
    activePlanId = plans[0].plan_id;
    updatePlanSummaryUI(plans[0]);
    loadPlanDetails(activePlanId);
  } catch (err) {
    if (semestersContainer) {
      semestersContainer.innerHTML = `<div class="p-6 text-center text-xs text-rose-500 bg-white rounded-2xl border border-slate-200">เกิดข้อผิดพลาดในการโหลดข้อมูลแผน</div>`;
    }
  }
}

function selectPlan(planId, plansList) {
  activePlanId = planId;
  const buttons = document.querySelectorAll("#plan-selector-container .chip");
  buttons.forEach((b) => {
    b.classList.toggle("active", b.getAttribute("data-plan-id") === planId);
  });
  const currentPlan = plansList.find((p) => p.plan_id === planId);
  if (currentPlan) {
    updatePlanSummaryUI(currentPlan);
  }
  loadPlanDetails(planId);
}

function updatePlanSummaryUI(planObj) {
  const prog = programsCache[planObj.program_id] || {};
  const summaryTitle = document.getElementById("plan-info-title");
  const summarySub = document.getElementById("plan-info-subtitle");
  const creditsBadge = document.getElementById("plan-total-credits-badge");
  const typeBadge = document.getElementById("plan-type-badge");

  if (summaryTitle) {
    summaryTitle.textContent = `${prog.name_th || planObj.program_id} — ${planObj.name_th}`;
  }
  if (summarySub) {
    summarySub.textContent = `${prog.degree || ""} • ระยะเวลาศึกษา ${prog.years || 4} ปี • ${planObj.name_en || ""}`;
  }
  if (creditsBadge) {
    creditsBadge.textContent = `${prog.total_credits || "--"} หน่วยกิต (ตลอดหลักสูตร)`;
  }
  if (typeBadge) {
    if (planObj.plan_type === "coop") {
      typeBadge.textContent = "แผนสหกิจศึกษา";
      typeBadge.className = "px-2.5 py-1 bg-amber-100 text-amber-800 border border-amber-200 rounded-lg font-medium";
    } else if (planObj.plan_type === "no_coop") {
      typeBadge.textContent = "แผนปกติ (ไม่สหกิจ)";
      typeBadge.className = "px-2.5 py-1 bg-blue-100 text-blue-800 border border-blue-200 rounded-lg font-medium";
    } else {
      typeBadge.textContent = "แผนการศึกษา";
      typeBadge.className = "px-2.5 py-1 bg-slate-100 text-slate-800 border border-slate-200 rounded-lg font-medium";
    }
  }
}

async function loadPlanDetails(planId) {
  const container = document.getElementById("plan-semesters-container");
  if (!container) return;

  container.innerHTML = `
    <div class="py-12 text-center text-xs text-slate-400 bg-white rounded-2xl border border-slate-200 flex items-center justify-center gap-2">
      <span class="w-3.5 h-3.5 border-2 border-slate-400 border-t-transparent rounded-full animate-spin"></span>
      <span>กำลังโหลดรายวิชาและหน่วยกิตตามภาคเรียน...</span>
    </div>
  `;

  try {
    const [itemsRes, summaryRes] = await Promise.all([
      fetch(`/api/plan?plan_id=${encodeURIComponent(planId)}`),
      fetch(`/api/plan/summary?plan_id=${encodeURIComponent(planId)}`),
    ]);

    if (!itemsRes.ok || !summaryRes.ok) throw new Error("โหลดข้อมูลรายวิชาในแผนไม่สำเร็จ");

    const items = await itemsRes.json();
    const summaries = await summaryRes.json();

    const sumMap = {};
    summaries.forEach((s) => {
      sumMap[`${s.year}/${s.semester}`] = s;
    });

    // จัดกลุ่มตาม year/semester
    const semMap = {};
    items.forEach((it) => {
      const key = `${it.year}/${it.semester}`;
      if (!semMap[key]) semMap[key] = [];
      semMap[key].push(it);
    });

    const semKeys = Object.keys(semMap).sort((a, b) => {
      const [y1, s1] = a.split("/").map(Number);
      const [y2, s2] = b.split("/").map(Number);
      return (y1 * 10 + s1) - (y2 * 10 + s2);
    });

    if (semKeys.length === 0) {
      container.innerHTML = `<div class="p-8 text-center text-xs text-slate-400 bg-white rounded-2xl border border-slate-200">ยังไม่มีข้อมูลรายวิชาในแผนนี้</div>`;
      return;
    }

    container.innerHTML = "";

    semKeys.forEach((key) => {
      const [year, semester] = key.split("/").map(Number);
      const semCourses = semMap[key];
      const sum = sumMap[key];
      const semTotalCr = sum ? sum.credits : semCourses.reduce((acc, c) => acc + (c.credits || 0), 0);

      const semCard = document.createElement("div");
      semCard.className = "bg-white rounded-2xl border border-slate-200/90 overflow-hidden shadow-xs";

      // Card Header
      const header = document.createElement("div");
      header.className = "bg-slate-50/80 px-5 py-3 border-b border-slate-200/80 flex items-center justify-between";
      header.innerHTML = `
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-slate-900"></span>
          <span class="font-bold text-xs sm:text-sm text-slate-900">ปีที่ ${year} ภาคการศึกษาที่ ${semester === 3 ? "ฤดูร้อน" : semester}</span>
        </div>
        <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-white border border-slate-200 text-slate-800 shadow-2xs">
          ${semTotalCr} หน่วยกิต
        </span>
      `;
      semCard.appendChild(header);

      // List of courses & elective slots
      const list = document.createElement("div");
      list.className = "divide-y divide-slate-100 p-2 sm:p-3";

      semCourses.forEach((c) => {
        const itemRow = document.createElement("div");
        itemRow.className = "py-2.5 px-3 flex items-start justify-between gap-3 hover:bg-slate-50/80 rounded-xl transition";

        const left = document.createElement("div");
        left.className = "min-w-0 flex-1";

        const titleLine = document.createElement("div");
        titleLine.className = "flex items-center gap-2 flex-wrap mb-0.5";

        if (c.is_elective_slot === 1) {
          // วิชาเลือก (Elective Slot)
          const slotTag = document.createElement("span");
          slotTag.className = "px-2 py-0.5 bg-indigo-50 border border-indigo-200 text-indigo-700 rounded text-[11px] font-medium";
          slotTag.textContent = "วิชาเลือก";
          titleLine.appendChild(slotTag);

          const codeSpan = document.createElement("span");
          codeSpan.className = "px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-xs font-mono font-medium text-slate-700";
          codeSpan.textContent = c.code;
          titleLine.appendChild(codeSpan);

          const nameTh = document.createElement("span");
          nameTh.className = "text-xs font-semibold text-slate-900";
          nameTh.textContent = c.name_th || c.code;
          titleLine.appendChild(nameTh);
        } else {
          // วิชาจริง 8 หลัก (Real Course)
          const codeSpan = document.createElement("span");
          codeSpan.className = "px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-xs font-mono font-bold text-slate-900";
          codeSpan.textContent = c.code;
          titleLine.appendChild(codeSpan);

          if (c.alt_group) {
            const altTag = document.createElement("span");
            altTag.className = "px-1.5 py-0.5 bg-amber-50 border border-amber-200 text-amber-800 rounded text-[10px] font-medium";
            altTag.textContent = "วิชาทางเลือก";
            titleLine.appendChild(altTag);
          }

          const nameTh = document.createElement("span");
          nameTh.className = "text-xs font-semibold text-slate-900";
          nameTh.textContent = c.name_th || "-";
          titleLine.appendChild(nameTh);
        }

        left.appendChild(titleLine);

        if (c.name_en) {
          const nameEn = document.createElement("div");
          nameEn.className = "text-[11px] text-slate-400 tracking-wide font-sans pl-0.5";
          nameEn.textContent = c.name_en;
          left.appendChild(nameEn);
        }

        // Right side: Credits and check prerequisite
        const right = document.createElement("div");
        right.className = "flex items-center gap-2 flex-shrink-0 text-right";

        const crSpan = document.createElement("span");
        crSpan.className = "text-xs font-medium text-slate-800";
        crSpan.textContent = `${c.credits} หน่วยกิต`;
        right.appendChild(crSpan);

        if (c.is_elective_slot === 0) {
          const preBtn = document.createElement("a");
          preBtn.href = `/?check=${encodeURIComponent(c.code)}`;
          preBtn.className = "px-2 py-1 rounded-lg border border-slate-200 hover:border-slate-400 text-[11px] text-slate-600 hover:text-slate-900 bg-white transition shadow-2xs";
          preBtn.textContent = "เงื่อนไข";
          preBtn.title = "ตรวจสอบวิชาบังคับก่อน";
          right.appendChild(preBtn);
        }

        itemRow.appendChild(left);
        itemRow.appendChild(right);
        list.appendChild(itemRow);
      });

      semCard.appendChild(list);
      container.appendChild(semCard);
    });
  } catch (err) {
    container.innerHTML = `<div class="p-6 text-center text-xs text-rose-500 bg-white rounded-2xl border border-slate-200">ไม่สามารถโหลดข้อมูลรายวิชาได้</div>`;
  }
}

// ==============================================================================
//  ส่วนที่ 3 — สารบัญรายวิชาทั้งหมด (Course Directory)
// ==============================================================================

async function loadCourses(search = "", program_id = "", append = false) {
  currentSearch = search;
  currentProgram = program_id;

  const container = document.getElementById("courses-list");
  const countBadge = document.getElementById("courses-count-badge");
  const loadMoreBox = document.getElementById("load-more-container");
  const loadMoreBtn = document.getElementById("load-more-btn");
  if (!container) return;

  if (!append) {
    currentOffset = 0;
    totalLoadedCount = 0;
    container.innerHTML = `
      <div class="py-8 text-center text-xs text-slate-400">
        กำลังโหลดข้อมูล...
      </div>
    `;
  }

  if (loadMoreBtn) {
    loadMoreBtn.disabled = true;
    loadMoreBtn.innerHTML = `<span>กำลังโหลด...</span>`;
  }

  try {
    let url = `/api/courses?search=${encodeURIComponent(search.trim())}&limit=${PAGE_SIZE}&offset=${currentOffset}`;
    if (program_id && program_id.trim() && program_id.trim() !== "ALL") {
      url += `&program_id=${encodeURIComponent(program_id.trim())}`;
    }

    const res = await fetch(url);
    if (!res.ok) throw new Error("โหลดรายวิชาไม่สำเร็จ");
    const courses = await res.json();

    if (!append) {
      container.innerHTML = "";
    }

    if (!courses || courses.length === 0) {
      if (!append) {
        container.innerHTML = `
          <div class="py-8 text-center text-xs text-slate-400">
            ไม่พบรายวิชาที่ตรงกับคำค้นหา
          </div>
        `;
      }
      if (loadMoreBox) loadMoreBox.classList.add("hidden");
      if (countBadge) countBadge.textContent = `${totalLoadedCount} วิชา`;
      return;
    }

    totalLoadedCount += courses.length;
    if (countBadge) {
      countBadge.textContent = `แสดง ${totalLoadedCount} วิชา`;
    }

    courses.forEach((c) => {
      const row = document.createElement("div");
      row.className = "py-3 flex items-start justify-between gap-3 hover:bg-slate-50/80 px-2 rounded-xl transition";

      const left = document.createElement("div");
      left.className = "min-w-0 flex-1";

      const titleLine = document.createElement("div");
      titleLine.className = "flex items-center gap-1.5 flex-wrap mb-1";

      const codeSpan = document.createElement("span");
      codeSpan.className = "px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-xs font-mono font-medium text-slate-800";
      codeSpan.textContent = c.code;
      titleLine.appendChild(codeSpan);

      if (c.programs && c.programs.length > 0) {
        c.programs.forEach((prog) => {
          const progSpan = document.createElement("span");
          progSpan.className = "px-1.5 py-0.5 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded text-[10px] font-mono text-slate-600 cursor-pointer transition";
          progSpan.textContent = prog;
          progSpan.title = `คลิกเพื่อกรองดูเฉพาะสาขา ${prog}`;
          progSpan.onclick = () => filterByProgram(prog);
          titleLine.appendChild(progSpan);
        });
      }

      const nameThSpan = document.createElement("span");
      nameThSpan.className = "text-xs font-semibold text-slate-900 ml-0.5";
      nameThSpan.textContent = c.name_th || "-";
      titleLine.appendChild(nameThSpan);

      left.appendChild(titleLine);

      if (c.name_en) {
        const nameEnDiv = document.createElement("div");
        nameEnDiv.className = "text-[11px] text-slate-400 tracking-wide font-sans";
        nameEnDiv.textContent = c.name_en;
        left.appendChild(nameEnDiv);
      }

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
      checkLink.className = "px-2 py-1 rounded-lg border border-slate-200 hover:border-slate-400 text-[11px] text-slate-600 hover:text-slate-900 bg-white transition shadow-2xs";
      checkLink.textContent = "เงื่อนไข";

      right.appendChild(creditsSpan);
      right.appendChild(hoursSpan);
      right.appendChild(checkLink);

      row.appendChild(left);
      row.appendChild(right);
      container.appendChild(row);
    });

    if (loadMoreBox) {
      if (courses.length === PAGE_SIZE) {
        loadMoreBox.classList.remove("hidden");
        if (loadMoreBtn) {
          loadMoreBtn.disabled = false;
          loadMoreBtn.innerHTML = `
            <span>โหลดเพิ่มเติม (+50 วิชา)</span>
            <svg class="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
          `;
        }
      } else {
        loadMoreBox.classList.add("hidden");
      }
    }
  } catch (err) {
    if (!append) {
      container.innerHTML = `
        <div class="py-6 text-center text-xs text-rose-500">
          เกิดข้อผิดพลาดในการโหลดรายวิชา
        </div>
      `;
    }
    if (loadMoreBox) loadMoreBox.classList.add("hidden");
  }
}

function filterByProgram(prog) {
  const chips = document.querySelectorAll("#program-filter-chips .chip");
  chips.forEach((c) => {
    c.classList.toggle("active", c.getAttribute("data-program") === prog);
  });
  loadCourses(currentSearch, prog, false);
}

// ==============================================================================
//  ส่วนที่ 4 — ฟอร์มเพิ่มวิชาใหม่ (Add Course Form)
// ==============================================================================

async function handleCreateCourse(event) {
  event.preventDefault();

  const btn = document.getElementById("save-course-btn");
  const loadingBox = document.getElementById("create-loading-box");
  const successBox = document.getElementById("create-success-box");
  const errorBox = document.getElementById("create-error-box");
  const successMsg = document.getElementById("create-success-msg");
  const errorTitle = document.getElementById("create-error-title");
  const errorMsg = document.getElementById("create-error-msg");

  loadingBox.classList.remove("hidden");
  successBox.classList.add("hidden");
  errorBox.classList.add("hidden");
  btn.disabled = true;

  const form = event.target;
  const programIdVal = form.program_id ? form.program_id.value.trim() : "";
  const planIdVal = form.plan_id ? form.plan_id.value.trim() : "";
  const yearVal = form.year && form.year.value ? parseInt(form.year.value, 10) : null;
  const semesterVal = form.semester && form.semester.value ? parseInt(form.semester.value, 10) : null;

  const payload = {
    code: form.code.value.trim(),
    name_th: form.name_th.value.trim(),
    name_en: form.name_en.value.trim() || null,
    credits: parseInt(form.credits.value, 10),
    lecture_h: form.lecture_h.value ? parseInt(form.lecture_h.value, 10) : null,
    lab_h: form.lab_h.value ? parseInt(form.lab_h.value, 10) : null,
    self_h: form.self_h.value ? parseInt(form.self_h.value, 10) : null,
    description_th: form.description_th.value.trim() || null,
    program_id: programIdVal || null,
    plan_id: planIdVal || null,
    year: yearVal,
    semester: semesterVal,
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
      const progInfo = payload.program_id ? ` (สาขา ${payload.program_id} แผน ${payload.plan_id || '-'} ปี ${payload.year} เทอม ${payload.semester})` : "";
      successMsg.textContent = `เพิ่มวิชา ${data.code} (${data.name_th})${progInfo} จำนวน ${data.credits} หน่วยกิต เข้าฐานข้อมูล SQLite เรียบร้อยแล้ว`;
      successBox.classList.remove("hidden");

      form.reset();
      form.credits.value = 3;
      form.lecture_h.value = 2;
      form.lab_h.value = 2;
      form.self_h.value = 5;
      updateCoursePlanOptions("");

      loadCourses(currentSearch, currentProgram);
      if (payload.program_id === activePlanProgram) {
        loadPlanDetails(activePlanId);
      }
    } else if (res.status === 409) {
      errorTitle.textContent = "รหัสวิชาซ้ำ";
      errorMsg.textContent = data.detail || "รหัสวิชานี้มีอยู่แล้วในฐานข้อมูลหลักสูตร";
      errorBox.classList.remove("hidden");
    } else if (res.status === 422) {
      errorTitle.textContent = "ข้อมูลไม่ถูกต้องตามเกณฑ์";
      if (typeof data.detail === "string") {
        errorMsg.textContent = data.detail;
      } else if (Array.isArray(data.detail)) {
        errorMsg.textContent = data.detail.map(d => d.msg || JSON.stringify(d)).join(", ");
      } else {
        errorMsg.textContent = "กรุณาตรวจสอบว่ารหัสวิชาเป็นตัวเลข 8 หลัก และจำนวนหน่วยกิตอยู่ระหว่าง 0 ถึง 12";
      }
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

function updateCoursePlanOptions(progId) {
  const planContainer = document.getElementById("course-plan-container");
  const planSelect = document.getElementById("course-plan");
  if (!planContainer || !planSelect) return;

  planSelect.innerHTML = "";
  if (!progId) {
    planContainer.classList.add("hidden");
    return;
  }

  const planOptions = {
    "DSBA": [
      { id: "DSBA_NON_COOP", name: "DSBA — แผนปกติ (ไม่ไปสหกิจศึกษา)" },
      { id: "DSBA_COOP", name: "DSBA — แผนสหกิจศึกษา" }
    ],
    "BIT": [
      { id: "BIT_NON_COOP", name: "BIT — แผนปกติ (ไม่ไปสหกิจศึกษา)" },
      { id: "BIT_COOP", name: "BIT — แผนสหกิจศึกษา" }
    ],
    "IT": [
      { id: "IT_NON_COOP", name: "IT — แผนปกติ (ไม่ไปสหกิจศึกษา)" },
      { id: "IT_COOP", name: "IT — แผนสหกิจศึกษา" }
    ],
    "AIT": [
      { id: "AIT_SINGLE", name: "AIT — แผนการศึกษา 4 ปี (AIT_SINGLE)" }
    ]
  };

  const list = planOptions[progId] || [];
  if (list.length > 0) {
    list.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      planSelect.appendChild(opt);
    });
    planContainer.classList.remove("hidden");
  } else {
    planContainer.classList.add("hidden");
  }
}

// ==============================================================================
//  ส่วนที่ 5 — เริ่มต้นระบบเมื่อโหลด DOM (Initialization)
// ==============================================================================

document.addEventListener("DOMContentLoaded", async () => {
  // 1. โหลดข้อมูลหลักสูตรและรายวิชา
  await loadProgramsMetadata();
  loadCourses();

  // 2. Tab Buttons
  document.getElementById("tab-directory-btn")?.addEventListener("click", () => switchTab("directory"));
  document.getElementById("tab-add-btn")?.addEventListener("click", () => switchTab("add"));

  // 4. Directory Search Input with debounce
  const searchInput = document.getElementById("search-courses-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      clearTimeout(searchDebounceTimeout);
      searchDebounceTimeout = setTimeout(() => {
        loadCourses(e.target.value, currentProgram);
      }, 250);
    });
  }

  // 5. Directory Program Filter Chips
  const filterChips = document.querySelectorAll("#program-filter-chips .chip");
  filterChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      filterChips.forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      const prog = chip.getAttribute("data-program") || "";
      loadCourses(currentSearch, prog);
    });
  });

  // 6. Create course form & plan dropdown listener
  const courseProgSelect = document.getElementById("course-program");
  if (courseProgSelect) {
    courseProgSelect.addEventListener("change", (e) => {
      updateCoursePlanOptions(e.target.value);
    });
    if (courseProgSelect.value) {
      updateCoursePlanOptions(courseProgSelect.value);
    }
  }

  const form = document.getElementById("create-course-form");
  if (form) {
    form.addEventListener("submit", handleCreateCourse);
  }

  // 7. Load more button
  const loadMoreBtn = document.getElementById("load-more-btn");
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener("click", () => {
      currentOffset += PAGE_SIZE;
      loadCourses(currentSearch, currentProgram, true);
    });
  }
});
