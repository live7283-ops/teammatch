/* 내 수업 / 수업 개설 */
const CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
function genCode() { let code; do { code = Array.from({ length: 6 }, () => CODE_ALPHABET[Math.floor(Math.random() * CODE_ALPHABET.length)]).join(""); } while (db.classes.some(k => k.join === code)); return code; }

function renderClasses(c, arg) {
  if (arg === "new") return renderClassForm(c);
  const wrap = el(`<div class="page"><div class="flex-end mb-16"><button class="btn" id="newCls" type="button">+ 수업 개설</button></div></div>`);
  $("#newCls", wrap).onclick = () => nav("classes/new");
  if (!db.classes.length) wrap.append(el(`<div class="card card-pad"><div class="empty"><b>개설한 수업이 없습니다</b>‘수업 개설’로 참여 코드를 만들어 학생에게 전달하세요.</div></div>`));
  const grid = el(`<div class="team-grid"></div>`);
  db.classes.forEach(k => { const st = classStatus(k), s = rosterStats(k);
    const card = el(`<article class="class-card"><div class="tc-top"><h4>${esc(k.name)}</h4><span class="tag ${st.tone}">${st.label}</span></div>
      <p class="card-sub">${esc(k.code)} · ${esc(k.term)} · ${esc(k.kind)}</p>
      <div class="metric mt-16"><span>설문 제출</span><b>${s.done}/${s.total}</b></div><div class="bar"><i style="width:${s.pct}%"></i></div>
      <p class="sm muted mt-8">마감 ${fmtDT(k.deadline)} (${deadlineText(k.deadline).text}) · 예상 ${k.cap}명</p>
      <div class="code-box mt-16"><span class="sm" style="color:var(--text-2)">참여 코드</span><span class="cd" style="font-size:16px">${esc(k.join)}</span><span class="grow"></span>
      <button class="btn btn-quiet btn-sm" data-a="copy" type="button">복사</button><button class="btn btn-quiet btn-sm" data-a="regen" type="button">재생성</button></div>
      <div class="tc-foot"><button class="btn btn-ghost btn-sm" data-a="roster" type="button">제출 현황</button><button class="btn btn-ghost btn-sm" data-a="setup" type="button">편성 설정</button>
      ${k.result ? '<button class="btn btn-ghost btn-sm" data-a="result" type="button">결과</button>' : ""}</div></article>`);
    $$("[data-a]", card).forEach(b => b.onclick = async () => { const a = b.dataset.a;
      if (a === "copy") return copyText(k.join);
      if (a === "regen") { if (await confirmDialog({ title: "참여 코드 재생성", message: `새 코드를 만들면 이전 코드(${k.join})로는 더 이상 참여할 수 없습니다. 이미 참여한 학생에게는 영향이 없습니다.`, okText: "재생성" })) { k.join = genCode(); markSaved(); toast("새 참여 코드를 만들었습니다."); renderRoute(); } return; }
      nav(a + "/" + k.id); });
    grid.append(card); });
  wrap.append(grid); c.append(wrap);
}

function renderClassForm(c) {
  const d = new Date(Date.now() + 7 * DAY_MS), code = genCode();
  const form = el(`<form class="card card-pad" novalidate><button class="back-link" type="button">← 내 수업</button>
    <div class="card-head"><div><h3 class="card-title">수업 개설</h3><p class="card-sub">수업을 만들면 학생 참여 코드가 생성됩니다. 조교 지정은 개설 후에 가능합니다.</p></div></div>
    <div class="row2"><div class="field"><label for="ncName">수업명 <span class="req">*</span></label><input class="input" id="ncName" placeholder="DS창업캡스톤디자인1"></div>
    <div class="field"><label for="ncCode">학수번호 <span class="req">*</span></label><input class="input" id="ncCode" placeholder="MAT2082"></div></div>
    <div class="row2"><div class="field"><label for="ncTerm">학기</label><select class="select" id="ncTerm"><option>2026학년도 2학기</option><option>2027학년도 1학기</option></select></div>
    <div class="field"><label for="ncCap">예상 수강 인원 <span class="req">*</span></label><input class="input" id="ncCap" type="number" min="2" max="500" value="40"></div></div>
    <div class="row2"><div class="field"><label for="ncKind">수업 성격</label><select class="select" id="ncKind">${["개발 프로젝트", "기획·마케팅 프로젝트", "학술 세미나", "공모전·해커톤"].map(x => `<option>${x}</option>`).join("")}</select>
    <p class="help">선택한 성격에 맞는 설문 문항 템플릿이 적용됩니다.</p></div>
    <div class="field"><label for="ncDue">설문 제출 마감 (23:59) <span class="req">*</span></label><input class="input" id="ncDue" type="date" value="${toDateInput(d)}" min="${toDateInput(new Date())}"></div></div>
    <div class="field"><label>학생 참여 코드</label><div class="code-box"><span class="cd" id="ncJoin">${code}</span><span class="grow"></span>
    <button class="btn btn-quiet btn-sm" id="ncCopy" type="button">복사</button><button class="btn btn-quiet btn-sm" id="ncRegen" type="button">재생성</button></div>
    <p class="help">학생은 가입 시 또는 ‘매칭 준비’ 화면에서 이 코드를 입력해 합류합니다.</p></div>
    <p class="err" id="ncErr" role="alert"></p>
    <div class="wizard-nav"><button class="btn btn-ghost" id="ncCancel" type="button">취소</button><button class="btn" type="submit">수업 개설 완료</button></div></form>`);
  $(".back-link", form).onclick = $("#ncCancel", form).onclick = () => nav("classes");
  $("#ncCopy", form).onclick = () => copyText($("#ncJoin", form).textContent);
  $("#ncRegen", form).onclick = () => { $("#ncJoin", form).textContent = genCode(); toast("참여 코드를 새로 만들었습니다."); };
  form.addEventListener("submit", ev => { ev.preventDefault(); clearAllErr(form);
    const g = id => $("#" + id, form), v = { name: g("ncName").value.trim(), code: g("ncCode").value.trim(), cap: Number(g("ncCap").value), due: g("ncDue").value, term: g("ncTerm").value, kind: g("ncKind").value };
    const bad = (id, m) => { setErr(g(id), m); g(id).focus(); };
    if (!v.name) return bad("ncName", "수업명을 입력하세요."); if (!v.code) return bad("ncCode", "학수번호를 입력하세요.");
    if (db.classes.some(k => k.code.toLowerCase() === v.code.toLowerCase() && k.term === v.term)) return bad("ncCode", "같은 학기에 같은 학수번호의 수업이 이미 있습니다.");
    if (!Number.isInteger(v.cap) || v.cap < 2 || v.cap > 500) return bad("ncCap", "2~500 사이의 정수를 입력하세요.");
    if (!v.due) return bad("ncDue", "마감일을 선택하세요."); const due = new Date(v.due + "T23:59:00");
    if (due.getTime() < Date.now()) return bad("ncDue", "마감일은 오늘 이후여야 합니다.");
    const k = { id: nextId("c"), name: v.name, code: v.code, term: v.term, cap: v.cap, join: g("ncJoin").textContent, deadline: due.toISOString(), kind: v.kind,
      createdAt: new Date().toISOString(), setup: defaultSetup(), roster: [], result: null, tas: [] };
    db.classes.unshift(k); lastClassId = k.id; markSaved(); renderNav(); toast("수업을 개설했습니다. 참여 코드를 학생에게 전달하세요."); nav("classes"); });
  const pg = el(`<div class="page"></div>`); pg.append(form); c.append(pg);
  $("#ncName", form).focus();
}
