/* 프로젝트(학생) — 편성 확정 후 열리는 팀 공간 (초반 협업 착수 지원)
   범위 원칙(기획안 1-3): 진행 관리는 하지 않는다 → '진행률' 대신 '첫 모임 준비 n/4'만 보여준다 */
const AGENDA = ["프로젝트 목표 확인", "역할 초안 논의", "협업 규범 정하기", "다음 회의 일정 확정"];
const NORMS = [
  { k: "comm", t: "소통 빈도", opts: ["주 1회 이하", "주 2회 이상", "매일"] },
  { k: "deadline", t: "마감 기한 태도", opts: ["미리 완료", "마감 집중"] },
  { k: "decide", t: "의사결정 방식", opts: ["다수결", "담당자 결정", "전원 합의"] }
];
const hashStr = s => [...String(s)].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7);
const liveMembers = p => p.team.map(m => (m.email && acct(m.email)) ? { ...m, sched: sched(acct(m.email)), submitted: true } : m);

/** 전원이 가능한 연속 구간(요일별) 중 긴 순서 */
function bestWindows(slots, limit = 3) {
  const set = new Set(slots), out = [];
  DAYS.forEach(d => { let s = null; for (let i = 0; i <= BLOCKS.length; i++) {
    const on = i < BLOCKS.length && set.has(slotKey(d, i));
    if (on && s === null) s = i; if (!on && s !== null) { out.push({ d, from: s, to: i - 1, len: i - s }); s = null; } } });
  return out.sort((x, y) => y.len - x.len || DAYS.indexOf(x.d) - DAYS.indexOf(y.d)).slice(0, limit)
    .map(w => `${w.d} ${BLOCKS[w.from][0].split("–")[0]}–${BLOCKS[w.to][0].split("–")[1]}시 (${w.len}시간)`);
}

function renderProjects(c, id) {
  const a = me(), wrap = el(`<div class="page"></div>`);
  if (id) { const p = a.projects.find(x => x.id === id); if (p) return renderProjectDetail(c, a, p); toast("프로젝트를 찾을 수 없습니다."); }
  if (!a.projects.length) { wrap.append(el(`<div class="card card-pad"><div class="empty"><b>참여 중인 프로젝트가 없습니다</b>교수가 편성을 확정하면 팀 공간이 자동으로 열립니다.</div>
    <div class="center mt-16"><button class="btn btn-ghost" data-go="readiness">매칭 준비로 가기</button></div></div>`)); c.append(wrap); return bindGo(wrap); }
  const grid = el(`<div class="team-grid"></div>`);
  a.projects.forEach(p => {
    const n = p.agenda.filter(Boolean).length;
    const card = el(`<article class="team-card"><div class="tc-top"><h4>${esc(p.name)}</h4><span class="tag ${n === 4 ? "tag-mint" : "tag-amber"}">${n === 4 ? "준비 완료" : "첫 모임 준비 중"}</span></div>
      <p class="card-sub">${esc(p.course)} · 팀원 ${p.team.length}명</p>
      <div class="bar mt-16"><i style="width:${n * 25}%"></i></div><p class="sm muted mt-8">첫 모임 준비 ${n}/4</p>
      <div class="tc-foot">${p.team.slice(0, 4).map(m => `<span class="tc-fact">${esc(m.n)} · ${esc(m.roles[0] || "역할 미정")}</span>`).join("")}</div></article>`);
    makeClickable(card, () => nav("projects/" + p.id), `${p.name} 열기`); grid.append(card);
  });
  wrap.append(grid); c.append(wrap);
}

function renderProjectDetail(c, a, p) {
  const members = liveMembers(p), n = members.length, overlap = TM.intersect(members.map(m => m.sched || []));
  const wrap = el(`<div class="page"><button class="back-link" type="button">← 프로젝트 목록</button><div class="stack"></div></div>`);
  $(".back-link", wrap).onclick = () => nav("projects"); const st = $(".stack", wrap);
  const done = () => p.agenda.filter(Boolean).length;

  st.append(el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">${esc(p.name)}</h3>
    <p class="card-sub">${esc(p.course)} · 팀원 ${n}명 · 편성 확정 ${fmtDate(p.createdAt)}</p></div><span class="tag tag-grey">팀 공간</span></div>
    <p class="sm muted">이 화면의 목표는 ‘첫 모임 전 준비 끝내기’입니다. 이후 진행 관리는 아래 외부 도구에서 이어가세요.</p></div>`));

  /* 아젠다 */
  const ag = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">첫 모임 준비</h3><p class="card-sub">네 가지를 끝내면 첫 회의에서 바로 작업을 시작할 수 있습니다</p></div>
    <span class="tag tag-grey" id="agc">${done()}/4</span></div><ul class="agenda"></ul></div>`);
  AGENDA.forEach((t, i) => {
    const li = el(`<li class="${p.agenda[i] ? "done" : ""}"><input type="checkbox" id="ag${i}" ${p.agenda[i] ? "checked" : ""}><label for="ag${i}">${esc(t)}</label></li>`);
    $("input", li).onchange = e => { p.agenda[i] = e.target.checked; li.classList.toggle("done", e.target.checked); $("#agc", ag).textContent = done() + "/4"; markSaved(); };
    $(".agenda", ag).append(li);
  });
  st.append(ag);

  /* 공통 가능 시간 — 실제 교집합 */
  const win = bestWindows(overlap), grid = heatGrid(members);
  st.append(el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">공통 가능 시간</h3>
    <p class="card-sub">팀원 ${n}명의 가능 시간을 겹쳐 계산했습니다 · 숫자는 가능한 인원, 진한 칸은 전원 가능</p></div>
    <span class="tag ${overlap.length ? "tag-mint" : "tag-amber"}">전원 가능 ${overlap.length}시간</span></div><div id="hg"></div>
    <p class="help mt-16">${win.length ? "추천 회의 시간: " + win.map(esc).join(" · ") : "전원이 겹치는 시간이 없습니다. 일부 팀원에게 시간 조정을 요청하거나 온라인 비동기 회의를 고려하세요."}</p></div>`));
  $("#hg", st).append(grid);

  /* 팀원 프로필 요약 + 역할 분배 */
  const roleCard = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">팀원 · 역할 분배</h3><p class="card-sub">역할마다 담당자를 정하세요. 미배정 역할은 경고로 표시됩니다</p></div><span class="tag" id="rw"></span></div>
    <div id="mem"></div><div class="mt-16" id="roles"></div></div>`);
  members.forEach(m => $("#mem", roleCard).append(el(`<div class="member"><span class="avatar" ${m.email === a.email ? 'style="background:var(--indigo)"' : ""}>${esc(initial(m.n))}</span>
    <span class="grow"><span class="m-nm block">${esc(m.n)}${m.email === a.email ? " (나)" : ""}</span><span class="m-mt">${esc(m.m)} · ${esc(m.yearLabel || m.y + "학년")}${m.skills?.length ? " · " + esc(m.skills.slice(0, 3).join(", ")) : ""}</span></span>
    <span class="chips">${(m.roles || []).map(r => `<span class="tag tag-grey">${esc(r)}</span>`).join("")}</span></div>`)));
  const warn = () => { const u = ROLES.filter(r => !p.roleMap[r]).length; const t = $("#rw", roleCard); t.textContent = u ? `미배정 ${u}` : "모두 배정"; t.className = "tag " + (u ? "tag-amber" : "tag-mint"); };
  ROLES.forEach(r => {
    const sel = el(`<select class="select" id="role-${r}" aria-label="${r} 담당자"><option value="">미배정</option>${members.map(m => `<option value="${esc(m.id)}" ${p.roleMap[r] === m.id ? "selected" : ""}>${esc(m.n)}</option>`).join("")}</select>`);
    sel.onchange = () => { p.roleMap[r] = sel.value || null; warn(); markSaved(); };
    $("#roles", roleCard).append(el(`<div class="role-row"><label class="r-nm" for="role-${r}">${r}</label><span class="grow"></span></div>`));
    $("#roles .role-row:last-child .grow", roleCard).append(sel);
  });
  warn(); st.append(roleCard);

  /* 협업 규범 합의 */
  const ans = (m, k) => (p.norms[m.id] && p.norms[m.id][k]) || (m.email === a.email ? "" : NORMS.find(x => x.k === k).opts[hashStr(m.id + k) % NORMS.find(x => x.k === k).opts.length]);
  const nc = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">협업 규범 합의</h3><p class="card-sub">내 답변을 고르면 팀 응답이 함께 표시됩니다 (다른 팀원 응답은 데모 값)</p></div><span class="tag tag-grey" id="nr"></span></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>항목</th><th>내 답변</th><th>팀 응답</th></tr></thead><tbody></tbody></table></div><div id="nhint" class="mt-16"></div></div>`);
  const drawNorms = () => {
    const tb = $("tbody", nc); tb.innerHTML = ""; let answered = 0, split = [];
    NORMS.forEach(q => {
      const cnt = {}; members.forEach(m => { const v = ans(m, q.k); if (v) cnt[v] = (cnt[v] || 0) + 1; });
      if (a.email && members.some(m => m.email === a.email) && ans(members.find(m => m.email === a.email), q.k)) answered++;
      if (Object.keys(cnt).length > 1 && Math.max(...Object.values(cnt)) < Math.ceil(n * 0.75)) split.push(q.t);
      const tr = el(`<tr><td>${q.t}</td><td><select class="select" aria-label="내 ${q.t}"><option value="">선택</option>${q.opts.map(o => `<option ${ (p.norms[members.find(m => m.email === a.email)?.id]?.[q.k]) === o ? "selected" : ""}>${o}</option>`).join("")}</select></td>
        <td class="sm">${Object.entries(cnt).map(([k, v]) => `${esc(k)} ${v}`).join(" · ") || "—"}</td></tr>`);
      $("select", tr).onchange = e => { const mid = members.find(m => m.email === a.email)?.id; if (!mid) return; p.norms[mid] = { ...(p.norms[mid] || {}), [q.k]: e.target.value }; markSaved(); drawNorms(); };
      tb.append(tr);
    });
    $("#nr", nc).textContent = `내 응답 ${answered}/3`;
    $("#nhint", nc).innerHTML = split.length ? `<div class="alert warn">‘${split.map(esc).join("’, ‘")}’은(는) 의견이 갈립니다. 첫 모임에서 절충안을 정해 두면 초반 갈등을 줄일 수 있습니다.</div>` : `<div class="alert ok">팀 응답이 대체로 일치합니다.</div>`;
  };
  drawNorms(); st.append(nc);

  /* 외부 도구 */
  const lk = el(`<form class="card card-pad" novalidate><div class="card-head"><div><h3 class="card-title">외부 협업 도구</h3><p class="card-sub">이후 진행은 연결한 도구에서 이어갑니다 · TeamMatch는 진행 관리를 대신하지 않습니다</p></div></div>
    <div class="field"><label for="lnNotion">Notion 주소</label><input class="input" id="lnNotion" inputmode="url" placeholder="https://www.notion.so/…" value="${esc(p.links.notion)}"></div>
    <div class="field"><label for="lnGit">GitHub 저장소 주소</label><input class="input" id="lnGit" inputmode="url" placeholder="https://github.com/org/repo" value="${esc(p.links.github)}"></div>
    <button class="btn btn-ghost btn-sm" type="submit">주소 저장</button></form>`);
  const okUrl = v => { try { const u = new URL(v); return u.protocol === "https:" || u.protocol === "http:"; } catch (e) { return false; } };
  lk.addEventListener("submit", ev => { ev.preventDefault(); clearAllErr(lk); let bad = false;
    [["lnNotion", "notion"], ["lnGit", "github"]].forEach(([id, key]) => { const i = $("#" + id, lk), v = i.value.trim(); if (v && !okUrl(v)) { setErr(i, "https:// 로 시작하는 올바른 주소를 입력하세요."); bad = true; } else p.links[key] = v; });
    if (!bad) { markSaved(); toast("연결 주소를 저장했습니다."); } });
  st.append(lk); c.append(wrap);
}
