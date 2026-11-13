/* 매칭 준비(학생) — 편성은 교수가 한다. 학생은 수업에 참여하고 프로필을 채운 뒤 '준비 완료'를 표시한다. */
function renderReadiness(c) {
  const a = me(), miss = requiredMissing(a);
  const wrap = el(`<div class="page stack"></div>`);

  /* 수업 참여 코드 */
  const join = el(`<form class="card card-pad" novalidate><div class="card-head"><div><h3 class="card-title">수업 참여</h3>
    <p class="card-sub">교수님께 받은 6자리 참여 코드를 입력하세요</p></div></div>
    <div class="flex"><div class="field grow" style="margin:0"><label class="sr" for="jc">참여 코드</label>
    <input class="input" id="jc" placeholder="예) A7X9K2" maxlength="6" autocapitalize="characters" autocomplete="off"></div><button class="btn" type="submit">참여하기</button></div></form>`);
  join.addEventListener("submit", ev => {
    ev.preventDefault(); const i = $("#jc", join); clearErr(i);
    const code = i.value.trim().toUpperCase(), cls = db.classes.find(k => k.join === code);
    if (!code) return setErr(i, "참여 코드를 입력하세요.");
    if (!cls) return setErr(i, "유효하지 않은 참여 코드입니다.");
    if (a.joined.includes(cls.id)) return setErr(i, "이미 참여한 수업입니다.");
    if (classStatus(cls).key === "done") return setErr(i, "이미 편성이 끝난 수업입니다. 교수님께 문의하세요.");
    joinClass(a, cls); markSaved(); toast(`${cls.name}에 참여했습니다.`); renderRoute();
  });
  wrap.append(join);

  const classes = a.joined.map(classById).filter(Boolean);
  if (!classes.length) wrap.append(el(`<div class="card card-pad"><div class="empty"><b>참여한 수업이 없습니다</b>위에 참여 코드를 입력하면 수업별 준비 상태가 여기에 표시됩니다.</div></div>`));

  /* 필수 항목 */
  if (classes.length) {
    const todos = profileTodos(a);
    wrap.append(el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">준비 항목</h3>
      <p class="card-sub">${miss.length ? `필수 ${miss.length}개를 더 채워야 합니다` : "필수 항목을 모두 채웠습니다"}</p></div></div>
      <ul class="todo">${todos.map(t => `<li class="${t.ok ? "done" : ""}${t.req ? "" : " opt-item"}"><span class="tick ${t.ok ? "" : "off"}">${t.ok ? "✓" : ""}</span>${esc(t.t)}
      ${t.ok ? "" : `<button class="btn btn-ghost btn-sm go" data-go="${t.go}">채우기</button>`}</li>`).join("")}</ul></div>`));
  }

  /* 수업별 준비 상태 */
  classes.forEach(k => {
    const st = classStatus(k), ready = !!(a.ready && a.ready[k.id]), d = deadlineText(k.deadline);
    const locked = st.key === "done" || (d.past && !ready);
    const card = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">${esc(k.name)}</h3>
      <p class="card-sub">${esc(k.code)} · 설문 마감 ${fmtDT(k.deadline)} (${d.text})</p></div>
      <span class="tag ${st.tone}">${st.label}</span></div><div id="sw"></div></div>`);
    const row = el(`<div class="switch-row ${ready ? "on" : ""}"><span id="sl-${k.id}" class="grow"><b>팀 매칭 준비 완료</b>
      <span class="sm muted block">${st.key === "done" ? "편성이 확정되었습니다. ‘프로젝트’에서 팀 공간을 확인하세요."
        : locked ? "설문 마감이 지나 변경할 수 없습니다. 변경이 필요하면 교수님께 문의하세요."
        : miss.length && !ready ? `필수 항목 ${miss.length}개를 먼저 채워야 켤 수 있습니다.` : "켜두면 교수가 편성할 때 내 정보가 반영됩니다."}</span></span></div>`);
    const sw = switchBtn({ on: ready, label: `${k.name} 팀 매칭 준비 완료`, disabled: locked || (miss.length > 0 && !ready), onChange: on => {
      if (on && requiredMissing(a).length) return toast("필수 항목을 먼저 채워 주세요.");
      a.ready = a.ready || {}; a.readyAt = a.readyAt || {};
      a.ready[k.id] = on; if (on) a.readyAt[k.id] = new Date().toISOString(); else delete a.readyAt[k.id];
      markSaved(); toast(on ? `${k.name} 준비 완료로 표시했습니다.` : "준비 완료 표시를 해제했습니다."); renderRoute();
    } });
    sw.setAttribute("aria-describedby", "sl-" + k.id); row.prepend(sw); $("#sw", card).append(row);
    if (st.key === "done") $("#sw", card).append(el(`<div class="mt-16"><button class="btn btn-ghost btn-sm" data-go="projects">프로젝트 보기</button></div>`));
    wrap.append(card);
  });
  c.append(wrap); bindGo(wrap);
}
