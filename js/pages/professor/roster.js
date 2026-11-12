/* 학생 제출 현황 — 교수/조교 공용 (조교는 열람·리마인드만).
   원본과 달리 수업별 명단에서 계산하고, 검색·페이지·구조화된 리마인드 횟수를 지원한다. */
const PAGE_SIZE = 10;
function renderRoster(c, arg, opts = {}) {
  const ta = !!opts.ta, a = me(), list = ta ? taClasses(a.email) : db.classes, cls = pickClass(arg, list);
  const wrap = el(`<div class="page"></div>`);
  if (!cls) { wrap.append(el(`<div class="card card-pad"><div class="empty"><b>${ta ? "조교로 지정된 수업이 없습니다" : "개설한 수업이 없습니다"}</b></div></div>`)); return c.append(wrap); }
  const redraw = () => { c.innerHTML = ""; renderRoster(c, cls.id, opts); };
  const rows = participantsOf(cls), s = rosterStats(cls), d = deadlineText(cls.deadline), st = classStatus(cls);

  wrap.append(el(`<div class="card card-pad mb-16"><div class="card-head"><div><h3 class="card-title">${esc(cls.name)} <span class="tag ${st.tone}">${st.label}</span></h3>
    <p class="card-sub">설문 마감 ${fmtDT(cls.deadline)} (${d.text})${ta ? " · 조교 권한: 열람과 리마인드만 가능합니다" : ""}</p></div>
    <div class="flex-end"><label class="sr" for="clsPick">수업 선택</label><select class="select" id="clsPick" style="width:auto">${list.map(x => `<option value="${x.id}" ${x.id === cls.id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
    <button class="btn btn-ghost btn-sm" id="dl" type="button">명단 내려받기</button>
    ${!ta && st.key !== "done" ? '<button class="btn btn-ghost btn-sm" id="ext" type="button">마감 +1일</button>' : ""}
    <button class="btn btn-sm" id="remAll" type="button" ${s.pending ? "" : "disabled"}>미제출자 리마인드 (${s.pending})</button></div></div>
    <div class="result-summary" style="margin-bottom:0"><div class="stat"><div class="n">${s.total}명</div><div class="l">등록 인원 (예상 ${cls.cap}명)</div></div>
    <div class="stat"><div class="n">${s.done}<span class="muted" style="font-size:14px"> · ${s.pct}%</span></div><div class="l">제출 완료</div></div>
    <div class="stat"><div class="n">${s.pending}명</div><div class="l">미제출</div></div><div class="stat"><div class="n">${d.past ? "마감" : d.text}</div><div class="l">마감까지</div></div></div>
    <div class="bar mt-16"><i style="width:${s.pct}%"></i></div></div>`));
  $("#clsPick", wrap).onchange = e => nav((ta ? "ta-roster/" : "roster/") + e.target.value);

  const remind = r => { const row = cls.roster.find(x => x.id === r.id); if (row) { row.reminders = (row.reminders || 0) + 1; row.lastReminder = new Date().toISOString(); } };
  $("#dl", wrap).onclick = () => downloadCSV(`${cls.name}_제출현황.csv`, [["학번", "이름", "학과", "학년", "제출 상태", "제출 시각", "리마인드 횟수"],
    ...rows.map(r => [r.sid, r.n, r.major, r.yearLabel, r.submitted ? "제출 완료" : "미제출", r.at ? fmtDT(r.at) : "", r.reminders])]);
  $("#remAll", wrap).onclick = async () => { if (!await confirmDialog({ title: "미제출자 리마인드", message: `미제출 ${s.pending}명에게 알림을 보냅니다. (데모에서는 횟수만 기록됩니다)`, okText: "보내기" })) return;
    rows.filter(r => !r.submitted).forEach(remind); markSaved(); toast(`미제출 ${s.pending}명에게 리마인드를 기록했습니다.`); redraw(); };
  const ext = $("#ext", wrap); if (ext) ext.onclick = async () => { if (await confirmDialog({ title: "설문 마감 연장", message: `마감을 ${fmtDT(new Date(new Date(cls.deadline).getTime() + DAY_MS).toISOString())}로 1일 연장합니다.`, okText: "연장" })) { cls.deadline = new Date(Math.max(Date.now(), new Date(cls.deadline).getTime()) + DAY_MS).toISOString(); markSaved(); toast("마감을 연장했습니다."); redraw(); } };

  if (!rows.length) { wrap.append(el(`<div class="card card-pad"><div class="empty"><b>아직 참여한 학생이 없습니다</b>학생에게 참여 코드 <b>${esc(cls.join)}</b> 를 전달하세요.</div>${ta ? "" : `<div class="center mt-16"><button class="btn btn-ghost btn-sm" id="cp" type="button">코드 복사</button></div>`}</div>`)); const cp = $("#cp", wrap); if (cp) cp.onclick = () => copyText(cls.join); return c.append(wrap); }

  let filter = "all", q = "", page = 1;
  const card = el(`<div class="card card-pad"><div class="toolbar"><div class="chips" id="rf" role="group" aria-label="제출 상태 필터">
    <button class="chip" aria-pressed="true" data-f="all" type="button">전체 ${s.total}</button><button class="chip" aria-pressed="false" data-f="y" type="button">제출 ${s.done}</button><button class="chip" aria-pressed="false" data-f="n" type="button">미제출 ${s.pending}</button></div>
    <div class="search"><label class="sr" for="rq">검색</label><input class="input" id="rq" type="search" placeholder="이름·학번·학과 검색"></div></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th scope="col">학번</th><th scope="col">이름</th><th scope="col">학과</th><th scope="col">학년</th><th scope="col">제출 상태</th><th scope="col">제출 시각</th><th scope="col" class="right">처리</th></tr></thead><tbody id="rb"></tbody></table></div>
    <div class="pager"><span id="pinfo"></span><span class="pg" id="pg"></span></div>
    <p class="help mt-16">마감까지 미제출한 학생은 편성 설정에서 ‘기본값 배정 · 마감 연장 · 편성 제외’ 중 하나로 처리합니다.</p></div>`);
  const draw = () => {
    const ql = q.trim().toLowerCase();
    const f = rows.filter(r => (filter === "all" || (filter === "y" ? r.submitted : !r.submitted)) && (!ql || [r.n, r.sid, r.major].some(v => String(v).toLowerCase().includes(ql))));
    const pages = Math.max(1, Math.ceil(f.length / PAGE_SIZE)); page = Math.min(page, pages);
    const body = $("#rb", card); body.innerHTML = "";
    if (!f.length) body.append(el(`<tr><td colspan="7"><div class="empty" style="padding:22px"><b>조건에 맞는 학생이 없습니다</b></div></td></tr>`));
    f.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).forEach(r => {
      const tr = el(`<tr><td class="num">${esc(r.sid)}</td><td style="font-weight:500;color:var(--navy)">${esc(r.n)}</td><td class="sm">${esc(r.major)}</td><td class="num">${esc(String(r.yearLabel).replace("학년", ""))}</td>
        <td><span class="tag ${r.submitted ? "tag-mint" : r.reminders ? "tag-amber" : "tag-grey"}">${r.submitted ? "제출 완료" : r.reminders ? `미제출 · 리마인드 ${r.reminders}회` : "미제출"}</span></td>
        <td class="num">${r.at ? fmtDT(r.at) : "—"}</td><td class="right">${r.submitted ? '<span class="num">—</span>' : `<button class="btn btn-ghost btn-sm" type="button" aria-label="${esc(r.n)} 리마인드">리마인드</button>`}</td></tr>`);
      const b = $("button", tr); if (b) b.onclick = () => { remind(r); markSaved(); toast(`${r.n} 학생에게 리마인드를 기록했습니다.`); r.reminders++; draw(); };
      body.append(tr); });
    $("#pinfo", card).textContent = f.length ? `${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, f.length)} / ${f.length}명` : "0명";
    const pg = $("#pg", card); pg.innerHTML = "";
    const mk = (t, p, o = {}) => { const b = el(`<button type="button" ${o.cur ? 'aria-current="page"' : ""} ${o.dis ? "disabled" : ""} aria-label="${o.label || p + "쪽"}">${t}</button>`); b.onclick = () => { page = p; draw(); }; pg.append(b); };
    mk("‹", page - 1, { dis: page === 1, label: "이전 쪽" });
    for (let p = 1; p <= pages; p++) if (p === 1 || p === pages || Math.abs(p - page) <= 1) mk(p, p, { cur: p === page }); else if (Math.abs(p - page) === 2) pg.append(el("<span>…</span>"));
    mk("›", page + 1, { dis: page === pages, label: "다음 쪽" });
  };
  $$("#rf .chip", card).forEach(ch => ch.onclick = () => { filter = ch.dataset.f; page = 1; $$("#rf .chip", card).forEach(x => x.setAttribute("aria-pressed", String(x === ch))); draw(); });
  $("#rq", card).oninput = e => { q = e.target.value; page = 1; draw(); };
  draw(); wrap.append(card);
  if (ta) wrap.append(el(`<div class="alert mt-16"><span aria-hidden="true">🔒</span><span>조교는 편성 조건 설정·매칭 실행·확정 권한이 없습니다. 해당 기능은 담당 교수 계정에서만 작동합니다.</span></div>`));
  c.append(wrap);
}
