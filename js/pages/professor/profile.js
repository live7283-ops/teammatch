/* 교수 프로필 — 기본 정보 확인·수정(변경 즉시 저장), 활동 요약, 회원 탈퇴.
   학생과 달리 성향·일정·기술은 없다. 이메일·비밀번호 변경은 로그인 서버가 생기면 지원한다. */
function renderProfProfile(c) {
  const a = me(), wrap = el(`<div class="page stack"></div>`);
  if (!a.school || !a.dept) wrap.append(el(`<div class="alert warn"><span>학교와 소속 학과를 입력해 주세요. 학생에게 보이는 수업 정보와 보고서에 사용됩니다.</span></div>`));

  const info = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">기본 정보</h3><p class="card-sub">변경하면 즉시 저장됩니다</p></div></div>
    <div class="flex mb-20"><span class="avatar" id="pfAv" style="width:54px;height:54px;font-size:20px;background:var(--indigo)" aria-hidden="true">${esc(initial(a.name))}</span>
    <div><b class="block" id="pfTitle" style="color:var(--navy)">${esc(a.name)} 교수</b><span class="sm muted">교수 계정</span></div></div>
    <div class="field"><label for="pfName">이름</label><input class="input" id="pfName" value="${esc(a.name)}" autocomplete="name"></div>
    <div class="field"><label for="pfEmail">학교 이메일</label><input class="input" id="pfEmail" value="${esc(a.email)}" disabled aria-describedby="pfEmailHelp">
    <p class="help" id="pfEmailHelp">이메일·비밀번호 변경은 로그인 서버 연동 후 지원됩니다.</p></div>
    <div class="row2"><div class="field"><label for="pfSchool">학교</label><input class="input" id="pfSchool" value="${esc(a.school || "")}" placeholder="한양대학교 ERICA"></div>
    <div class="field"><label for="pfDept">소속 학과</label><input class="input" id="pfDept" value="${esc(a.dept || "")}" placeholder="데이터사이언스학과"></div></div></div>`);
  [["pfName", "name", "이름을 입력하세요."], ["pfSchool", "school", "학교를 입력하세요."], ["pfDept", "dept", "소속 학과를 입력하세요."]].forEach(([id, key, msg]) => {
    const i = $("#" + id, info);
    i.onchange = () => { clearErr(i); const v = i.value.trim(); if (!v) return setErr(i, msg);
      a[key] = v; markSaved(); syncSideUser(); $("#pfAv", info).textContent = initial(a.name); $("#pfTitle", info).textContent = a.name + " 교수"; };
  });
  wrap.append(info);

  const cl = db.classes, tas = new Set(cl.flatMap(k => k.tas.map(t => t.email))).size, students = cl.reduce((s, k) => s + rosterStats(k).total, 0);
  wrap.append(el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">활동 요약</h3><p class="card-sub">수정할 수 없는 집계입니다</p></div></div>
    <div class="result-summary" style="margin-bottom:0"><div class="stat"><div class="n">${cl.length}</div><div class="l">운영 중인 수업</div></div>
    <div class="stat"><div class="n">${cl.filter(k => classStatus(k).key === "done").length}</div><div class="l">편성 완료</div></div>
    <div class="stat"><div class="n">${students}명</div><div class="l">등록 학생</div></div><div class="stat"><div class="n">${tas}명</div><div class="l">지정된 조교</div></div></div></div>`));

  wrap.append(withdrawCard(a)); c.append(wrap);
}
