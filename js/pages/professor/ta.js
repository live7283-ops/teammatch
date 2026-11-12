/* 조교 관리 — 수업(과목) 단위로 권한을 부여한다. 검색은 실제 가입한 학생 계정에서 한다. */
function renderTA(c, arg) {
  const cls = pickClass(arg), wrap = el(`<div class="page stack"></div>`);
  if (!cls) { wrap.append(el(`<div class="card card-pad"><div class="empty"><b>개설한 수업이 없습니다</b></div></div>`)); return c.append(wrap); }
  const sc = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">조교 권한 부여</h3><p class="card-sub">가입한 학생 계정 중 <b>${esc(cls.name)}</b> 과목에 한해 조교 권한을 부여합니다</p></div>
    <div><label class="sr" for="clsPick">수업 선택</label><select class="select" id="clsPick" style="width:auto">${db.classes.map(x => `<option value="${x.id}" ${x.id === cls.id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></div></div>
    <form class="flex" id="sf"><div class="grow"><label class="sr" for="taQ">학생 검색</label><input class="input" id="taQ" type="search" placeholder="학교 이메일 또는 이름으로 검색"></div><button class="btn" type="submit">검색</button></form>
    <p class="help">아직 가입하지 않은 학생은 검색되지 않습니다. 이미 이 과목의 조교인 계정은 제외됩니다.</p><div id="found" class="mt-16" aria-live="polite"></div></div>`);
  $("#clsPick", sc).onchange = e => nav("ta/" + e.target.value);
  $("#sf", sc).onsubmit = ev => { ev.preventDefault(); const q = $("#taQ", sc).value.trim().toLowerCase(), box = $("#found", sc); box.innerHTML = "";
    if (!q) return toast("검색어를 입력하세요.");
    const hits = Object.values(db.accounts).filter(x => x.role === "student" && !cls.tas.some(t => t.email === x.email) && (x.name.toLowerCase().includes(q) || x.email.toLowerCase().includes(q))).slice(0, 8);
    if (!hits.length) return box.append(el(`<div class="empty"><b>검색 결과가 없습니다</b>가입한 학생 계정만 검색됩니다.</div>`));
    hits.forEach(x => { const r = el(`<div class="role-row" style="border-top:1px solid var(--line)"><span class="avatar" style="width:34px;height:34px;font-size:13px" aria-hidden="true">${esc(initial(x.name))}</span>
      <span class="r-who"><b style="color:var(--navy);font-weight:500">${esc(x.name)}</b><br><span class="sm muted">${esc(x.email)} · ${esc(x.major)}${x.year ? " · " + esc(x.year) : ""}</span></span><span class="tag tag-grey">학생</span>
      <button class="btn btn-sm" type="button">이 과목 조교로 지정</button></div>`);
      $("button", r).onclick = () => { cls.tas.push({ email: x.email, date: new Date().toISOString() }); markSaved(); toast(`${x.name} 학생을 ${cls.name} 조교로 지정했습니다.`); renderRoute(); }; box.append(r); }); };
  wrap.append(sc);

  const lc = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">현재 지정된 조교</h3><p class="card-sub">${esc(cls.name)} · ${cls.tas.length}명</p></div></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th scope="col">이름</th><th scope="col">소속</th><th scope="col">지정일</th><th scope="col">권한 범위</th><th scope="col" class="right">처리</th></tr></thead><tbody id="tb"></tbody></table></div>
    <div class="demo-note mt-16">이 목록의 계정은 <b>${esc(cls.name)}</b>에서만 조교 메뉴(제출 현황·확정 후 결과)를 이용합니다. 다른 과목에서는 그대로 학생 권한이며, 편성 조건 설정·매칭 실행·확정 권한은 부여되지 않습니다.
    (데모: 조교로 지정된 계정으로 ‘학생’ 탭에서 로그인하면 사이드바에 ‘조교 업무’가 나타납니다.)</div></div>`);
  const tb = $("#tb", lc);
  if (!cls.tas.length) tb.append(el(`<tr><td colspan="5"><div class="empty" style="padding:24px"><b>지정된 조교가 없습니다</b>위에서 학생을 검색해 권한을 부여하세요.</div></td></tr>`));
  cls.tas.forEach((t, i) => { const x = acct(t.email);
    const tr = el(`<tr><td style="font-weight:500;color:var(--navy)">${esc(x ? x.name : t.email)}</td><td class="sm">${x ? esc(x.major + (x.year ? " " + x.year : "")) : "—"}</td><td class="num">${fmtDate(t.date)}</td>
      <td><span class="tag tag-grey">제출 현황 열람 · 리마인드 · 확정 후 결과 열람</span></td><td class="right"><button class="btn btn-ghost btn-sm" type="button">권한 해제</button></td></tr>`);
    $("button", tr).onclick = async () => { if (await confirmDialog({ title: "조교 권한 해제", message: `${x ? x.name : t.email} 계정의 ${cls.name} 조교 권한을 해제합니다.`, okText: "해제", danger: true })) { cls.tas.splice(i, 1); markSaved(); toast("조교 권한을 해제했습니다."); renderRoute(); } };
    tb.append(tr); });
  wrap.append(lc); c.append(wrap);
}
