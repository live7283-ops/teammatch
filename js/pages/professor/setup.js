/* 편성 설정 — 수업마다 독립된 설정(cls.setup). 상단 '내 설정 보관함'에서 교수 계정에 저장해 둔 설정을 다른 수업으로 불러올 수 있다. 가중치는 교수가 조절하지 않는다 — 제작팀 고정값(TM.DEFAULT_WEIGHTS)을 모든 수업에 일괄 적용한다.
   "AI 해석" 영역은 키워드 해석(데모)이며, 해석된 조건은 실제로 편성 알고리즘에 반영·검증된다. */
const SURVEY = { "개발 프로젝트": ["희망 역할 순위", "보유 기술·도구", "협업 성향 4문항", "주간 가용 시간", "자기소개"], "기획·마케팅 프로젝트": ["희망 역할 순위", "경험 분야·도구", "협업 성향 4문항", "주간 가용 시간", "자기소개"],
  "학술 세미나": ["희망 역할 순위", "관심 주제·방법론", "협업 성향 4문항", "주간 가용 시간", "자기소개"], "공모전·해커톤": ["희망 역할 순위", "보유 기술·도구", "협업 성향 4문항", "주간 가용 시간", "자기소개"] };

function loadingCard(n, server) {
  const steps = server ? ["사전 점검 (후보·제약 실현 가능성)", "메모 해석 (자연어 → 조건)", "희소 태그 우선 초기 배치", "2-교환 국소 탐색", "담금질(SA)로 지역 최적 탈출", "3회 시작 중 최고 해 선택"]
    : ["제출 응답 정리", "요구사항 키워드 해석", "그리디 초기 배정", "2-교환 지역 탐색으로 개선 (5회 재시작)", "제약 검증과 조화도 계산"];
  return el(`<div class="card card-pad page" role="status" aria-live="polite"><div class="loading-wrap"><div class="pulse" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.8 4.3L18 9l-4.2 1.7L12 15l-1.8-4.3L6 9l4.2-1.7z"/></svg></div>
    <h3 style="font-size:19px">팀 조합을 계산하고 있습니다</h3><p class="card-sub" style="margin-top:8px">${n}명의 응답을 기준으로 조건에 가장 잘 맞는 조합을 찾습니다</p>
    <ul class="load-steps">${steps.map(s => `<li>· ${esc(s)}</li>`).join("")}</ul>${server ? `<p class="sm muted" style="margin-top:10px">서버 AI 엔진(TeamFit)으로 계산 중</p>` : ""}</div></div>`);
}

/** 편성 실행 — 설정 화면과 결과 화면(다시 실행)이 공용으로 쓴다 */
async function runMatching(cls, opts = {}) {
  const S = cls.setup, all = participantsOf(cls), stats = rosterStats(cls);
  if (cls.result && cls.result.confirmedAt) return toast("이미 확정된 결과입니다. 결과 화면에서 ‘확정 취소’ 후 다시 실행하세요.");
  if (S.miss === "extend" && stats.pending > 0) {
    if (await confirmDialog({ title: "마감 연장 후 대기", message: `미제출 ${stats.pending}명이 있어 편성을 보류하고 설문 마감을 1일 연장합니다.`, okText: "연장하고 대기" })) {
      cls.deadline = new Date(Math.max(Date.now(), new Date(cls.deadline).getTime()) + DAY_MS).toISOString(); S.touched = true; markSaved(); toast("마감을 연장했습니다. 편성은 실행하지 않았습니다."); renderRoute(); }
    return;
  }
  const people = S.miss === "exclude" ? all.filter(p => p.submitted) : all;
  if (people.length < Math.max(2, S.size)) return toast(`배정할 인원이 부족합니다 (${people.length}명). 팀 인원(${S.size}명) 이상이 필요합니다.`);
  if (!deadlineText(cls.deadline).past && stats.pending > 0 && !opts.rerun &&
    !await confirmDialog({ title: "설문 마감 전입니다", message: `미제출 ${stats.pending}명이 있습니다. 지금 실행하면 이들은 ${S.miss === "exclude" ? "제외됩니다" : "기본값(학과·학년)으로 배정됩니다"}.`, okText: "그래도 실행" })) return;
  S.touched = true; S.seed = (S.seed || 0) + 1;
  S.weights = { ...TM.DEFAULT_WEIGHTS }; // 저장된 값이 무엇이든 실행에는 제작팀 고정 가중치만 쓴다
  const keep = cls.result && !cls.result.confirmedAt ? cls.result.teams.filter(t => t.locked) : [];
  const locked = keep.map(t => ({ no: t.no, members: t.members.map(m => people.find(p => p.id === m.id) || m) }));
  // 고정한 팀이 있으면 서버 엔진(고정 기능 없음) 대신 로컬 계산을 쓴다
  const useServer = EngineAPI.mode() === "server" && !locked.length;
  const c = $("#content"); c.innerHTML = ""; c.append(loadingCard(people.length, useServer));
  const lis = $$(".load-steps li", c); lis.forEach((li, i) => setTimeout(() => li.classList.add("on"), i * 240));
  const anim = new Promise(r => setTimeout(r, lis.length * 240 + 100));

  let teams = null, engine = null, fellBack = "";
  if (useServer) {
    const t0 = performance.now();
    try {
      const data = await EngineAPI.solve(people, S, S.seed); await anim;
      if (!data.feasible) { // 사전 점검 불가: 결과를 만들지 않고 이유를 알려 준다
        const bad = (data.precheck.items || []).filter(i => !i.ok);
        await confirmDialog({ title: "현재 조건으로는 편성할 수 없습니다", okText: "확인",
          message: bad.map(i => `· ${i.name}: ${i.detail}${i.suggestion ? `\n   → ${i.suggestion}` : ""}`).join("\n") || "사전 점검을 통과하지 못했습니다." });
        S.seed -= 1; return renderRoute();
      }
      engine = EngineAPI.summarize(data, Math.round(performance.now() - t0));
      const byId = new Map(people.map(p => [String(p.id), p]));
      teams = engine.teams.map(t => t.ids.map(id => byId.get(String(id))).filter(Boolean));
      if (teams.reduce((s, t) => s + t.length, 0) !== people.length) throw new EngineAPI.EngineUnavailable("응답의 인원이 맞지 않음");
    } catch (e) {
      if (!(e instanceof EngineAPI.EngineUnavailable)) throw e;
      teams = null; engine = null; fellBack = e.message;
    }
  }
  if (!teams) {
    await anim;
    const res = TM.solve(people.map(p => ({ ...p })), S, { seed: S.seed, locked });
    cls.result = { seed: S.seed, createdAt: new Date().toISOString(), confirmedAt: null, settings: JSON.parse(JSON.stringify(S)),
      teams: res.teams.map(t => ({ no: t.no, locked: !!t.locked, members: t.members.map(memberSnapshot) })) };
  } else {
    cls.result = { seed: S.seed, createdAt: new Date().toISOString(), confirmedAt: null, settings: JSON.parse(JSON.stringify(S)),
      teams: teams.map((t, i) => ({ no: i + 1, locked: false, members: t.map(memberSnapshot) })), engine };
  }
  markSaved();
  toast(`편성을 완료했습니다 (시드 #${S.seed}). ${engine ? "서버 AI 엔진 결과입니다. " : fellBack ? `서버 연결 실패(${fellBack}) — 로컬 계산으로 대체했습니다. ` : ""}결과를 검토하세요.`);
  nav("result/" + cls.id);
}

/* ---------- 내 설정 보관함: 저장한 편성 설정을 다른 수업에서 불러오기 ----------
   저장 대상은 팀 구성 · 하드 제약 · 주관식 요구사항 (고정/분리 쌍은 수업마다 학생이 달라 제외). 로직은 TM.snapshotSetup/applySetupSnapshot, 저장소는 store.js의 saveSetupToLibrary. */
let svSelected = null; // 직전에 저장·선택한 항목 (화면을 다시 그려도 유지)
function setupLibraryCard(cls) {
  const S = cls.setup, list = savedSetups(), a = me();
  if (!list.some(x => x.id === svSelected)) svSelected = list[0] ? list[0].id : null;
  const card = el(`<div class="card card-pad" id="svCard"><div class="card-head"><div><h3 class="card-title">내 설정 보관함</h3>
    <p class="card-sub">팀 구성·하드 제약·주관식 요구사항을 이름 붙여 저장해 두고, 다른 수업에서 불러와 그대로 쓸 수 있습니다.</p></div>
    <span class="tag tag-grey">${list.length}/${MAX_SAVED_SETUPS}</span></div>
    <div id="svLoadBox"></div>
    <form class="mt-16" id="svForm" novalidate><div class="field" style="margin-bottom:0"><label for="svName">현재 수업(${esc(cls.name)})의 설정을 저장</label>
      <div class="flex" style="flex-wrap:nowrap"><input class="input" id="svName" maxlength="${SAVED_SETUP_NAME_MAX}" placeholder="예: 캡스톤 기본 설정" autocomplete="off" style="flex:1;min-width:0">
      <button class="btn btn-ghost" id="svSave" type="submit">저장</button></div>
      <p class="help">고정·분리로 지정한 학생 쌍은 수업마다 학생이 달라 저장하지 않습니다. 같은 이름으로 저장하면 덮어씁니다.</p></div></form></div>`);

  const box = $("#svLoadBox", card);
  if (!list.length) box.append(el(`<p class="sm muted">저장해 둔 설정이 없습니다. 아래 조건을 정한 뒤 이름을 붙여 저장하면 다른 수업에서 불러올 수 있습니다.</p>`));
  else {
    box.append(el(`<div class="field" style="margin-bottom:0"><label for="svPick">저장한 설정 불러오기</label>
      <div class="flex" style="flex-wrap:nowrap"><select class="select" id="svPick" style="flex:1;min-width:0">${list.map(x => `<option value="${esc(x.id)}" ${x.id === svSelected ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
      <button class="btn" id="svLoad" type="button">이 수업에 불러오기</button><button class="btn btn-quiet" id="svDel" type="button" aria-label="선택한 저장 설정 삭제">삭제</button></div>
      <p class="help" id="svInfo" aria-live="polite"></p></div>`));
    const pick = $("#svPick", box), info = $("#svInfo", box), cur = () => getSavedSetup(pick.value);
    const drawInfo = () => { const e = cur(); if (!e) return; svSelected = e.id; const n = TM.normalizeSetupSnapshot(e.snap), note = n.note.trim();
      info.innerHTML = `${esc(TM.describeSetupSnapshot(e.snap))}<br>${esc(e.from)}에서 ${fmtDate(e.savedAt)}에 저장${note ? `<br>요구사항: “${esc(note.length > 70 ? note.slice(0, 70) + "…" : note)}”` : ""}`; };
    pick.onchange = drawInfo; drawInfo();
    $("#svLoad", box).onclick = async () => {
      const e = cur(); if (!e) return;
      if (TM.sameSetupSnapshot(TM.snapshotSetup(S), e.snap)) return toast("이미 같은 설정입니다.");
      if (!await confirmDialog({ title: `‘${e.name}’ 불러오기`, okText: "불러오기",
        message: `${cls.name}의 팀 구성·하드 제약·주관식 요구사항을 아래 내용으로 바꿉니다.\n\n${TM.describeSetupSnapshot(e.snap)}\n\n이 수업에 지정한 고정·분리 쌍은 그대로 유지됩니다.` })) return;
      TM.applySetupSnapshot(S, e.snap); markSaved(); toast(`‘${e.name}’ 설정을 불러왔습니다. 아래에서 확인하고 필요하면 수정하세요.`); renderRoute();
    };
    $("#svDel", box).onclick = async () => {
      const e = cur(); if (!e) return;
      if (!await confirmDialog({ title: "저장한 설정 삭제", message: `‘${e.name}’을(를) 보관함에서 삭제합니다. 이미 이 설정을 불러와 쓴 수업에는 영향이 없습니다.`, okText: "삭제", danger: true })) return;
      deleteSavedSetup(e.id); svSelected = null; markSaved(); toast("저장한 설정을 삭제했습니다."); renderRoute();
    };
  }
  const nameIn = $("#svName", card);
  nameIn.oninput = () => clearErr(nameIn);
  $("#svForm", card).onsubmit = async ev => {
    ev.preventDefault(); clearErr(nameIn);
    const nm = nameIn.value, dup = nm.trim() && findSavedSetup(nm);
    if (!nm.trim()) { setErr(nameIn, "저장할 이름을 입력하세요."); return nameIn.focus(); }
    if (dup && !await confirmDialog({ title: "같은 이름의 설정이 있습니다", message: `‘${dup.name}’에 현재 설정을 덮어쓸까요? 이전 내용은 복구할 수 없습니다.`, okText: "덮어쓰기" })) return;
    const r = saveSetupToLibrary(nm, cls);
    if (!r.ok) { setErr(nameIn, r.error); return nameIn.focus(); }
    svSelected = r.entry.id; markSaved(); toast(r.replaced ? `‘${r.entry.name}’을(를) 덮어썼습니다.` : `‘${r.entry.name}’(으)로 저장했습니다. 다른 수업에서 불러올 수 있습니다.`); renderRoute();
  };
  return card;
}

function renderSetup(c, arg) {
  const cls = pickClass(arg), wrap = el(`<div class="page stack"></div>`);
  if (!cls) { wrap.append(el(`<div class="card card-pad"><div class="empty"><b>개설한 수업이 없습니다</b></div></div>`)); return c.append(wrap); }
  const S = cls.setup, people = participantsOf(cls).sort((x, y) => x.n.localeCompare(y.n, "ko")), stats = rosterStats(cls);
  const manual = () => { S.touched = true; markSaved(); };

  if (cls.result && !cls.result.confirmedAt) wrap.append(el(`<div class="alert warn"><span>이 수업에는 아직 확정하지 않은 편성 결과가 있습니다. 다시 실행하면 <b>고정하지 않은 팀</b>이 새로 계산됩니다. <button class="link-btn" data-go="result/${cls.id}" type="button">결과 보기</button></span></div>`));
  if (cls.result && cls.result.confirmedAt) wrap.append(el(`<div class="alert ok"><span>이 수업은 편성이 확정되었습니다. 설정은 바꿀 수 있지만 다시 실행하려면 결과 화면에서 ‘확정 취소’가 필요합니다.</span></div>`));

  wrap.append(setupLibraryCard(cls));

  /* ---- 팀 구성 ---- */
  const comp = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">팀 구성</h3><p class="card-sub">${esc(cls.name)} · 등록 ${stats.total}명 · 제출 ${stats.done}명</p></div>
    <div><label class="sr" for="setCls">수업 선택</label><select class="select" id="setCls" style="width:auto">${db.classes.map(x => `<option value="${x.id}" ${x.id === cls.id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></div></div>
    <div class="row2"><div class="field"><label for="stSize">팀당 인원</label><select class="select" id="stSize">${[2, 3, 4, 5, 6, 7, 8].map(n => `<option ${n === S.size ? "selected" : ""}>${n}</option>`).join("")}</select></div>
    <div class="field"><label for="stRest">인원이 나누어지지 않을 때</label><select class="select" id="stRest"><option value="extra" ${S.rest === "extra" ? "selected" : ""}>일부 팀 1명 추가 (팀 수 ↓)</option><option value="fewer" ${S.rest === "fewer" ? "selected" : ""}>일부 팀 1명 감소 (팀 수 ↑)</option></select></div></div>
    <div class="field"><label for="stMiss">미제출자 처리</label><select class="select" id="stMiss"><option value="default" ${S.miss === "default" ? "selected" : ""}>기본값 배정 (학과·학년만 사용, 결과에 ‘설문 미제출’ 표시)</option>
    <option value="exclude" ${S.miss === "exclude" ? "selected" : ""}>편성 제외</option><option value="extend" ${S.miss === "extend" ? "selected" : ""}>마감 연장 (편성 보류)</option></select></div>
    <div class="alert" id="stCalc" aria-live="polite"></div></div>`);
  const calc = () => { const n = S.miss === "exclude" ? stats.done : stats.total, pl = TM.planTeamCount(n, S.size, S.rest);
    $("#stCalc", comp).innerHTML = S.miss === "extend" && stats.pending ? `미제출 ${stats.pending}명이 있어 실행하면 <b>마감을 1일 연장하고 편성을 보류</b>합니다.`
      : !n ? "배정 대상이 없습니다. 학생이 수업에 참여하고 설문을 제출해야 합니다."
      : `배정 대상 <b>${n}명</b> → <b>${pl.teams}팀</b> (${esc(TM.describePlan(pl))})${stats.pending ? ` · 미제출 ${stats.pending}명은 ${S.miss === "exclude" ? "제외" : "기본값으로 배정"}` : ""}`; };
  $("#stSize", comp).onchange = e => { S.size = +e.target.value; manual(); calc(); };
  $("#stRest", comp).onchange = e => { S.rest = e.target.value; manual(); calc(); };
  $("#stMiss", comp).onchange = e => { S.miss = e.target.value; S.touched = true; markSaved(); calc(); };
  $("#setCls", comp).onchange = e => nav("setup/" + e.target.value);
  calc(); wrap.append(comp);

  /* ---- 하드 제약 + 쌍 ---- */
  const hc = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">하드 제약</h3><p class="card-sub">반드시 지켜야 하는 조건입니다. 지키지 못하면 결과 화면에 위반으로 표시됩니다.</p></div></div>
    <label class="check"><input type="checkbox" data-h="sameMajor" ${S.hard.sameMajor ? "checked" : ""}><span>같은 학과 인원을 팀당 2명 이하로 제한한다</span></label>
    <label class="check"><input type="checkbox" data-h="evenTransfer" ${S.hard.evenTransfer ? "checked" : ""}><span>편입생·유학생을 각 팀에 고르게 배치한다 <span class="sm muted">(학적 연동이 필요해 데모에서는 모의 학생에게만 해당)</span></span></label>
    <h4 class="mt-24" style="font-size:14.5px">특정 학생 고정 · 분리</h4><div id="pl"></div>
    <form class="pair-add" id="pf"><label class="sr" for="pa">학생 A</label><select class="select" id="pa"><option value="">학생 A</option>${people.map(p => `<option value="${esc(p.id)}">${esc(p.n)} (${esc(p.sid)})</option>`).join("")}</select>
    <label class="sr" for="pb">학생 B</label><select class="select" id="pb"><option value="">학생 B</option>${people.map(p => `<option value="${esc(p.id)}">${esc(p.n)} (${esc(p.sid)})</option>`).join("")}</select>
    <label class="sr" for="pt">유형</label><select class="select" id="pt"><option value="fix">같은 팀 고정</option><option value="split">다른 팀 분리</option></select><button class="btn btn-ghost" type="submit">추가</button></form></div>`);
  $$("[data-h]", hc).forEach(ch => ch.onchange = () => { S.hard[ch.dataset.h] = ch.checked; manual(); });
  const nameOf = id => (people.find(p => p.id === id) || { n: "(명단에 없음)" }).n;
  const drawPairs = () => { const box = $("#pl", hc); box.innerHTML = ""; if (!S.pairs.length) box.append(el(`<p class="sm muted">지정한 쌍이 없습니다.</p>`));
    S.pairs.forEach((p, i) => { const r = el(`<div class="pair-row"><span class="tag ${p.type === "fix" ? "tag-mint" : "tag-amber"}">${p.type === "fix" ? "같은 팀" : "분리"}</span><span>${esc(nameOf(p.a))} · ${esc(nameOf(p.b))}</span><span class="grow"></span><button class="x-btn" type="button" aria-label="쌍 삭제">×</button></div>`);
      $("button", r).onclick = () => { S.pairs.splice(i, 1); manual(); drawPairs(); }; box.append(r); }); };
  $("#pf", hc).onsubmit = ev => { ev.preventDefault(); const A = $("#pa", hc), B = $("#pb", hc), T = $("#pt", hc); clearErr(A); clearErr(B);
    if (!A.value) return setErr(A, "학생 A를 선택하세요."); if (!B.value) return setErr(B, "학생 B를 선택하세요."); if (A.value === B.value) return setErr(B, "서로 다른 학생을 선택하세요.");
    const same = (p) => (p.a === A.value && p.b === B.value) || (p.a === B.value && p.b === A.value);
    if (S.pairs.some(p => same(p) && p.type === T.value)) return setErr(B, "이미 지정한 쌍입니다.");
    if (S.pairs.some(p => same(p) && p.type !== T.value)) return setErr(B, "같은 쌍에 ‘고정’과 ‘분리’를 동시에 지정할 수 없습니다.");
    S.pairs.push({ a: A.value, b: B.value, type: T.value }); manual(); A.value = B.value = ""; drawPairs(); };
  drawPairs(); wrap.append(hc);

  /* ---- 요구사항 ---- */
  const nc = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">주관식 요구사항</h3><p class="card-sub">문장에서 조건을 뽑아 편성에 반영하고 결과에서 검증합니다</p></div></div>
    <label class="sr" for="stNote">요구사항</label><textarea class="textarea" id="stNote" maxlength="500" style="min-height:120px">${esc(S.note)}</textarea>
    <p class="help"><span id="nl">${S.note.length}</span>/500</p><p class="help">서버 AI 엔진으로 실행하면 이 메모를 서버가 직접 해석하므로 아래 체크 해제는 적용되지 않습니다. 편입생 분산과 팀 고정은 서버 엔진이 지원하지 않습니다(고정한 팀이 있으면 로컬 계산을 사용).</p><div class="mt-16"><b style="font-size:13.5px;color:var(--navy-soft)">해석된 조건</b></div><div id="pc"></div>
    <p class="help">데모 해석기는 <b>‘발표’, ‘개발/코딩/구현’, ‘디자인/UI/UX’, ‘N학년 … 몰리지/분산/최대/이하’</b> 키워드만 인식합니다. 실제 서비스에서는 LLM이 대신하며, 해석 결과는 이 화면에서 직접 확인하게 됩니다.</p></div>`);
  const drawParsed = () => { const box = $("#pc", nc); box.innerHTML = ""; const conds = TM.parseNote(S.note);
    if (!conds.length) return box.append(el(`<p class="sm muted mt-8">${S.note.trim() ? "인식된 조건이 없습니다. 위 키워드를 포함해 다시 써 보세요." : "요구사항을 입력하면 해석 결과가 여기에 표시됩니다."}</p>`));
    conds.forEach(cd => { const r = el(`<div class="parse-row"><input type="checkbox" id="pr-${cd.id}" ${S.parsedOff[cd.id] ? "" : "checked"}><label class="p-txt" for="pr-${cd.id}">${esc(cd.text)}</label><span class="tag ${cd.kind === "hard" ? "tag-amber" : "tag-grey"}">${cd.kind === "hard" ? "하드 제약" : "권장"}</span></div>`);
      $("input", r).onchange = e => { if (e.target.checked) delete S.parsedOff[cd.id]; else S.parsedOff[cd.id] = true; S.touched = true; markSaved(); }; box.append(r); }); };
  $("#stNote", nc).oninput = e => { S.note = e.target.value; $("#nl", nc).textContent = S.note.length; S.touched = true; drawParsed(); save(); };
  drawParsed(); wrap.append(nc);

  /* ---- 설문 템플릿 ---- */
  wrap.append(el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">학생 설문 문항</h3><p class="card-sub">템플릿: ${esc(cls.kind)} · 필수 4개 + 선택 1개 (응답 3분 이내)</p></div></div>
    ${(SURVEY[cls.kind] || SURVEY["개발 프로젝트"]).map((q, i) => `<div class="role-row"><span class="grow" style="color:var(--navy);font-weight:500">${esc(q)}</span><span class="tag tag-grey" ${i < 4 ? 'style="color:var(--navy);font-weight:600"' : ""}>${i < 4 ? "필수" : "선택"}</span></div>`).join("")}
    <div class="flex mt-16"><button class="btn btn-ghost btn-sm" type="button" disabled title="데모에서는 지원하지 않습니다">문항 추가 (준비 중)</button><button class="btn btn-ghost btn-sm" type="button" disabled title="데모에서는 지원하지 않습니다">다른 템플릿 (준비 중)</button></div></div>`));

  const bar = el(`<div class="wizard-nav"><button class="btn btn-ghost" id="stSave" type="button">임시 저장</button><button class="btn" id="stRun" type="button">저장 후 매칭 실행</button></div>`);
  $("#stSave", bar).onclick = () => { S.touched = true; markSaved(); toast("편성 조건을 저장했습니다. (변경 사항은 자동으로도 저장됩니다)"); };
  $("#stRun", bar).onclick = () => runMatching(cls);
  wrap.append(bar); c.append(wrap); bindGo(wrap);
}
