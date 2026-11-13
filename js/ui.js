/* =================================================================
   ui.js — 공통 UI 헬퍼
   · 접근성: role=switch / radiogroup / dialog / aria-live 토스트 / 필드 오류 연결
   · prompt()/confirm() 대신 <dialog> 기반 확인창
================================================================= */
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const el = h => { const t = document.createElement("template"); t.innerHTML = h.trim(); return t.content.firstElementChild; };
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const initial = n => (n || "?").trim().charAt(0);
const p2 = n => String(n).padStart(2, "0");
const plural = (n, unit) => `${n}${unit}`;

/* ---------- 날짜 ---------- */
const fmtDate = iso => { if (!iso) return "—"; const d = new Date(iso); return `${d.getFullYear()}.${p2(d.getMonth() + 1)}.${p2(d.getDate())}`; };
const fmtDT = iso => { if (!iso) return "—"; const d = new Date(iso); return `${p2(d.getMonth() + 1)}.${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`; };
const toDateInput = iso => { const d = new Date(iso); return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`; };
function deadlineText(iso) {
  const t = new Date(iso).getTime(), now = Date.now();
  if (now > t) { const d = Math.floor((now - t) / DAY_MS); return { text: d === 0 ? "오늘 마감됨" : `마감 ${d}일 지남`, past: true }; }
  return { text: `D-${Math.ceil((t - now) / DAY_MS)}`, past: false };
}

/* ---------- 토스트 (aria-live) ---------- */
function toast(msg) {
  const t = $("#toast"); if (!t) return;
  t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 2800);
}

/* ---------- 클릭 가능한 카드 (키보드: Enter/Space) ---------- */
function makeClickable(node, fn, label) {
  node.setAttribute("role", "button"); node.tabIndex = 0;
  if (label) node.setAttribute("aria-label", label);
  node.onclick = fn;
  node.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(e); } };
}
function bindGo(scope) { $$("[data-go]", scope).forEach(b => b.onclick = () => nav(b.dataset.go)); }

/* ---------- 스위치 (진짜 버튼 + role=switch) ---------- */
function switchBtn({ on = false, label, onChange, disabled = false }) {
  const b = el(`<button type="button" class="switch" role="switch" aria-checked="${on}" aria-label="${esc(label)}" data-on="${on ? 1 : 0}" ${disabled ? "disabled" : ""}><i></i></button>`);
  b.onclick = () => { if (!b.disabled) onChange(b.getAttribute("aria-checked") !== "true"); };
  return b;
}

/* ---------- 1~5점 원형 선택 (radiogroup, 방향키 지원) ---------- */
function dotPicker({ value = 0, onChange, label, min = 1, max = 5 }) {
  const wrap = el(`<div class="dot-picker" role="radiogroup" aria-label="${esc(label)}"></div>`);
  const paint = () => $$(".dot", wrap).forEach(d => {
    const v = +d.dataset.v;
    d.classList.toggle("filled", v <= value); d.classList.toggle("sel", v === value);
    d.setAttribute("aria-checked", String(v === value)); d.tabIndex = (v === value || (!value && v === min)) ? 0 : -1;
  });
  const set = (v, focus) => { value = Math.max(min, Math.min(max, v)); paint(); if (focus) $(`.dot[data-v="${value}"]`, wrap).focus(); onChange(value); };
  for (let v = min; v <= max; v++) {
    const b = el(`<button type="button" class="dot" role="radio" data-v="${v}" aria-label="${v}점">${v}</button>`);
    b.onclick = () => set(v, false);
    b.onkeydown = e => {
      if (e.key === "ArrowRight" || e.key === "ArrowUp") { e.preventDefault(); set((value || min - 1) + 1, true); }
      else if (e.key === "ArrowLeft" || e.key === "ArrowDown") { e.preventDefault(); set((value || min + 1) - 1, true); }
    };
    wrap.append(b);
  }
  paint(); return wrap;
}

/* ---------- 확인 대화상자 (<dialog>) ---------- */
function confirmDialog({ title = "확인", message = "", okText = "확인", cancelText = "취소", danger = false, requireText = "" } = {}) {
  return new Promise(resolve => {
    const d = $("#dlg");
    if (!d || typeof d.showModal !== "function") { resolve(requireText ? window.prompt(`${title}\n\n${message}\n\n확인 문구 '${requireText}' 를 그대로 입력하세요`) === requireText : window.confirm(`${title}\n\n${message}`)); return; }
    d.innerHTML = `<form method="dialog" class="dlg-card"><h3 class="dlg-title">${esc(title)}</h3>
      <p class="dlg-msg">${esc(message).replace(/\n/g, "<br>")}</p>
      ${requireText ? `<label class="dlg-req" for="dlgTxt">확인 문구: <b>${esc(requireText)}</b> — 아래 칸에 그대로 입력하세요</label><input class="input" id="dlgTxt" autocomplete="off">` : ""}
      <div class="dlg-actions"><button class="btn btn-ghost" value="cancel">${esc(cancelText)}</button>
      <button class="btn ${danger ? "btn-danger" : ""}" value="ok" id="dlgOk" ${requireText ? "disabled" : "autofocus"}>${esc(okText)}</button></div></form>`;
    if (requireText) {
      const i = $("#dlgTxt", d), ok = $("#dlgOk", d);
      i.oninput = () => { ok.disabled = i.value.trim() !== requireText; };
      i.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); if (!ok.disabled) ok.click(); } }; // Enter가 '취소'로 제출되지 않게
      setTimeout(() => i.focus(), 0);
    }
    const done = () => { d.removeEventListener("close", done); resolve(d.returnValue === "ok"); };
    d.addEventListener("close", done); d.returnValue = "cancel";
    d.onclick = e => { if (e.target === d) d.close("cancel"); };
    d.showModal();
  });
}

/* ---------- 폼 오류 (aria-invalid + aria-describedby) ---------- */
function setErr(input, msg) {
  const host = input.closest(".field") || input.parentElement;
  let e = host.querySelector(".field-err");
  if (!e) { e = document.createElement("p"); e.className = "field-err"; e.id = (input.id || "f" + Math.random().toString(36).slice(2, 7)) + "-err"; host.append(e); }
  e.textContent = msg; input.setAttribute("aria-invalid", "true"); input.setAttribute("aria-describedby", e.id);
}
function clearErr(input) {
  const e = (input.closest(".field") || input.parentElement).querySelector(".field-err"); if (e) e.remove();
  input.removeAttribute("aria-invalid"); input.removeAttribute("aria-describedby");
}
function clearAllErr(scope) { $$("[aria-invalid]", scope).forEach(clearErr); }

/* ---------- 클립보드 / CSV ---------- */
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(String(text));
    else {
      const a = document.createElement("textarea"); a.value = String(text); a.setAttribute("readonly", "");
      a.style.cssText = "position:fixed;opacity:0"; document.body.append(a); a.select();
      const ok = document.execCommand("copy"); a.remove(); if (!ok) throw new Error("copy failed");
    }
    toast("클립보드에 복사했습니다."); return true;
  } catch (e) { toast("복사하지 못했습니다. 코드를 직접 선택해 복사해 주세요."); return false; }
}
function downloadCSV(filename, rows) {
  const csv = rows.map(r => r.map(v => {
    let s = String(v ?? "");
    if (/^[=+@\-\t\r]/.test(s)) s = "'" + s; // CSV 수식 주입 방지
    return '"' + s.replace(/"/g, '""') + '"';
  }).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8;" }));
  const a = document.createElement("a"); a.href = url; a.download = filename; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000); toast("CSV 파일을 다운로드했습니다.");
}

/* ---------- 시간표 표현 ---------- */
const slotLabel = k => { const [d, i] = k.split("-"); return `${d} ${BLOCKS[+i][0]}시`; };
/** members: [{sched:[...]}] → 요일×시간 히트맵. 전원 가능한 칸은 강조 */
function heatGrid(members) {
  const n = members.length, cnt = {};
  members.forEach(m => (m.sched || []).forEach(k => cnt[k] = (cnt[k] || 0) + 1));
  const all = ALL_SLOTS.filter(k => cnt[k] === n && n > 0).length;
  const g = el(`<div class="scroll-x"><table class="heat" aria-label="팀원 가능 인원 표">
    <thead><tr><th></th>${DAYS.map(d => `<th scope="col">${d}</th>`).join("")}</tr></thead>
    <tbody>${BLOCKS.map(([lb], i) => `<tr><th scope="row">${lb}</th>${DAYS.map(d => {
      const c = cnt[slotKey(d, i)] || 0;
      return `<td class="${c === n && n ? "all" : c >= n - 1 && n > 2 ? "most" : ""}" title="${d} ${lb}시 · ${c}/${n}명 가능">${c || ""}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>`);
  g.dataset.all = all; return g;
}
