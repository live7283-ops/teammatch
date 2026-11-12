/* 프로필(학생) — 입력 즉시 검증·자동 저장. 선호 역할은 최대 2개(1·2순위). */
const TRAITS = [["pace", "신속한 결정", "충분한 논의"], ["prep", "미리 준비", "마감 집중"], ["lead", "주도적 진행", "맡은 역할 집중"], ["comm", "자주 소통", "필요할 때 소통"]];

function renderProfile(c) {
  const a = me(), wrap = el(`<div class="page stack"></div>`);
  const saved = () => { markSaved(); syncSideUser(); renderNav(); };

  /* 기본 정보 */
  const info = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">기본 정보</h3><p class="card-sub">팀원에게 공개되는 프로필입니다 · 변경 즉시 저장됩니다</p></div>
    <span class="tag" id="pscore">완성도 ${profileScore(a)}%</span></div>
    <div class="flex mb-20"><span class="avatar" style="width:54px;height:54px;font-size:20px;background:var(--indigo)" aria-hidden="true">${esc(initial(a.name))}</span>
    <div><b class="block" style="color:var(--navy)">${esc(a.name)}</b><span class="sm muted">${esc(a.email)}</span></div></div>
    <div class="field"><label for="pName">이름</label><input class="input" id="pName" value="${esc(a.name)}" autocomplete="name"></div>
    <div class="row2"><div class="field"><label for="pMajor">전공</label><input class="input" id="pMajor" value="${esc(a.major)}"></div>
    <div class="field"><label for="pSid">학번</label><input class="input" id="pSid" inputmode="numeric" value="${esc(a.studentId)}"></div></div>
    <div class="field"><label for="pYear">학년 <span class="req">(필수)</span></label><select class="select" id="pYear"><option value="">선택하세요</option>
    ${["1학년", "2학년", "3학년", "4학년", "대학원"].map(y => `<option ${y === a.year ? "selected" : ""}>${y}</option>`).join("")}</select>
    <p class="help">매칭의 학년 분산 조건에 사용됩니다. 가입 시 입력하지 않았다면 여기서 선택하세요.</p></div></div>`);
  const upd = () => { $("#pscore", wrap).textContent = `완성도 ${profileScore(a)}%`; };
  const bindText = (id, key, validate) => { const i = $("#" + id, info);
    i.onchange = () => { clearErr(i); const v = i.value.trim(), msg = validate(v); if (msg) return setErr(i, msg); a[key] = v; saved(); upd(); }; };
  bindText("pName", "name", v => v ? "" : "이름을 입력하세요.");
  bindText("pMajor", "major", v => v ? "" : "전공을 입력하세요.");
  bindText("pSid", "studentId", v => /^\d{8,10}$/.test(v) ? "" : "학번은 숫자 8~10자리입니다.");
  $("#pYear", info).onchange = e => { a.year = e.target.value; saved(); upd(); };
  wrap.append(info);

  /* 자기소개 + 역할 */
  const bio = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">자기소개 · 선호 역할</h3><p class="card-sub">선호 역할은 최대 2개까지, 먼저 누른 것이 1순위입니다</p></div></div>
    <div class="field"><label for="pBio">자기소개 <span class="opt">(선택, 팀원에게 공개)</span></label><textarea class="textarea" id="pBio" maxlength="300">${esc(a.bio)}</textarea>
    <p class="help"><span id="bioN">${a.bio.length}</span>/300 · 관심 분야와 경험을 적으면 팀원이 서로를 이해하기 쉽습니다.</p></div>
    <fieldset class="field" style="border:0;padding:0;margin:0"><legend class="lbl">선호 역할 <span class="req">(필수)</span></legend><div class="chips" id="pRoles"></div></fieldset></div>`);
  const bi = $("#pBio", bio); bi.oninput = () => { $("#bioN", bio).textContent = bi.value.length; };
  bi.onchange = () => { a.bio = bi.value; saved(); upd(); };
  const drawRoles = () => { const box = $("#pRoles", bio); box.innerHTML = "";
    ROLES.forEach(r => { const idx = a.roles.indexOf(r), on = idx >= 0;
      const b = el(`<button type="button" class="chip" aria-pressed="${on}" aria-label="${r}${on ? ` (${idx + 1}순위, 선택됨)` : ""}">${r}${on ? `<span class="ord" aria-hidden="true">${idx + 1}</span>` : ""}</button>`);
      b.onclick = () => { if (on) a.roles.splice(idx, 1); else if (a.roles.length >= 2) return toast("선호 역할은 최대 2개까지 고를 수 있습니다."); else a.roles.push(r); drawRoles(); saved(); upd(); };
      box.append(b); }); };
  drawRoles(); wrap.append(bio);

  /* 기술 */
  const sk = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">보유 기술 · 숙련도</h3><p class="card-sub">1(입문) ~ 5(능숙)</p></div></div><div id="sl"></div>
    <form class="add-skill" id="addSk"><label class="sr" for="newSk">기술 이름</label><input class="input" id="newSk" placeholder="기술 이름 입력 (예: SQL)" maxlength="20"><button class="btn btn-ghost" type="submit">추가</button></form></div>`);
  const drawSk = () => { const box = $("#sl", sk); box.innerHTML = "";
    if (!a.skills.length) box.append(el(`<div class="empty"><b>등록된 기술이 없습니다</b>아래에서 하나 이상 추가하세요.</div>`));
    a.skills.forEach((s, i) => { const row = el(`<div class="skill-row"><span class="sk-nm">${esc(s.n)}</span><span class="dp"></span><button type="button" class="x-btn" aria-label="${esc(s.n)} 삭제">×</button></div>`);
      const dp = dotPicker({ value: s.l, label: `${s.n} 숙련도`, onChange: v => { s.l = v; saved(); } }); dp.classList.add("sm"); $(".dp", row).append(dp);
      $(".x-btn", row).onclick = () => { a.skills.splice(i, 1); drawSk(); saved(); upd(); }; box.append(row); }); };
  $("#addSk", sk).onsubmit = ev => { ev.preventDefault(); const i = $("#newSk", sk); clearErr(i); const v = i.value.trim();
    if (!v) return setErr(i, "기술 이름을 입력하세요."); if (a.skills.some(s => s.n.toLowerCase() === v.toLowerCase())) return setErr(i, "이미 등록된 기술입니다.");
    if (a.skills.length >= 12) return setErr(i, "기술은 최대 12개까지 등록할 수 있습니다.");
    a.skills.push({ n: v, l: 3 }); i.value = ""; drawSk(); saved(); upd(); i.focus(); };
  drawSk(); wrap.append(sk);

  /* 협업 성향 — 1~5점 원형 선택 (가중치 UI와 동일) */
  a.traitTouched = a.traitTouched || {};
  const tr = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">협업 성향 <span class="req">(필수)</span></h3><p class="card-sub">네 문항 모두 선택해야 응답으로 인정됩니다</p></div>
    <span class="tag ${a.traitsSet ? "tag-mint" : "tag-amber"}" id="trs">${a.traitsSet ? "응답 완료" : "응답 전"}</span></div><div id="trl"></div></div>`);
  TRAITS.forEach(([k, l, r]) => { const answered = a.traitsSet || a.traitTouched[k];
    const row = el(`<div class="pick-row"><div class="ends"><b>${l}</b><b>${r}</b></div><div class="grow"></div></div>`);
    $(".grow", row).append(dotPicker({ value: answered ? a.traits[k] : 0, label: `${l} ↔ ${r}`, onChange: v => { a.traits[k] = v; a.traitTouched[k] = true;
      a.traitsSet = TRAITS.every(([x]) => a.traitTouched[x]) || a.traitsSet; $("#trs", tr).textContent = a.traitsSet ? "응답 완료" : "응답 전"; $("#trs", tr).className = "tag " + (a.traitsSet ? "tag-mint" : "tag-amber"); saved(); upd(); } }));
    $("#trl", tr).append(row); });
  wrap.append(tr);

  wrap.append(el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">가능한 일정</h3><p class="card-sub">${sched(a).length}시간이 ‘가능’으로 표시되어 있습니다 (필수: 5시간 이상)</p></div>
    <button class="btn btn-ghost btn-sm" data-go="schedule">시간표 편집</button></div></div>`));
  wrap.append(withdrawCard(a));
  c.append(wrap); bindGo(wrap);
}
