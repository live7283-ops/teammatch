/* 학생 대시보드 — 모든 수치는 계정/수업 데이터에서 계산한다 */
function renderDashboard(c) {
  const a = me(), sc = profileScore(a), todos = profileTodos(a), miss = requiredMissing(a);
  const classes = a.joined.map(classById).filter(Boolean);
  const open = classes.filter(k => classStatus(k).key !== "done");
  const needReady = open.filter(k => !(a.ready && a.ready[k.id]));
  const hour = new Date().getHours(), greet = hour < 6 ? "늦은 시간까지 수고 많아요" : hour < 12 ? "좋은 아침이에요" : hour < 18 ? "안녕하세요" : "오늘도 수고했어요";
  const msg = !classes.length ? "아직 참여한 수업이 없습니다. 교수님께 받은 참여 코드를 입력하면 팀 매칭 준비가 시작됩니다."
    : miss.length ? `팀 편성은 담당 교수가 실행합니다. 필수 항목이 ${miss.length}개 남았어요. 먼저 채워 주세요.`
    : needReady.length ? `필수 항목을 모두 채웠습니다. ${needReady.map(k => k.name).join(", ")}에 ‘준비 완료’를 표시해 두세요.`
    : "준비가 끝났습니다. 교수가 편성을 확정하면 프로젝트 메뉴에 팀 공간이 열립니다.";
  const wrap = el(`<div class="page"><section class="hello"><h2>${greet}, ${esc(a.name)}님</h2><p>${esc(msg)}</p>
    <div class="hello-cta"><button class="btn btn-white" data-go="readiness">${classes.length ? "매칭 준비 확인하기" : "참여 코드 입력하기"}</button>
    <button class="btn btn-line" data-go="profile">프로필 채우기</button></div></section><div class="stack" id="dg"></div></div>`);
  const g = $("#dg", wrap);

  const dl = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">팀 매칭 준비</h3>
    <p class="card-sub">교수가 정한 마감 전까지 준비 완료로 표시하세요</p></div><button class="btn btn-quiet btn-sm" data-go="readiness">자세히</button></div><div id="dls"></div></div>`);
  const box = $("#dls", dl);
  if (!classes.length) box.append(el(`<div class="empty"><b>참여한 수업이 없습니다</b>‘매칭 준비’에서 교수님께 받은 참여 코드를 입력하세요.</div>`));
  classes.forEach(k => {
    const st = classStatus(k), ready = !!(a.ready && a.ready[k.id]), d = deadlineText(k.deadline);
    box.append(el(`<div class="proj-item"><span class="pi-ico" aria-hidden="true">${esc(initial(k.name))}</span><div class="grow">
      <h4>${esc(k.name)}</h4><div class="meta">설문 마감 ${fmtDT(k.deadline)} · ${d.text}</div></div>
      <span class="tag ${st.key === "done" ? "tag-mint" : ready ? "tag-mint" : "tag-amber"}">${st.key === "done" ? "편성 완료" : ready ? "준비 완료" : "준비 중"}</span></div>`));
  });
  g.append(dl);

  const ring = 2 * Math.PI * 44;
  const rc = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">프로필 완성도</h3>
    <p class="card-sub">필수 5개를 채워야 ‘준비 완료’로 표시할 수 있습니다</p></div></div>
    <div class="progress-ring"><div class="ring" role="img" aria-label="프로필 완성도 ${sc}%"><svg width="104" height="104"><circle cx="52" cy="52" r="44" stroke="var(--bg-deep)" stroke-width="10" fill="none"/>
    <circle cx="52" cy="52" r="44" stroke="var(--indigo)" stroke-width="10" fill="none" stroke-linecap="round" stroke-dasharray="${ring}" stroke-dashoffset="${ring * (1 - sc / 100)}"/></svg><div class="val">${sc}%</div></div>
    <ul class="todo grow">${todos.map(t => `<li class="${t.ok ? "done" : ""}${t.req ? "" : " opt-item"}"><span class="tick ${t.ok ? "" : "off"}">${t.ok ? "✓" : ""}</span>${esc(t.t)}
    ${t.ok ? "" : `<button class="btn btn-ghost btn-sm go" data-go="${t.go}">채우기</button>`}</li>`).join("")}</ul></div></div>`);
  g.append(rc);

  const prj = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">참여 중인 프로젝트</h3><p class="card-sub">편성이 확정되면 자동으로 생깁니다</p></div>
    <button class="btn btn-quiet btn-sm" data-go="projects">전체 보기</button></div><div id="pj"></div></div>`);
  if (!a.projects.length) $("#pj", prj).append(el(`<div class="empty"><b>아직 확정된 팀이 없습니다</b>교수가 편성을 확정하면 여기에 표시됩니다.</div>`));
  a.projects.forEach(p => {
    const n = p.agenda.filter(Boolean).length;
    const it = el(`<div class="proj-item"><span class="pi-ico" aria-hidden="true">${esc(initial(p.name))}</span><div class="grow"><h4>${esc(p.name)}</h4>
      <div class="meta">${esc(p.course)} · 팀원 ${p.team.length}명 · 첫 모임 준비 ${n}/4</div></div></div>`);
    makeClickable(it, () => nav("projects/" + p.id), `${p.name} 열기`); $("#pj", prj).append(it);
  });
  g.append(prj);

  const y = sched(a).length;
  g.append(el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">내 가능 시간</h3><p class="card-sub">팀원과 겹치는 시간을 계산하는 데 쓰입니다</p></div>
    <button class="btn btn-ghost btn-sm" data-go="schedule">시간표 수정</button></div>
    <div class="flex"><b class="big">${y}</b><span class="muted">시간 가능 (1시간 단위)</span></div>
    <div class="chips mt-16">${DAYS.map(d => { const n = BLOCKS.filter((_, i) => a.schedule[slotKey(d, i)] === "y").length; return `<span class="chip chip-static" ${n ? 'style="border-color:var(--mint);color:var(--mint)"' : ""}>${d} ${n}</span>`; }).join("")}</div></div>`));
  c.append(wrap); bindGo(wrap);
}
