/* 교수 대시보드 — '지금 할 일'을 포함한 모든 수치는 수업 데이터에서 계산한다 (원본은 고정 문구) */
function focusClass() {
  const rank = { ready: 0, review: 1, collecting: 2, done: 3 };
  return [...db.classes].sort((a, b) => rank[classStatus(a).key] - rank[classStatus(b).key])[0] || null;
}
function renderProfDashboard(c) {
  const a = me(), cl = db.classes, ready = cl.filter(k => classStatus(k).key === "ready"), collecting = cl.filter(k => classStatus(k).key === "collecting");
  const total = cl.reduce((s, k) => s + rosterStats(k).total, 0), tas = new Set(cl.flatMap(k => k.tas.map(t => t.email))).size;
  const wrap = el(`<div class="page"><section class="hello"><h2>${esc(a.name)} 교수님${ready.length ? `, 지금 편성할 수 있는 수업이 ${ready.length}개 있습니다` : ", 안녕하세요"}</h2>
    <p>${ready.length ? esc(ready.map(k => k.name).join(", ")) + " — 설문 마감이 지났거나 모두 제출했습니다. 조건을 확인하고 편성을 실행하세요." : collecting.length ? `설문을 받는 중인 수업이 ${collecting.length}개 있습니다. 편성은 마감 후 실행하는 것을 권장합니다.` : "모든 수업의 편성이 정리되었습니다."} 결과는 확정 전까지 학생에게 공개되지 않습니다.</p>
    <div class="hello-cta"><button class="btn btn-white" data-go="setup/${(focusClass() || {}).id || ""}">편성 설정</button><button class="btn btn-line" data-go="classes/new">수업 개설</button></div></section>
    <div class="result-summary"><div class="stat"><div class="n">${cl.length}</div><div class="l">운영 중인 수업</div></div><div class="stat"><div class="n">${total}명</div><div class="l">전체 수강생(참여 등록)</div></div>
    <div class="stat"><div class="n">${cl.filter(k => classStatus(k).key === "done").length}</div><div class="l">편성 완료</div></div><div class="stat"><div class="n">${tas}명</div><div class="l">지정된 조교</div></div></div>
    <div class="stack" id="dg"></div></div>`);
  const g = $("#dg", wrap);

  const list = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">수업별 설문 제출 현황</h3><p class="card-sub">수업을 누르면 제출 현황으로 이동합니다</p></div></div><div id="cl"></div></div>`);
  if (!cl.length) $("#cl", list).append(el(`<div class="empty"><b>개설한 수업이 없습니다</b>‘수업 개설’에서 첫 수업을 만드세요.</div>`));
  cl.forEach(k => { const st = classStatus(k), s = rosterStats(k), d = deadlineText(k.deadline);
    const row = el(`<div class="proj-item"><span class="pi-ico" aria-hidden="true">${esc(initial(k.name))}</span><div class="grow"><h4>${esc(k.name)} <span class="tag ${st.tone}">${st.label}</span></h4>
      <div class="meta">${esc(k.code)} · 등록 ${s.total}명(예상 ${k.cap}) · 마감 ${fmtDT(k.deadline)} (${d.text})</div>
      <div class="metric mt-8"><span>설문 제출</span><b>${s.done}/${s.total} · ${s.pct}%</b></div><div class="bar"><i style="width:${s.pct}%"></i></div></div></div>`);
    makeClickable(row, () => nav("roster/" + k.id), `${k.name} 제출 현황 열기`); $("#cl", list).append(row); });
  g.append(list);

  const f = focusClass();
  if (f) {
    const s = rosterStats(f), st = classStatus(f), steps = [
      { ok: true, t: "수업 개설과 참여 코드 배포", go: ["classes", "수업 보기"] },
      { ok: st.key !== "collecting", t: `설문 수집 — 제출 ${s.done}/${s.total}명${s.pending ? ` (미제출 ${s.pending}명)` : ""}`, go: ["roster/" + f.id, s.pending ? "리마인드" : "현황 보기"] },
      { ok: !!f.setup.touched || !!f.result, t: "편성 조건과 가중치 확정", go: ["setup/" + f.id, "설정"] },
      { ok: !!f.result, t: "편성 실행 후 결과 검토", go: ["result/" + f.id, "결과"] },
      { ok: st.key === "done", t: "팀 확정 및 학생에게 공개", go: ["result/" + f.id, "확정"] }];
    const next = steps.findIndex(x => !x.ok);
    g.append(el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">지금 할 일 — ${esc(f.name)}</h3><p class="card-sub">남은 단계는 실제 수업 상태에서 계산됩니다</p></div></div>
      <ul class="todo">${steps.map((x, i) => `<li class="${x.ok ? "done" : ""}"><span class="tick ${x.ok ? "" : "off"}">${x.ok ? "✓" : ""}</span>${esc(x.t)}
      ${i === next ? `<button class="btn btn-sm go" data-go="${x.go[0]}">${x.go[1]}</button>` : ""}</li>`).join("")}</ul></div>`));
  }
  const taList = cl.flatMap(k => k.tas.map(t => ({ ...t, cls: k.name })));
  g.append(el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">조교</h3><p class="card-sub">과목 단위로만 권한이 적용됩니다</p></div><button class="btn btn-ghost btn-sm" data-go="ta/${(focusClass() || {}).id || ""}">조교 관리</button></div>
    ${taList.length ? taList.map(t => { const x = acct(t.email); return `<div class="role-row"><span class="avatar" style="width:30px;height:30px;font-size:12px" aria-hidden="true">${esc(initial(x ? x.name : "?"))}</span><span class="r-who"><b style="color:var(--navy);font-weight:500">${esc(x ? x.name : t.email)}</b><br><span class="sm muted">${esc(t.cls)}</span></span><span class="tag tag-grey">조교</span></div>`; }).join("") : `<div class="empty"><b>지정된 조교가 없습니다</b></div>`}</div>`));
  c.append(wrap); bindGo(wrap);
}
