/* 매칭 결과 — 교수(검토·교환·고정·확정) / 조교(확정 후 열람만)
   · 점수·제약은 저장된 값이 아니라 현재 팀 구성에서 매번 다시 계산한다 (교환해도 항상 정확)
   · prompt()/confirm() 대신 '클릭해서 선택 → 다른 팀 학생을 클릭해 교환' + <dialog> 확인창 */
function renderProfResult(c, arg, opts = {}) {
  const ta = !!opts.ta, a = me(), list = ta ? taClasses(a.email) : db.classes, cls = pickClass(arg, list);
  let sel = null;
  const pick = () => { const w = el(`<div class="page"></div>`); return w; };
  if (!cls) { const w = pick(); w.append(el(`<div class="card card-pad"><div class="empty"><b>${ta ? "조교로 지정된 수업이 없습니다" : "개설한 수업이 없습니다"}</b></div></div>`)); return c.append(w); }

  const render = () => {
    const y = window.scrollY; c.innerHTML = ""; const wrap = pick(), res = cls.result;
    const head = el(`<div class="card card-pad mb-16"><div class="card-head"><div><h3 class="card-title">${esc(cls.name)} 편성 결과</h3><p class="card-sub" id="rsub"></p></div>
      <div class="flex-end"><label class="sr" for="clsPick">수업 선택</label><select class="select" id="clsPick" style="width:auto">${list.map(x => `<option value="${x.id}" ${x.id === cls.id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select><span id="acts" class="flex-end"></span></div></div><div id="hbody"></div></div>`);
    $("#clsPick", head).onchange = e => nav((ta ? "ta-result/" : "result/") + e.target.value);
    wrap.append(head); c.append(wrap);
    if (!res) { $("#rsub", head).textContent = "확정 전까지 학생에게 공개되지 않습니다";
      $("#hbody", head).append(el(`<div class="empty"><b>${ta ? "아직 편성 결과가 없습니다" : "아직 편성을 실행하지 않았습니다"}</b>${ta ? "교수가 편성을 확정하면 열람할 수 있습니다." : "편성 설정에서 조건을 정하고 매칭을 실행하세요."}</div>`));
      if (!ta) { const b = el(`<button class="btn mt-16" type="button">편성 설정으로 가기</button>`), ctr = el(`<div class="center"></div>`); b.onclick = () => nav("setup/" + cls.id); ctr.append(b); $("#hbody", head).append(ctr); } return; }
    if (ta && !res.confirmedAt) { $("#rsub", head).textContent = "조교는 확정 후에 열람할 수 있습니다";
      return $("#hbody", head).append(el(`<div class="alert"><span aria-hidden="true">🔒</span><span>매칭 결과는 교수가 팀을 확정·공개한 뒤에 열람할 수 있습니다.</span></div>`)); }

    const confirmed = !!res.confirmedAt, readOnly = ta || confirmed, teams = res.teams;
    const ev = TM.evaluate(teams, res.settings), ew = TM.effectiveWeights(res.settings.weights);
    const people = teams.reduce((s, t) => s + t.members.length, 0), unsub = teams.reduce((s, t) => s + t.members.filter(m => !m.submitted).length, 0);
    $("#rsub", head).textContent = `${confirmed ? `확정 ${fmtDT(res.confirmedAt)} · 학생에게 공개됨` : "확정 전까지 학생에게 공개되지 않습니다"} · 실행 ${fmtDT(res.createdAt)} · 시드 #${res.seed}`;

    const acts = $("#acts", head);
    const csv = el(`<button class="btn btn-ghost btn-sm" type="button">결과 CSV</button>`);
    csv.onclick = () => downloadCSV(`${cls.name}_편성결과.csv`, [["팀", "팀 조화도", "이름", "학번", "학과", "학년", "희망 역할", "설문 제출"],
      ...teams.flatMap((t, i) => t.members.map(m => [t.no, ev.per[i].metrics.score, m.n, m.sid, m.m, m.yearLabel || m.y, (m.roles || []).join("/"), m.submitted ? "제출" : "미제출"]))]);
    acts.append(csv);
    if (!ta) {
      const cond = el(`<button class="btn btn-ghost btn-sm" type="button">조건 수정</button>`); cond.onclick = () => nav("setup/" + cls.id);
      const re = el(`<button class="btn btn-ghost btn-sm" type="button" ${confirmed ? "disabled title=\"확정을 취소해야 다시 실행할 수 있습니다\"" : ""}>다시 실행</button>`);
      re.onclick = async () => { if (await confirmDialog({ title: "다시 실행", message: "현재 결과를 새 결과로 교체합니다. 직접 교환한 내용은 사라지고, 고정한 팀은 유지됩니다.", okText: "다시 실행" })) runMatching(cls, { rerun: true }); };
      const cf = el(confirmed ? `<button class="btn btn-ghost btn-sm" type="button">확정 취소</button>` : `<button class="btn btn-sm" type="button">팀 확정 및 공개</button>`);
      cf.onclick = async () => {
        if (!confirmed) {
          if (!await confirmDialog({ title: "팀 확정 및 공개", message: `${ev.errors ? `제약 위반 ${ev.errors}건이 남아 있습니다. ` : ""}${teams.length}개 팀을 확정하고 학생에게 공개합니다.\n확정하면 교환·다시 실행이 잠기며, 확정 취소로 되돌릴 수 있습니다.`, okText: "확정" })) return;
          res.confirmedAt = new Date().toISOString(); const n = publishProjects(cls); markSaved(); renderNav();
          toast(`${teams.length}개 팀을 확정했습니다. 실제 계정 ${n}명에게 팀 공간이 열렸습니다.`);
        } else {
          if (!await confirmDialog({ title: "확정 취소", message: "학생에게 열린 팀 공간(첫 모임 준비 체크, 역할 분배, 협업 규범 응답)이 모두 삭제됩니다.", okText: "확정 취소", danger: true })) return;
          res.confirmedAt = null; withdrawProjects(cls); markSaved(); renderNav(); toast("확정을 취소했습니다.");
        }
        render();
      };
      acts.append(cond, re, cf);
    }

    $("#hbody", head).append(el(`<div class="result-summary" style="margin-bottom:0"><div class="stat"><div class="n">${teams.length}팀</div><div class="l">생성된 팀</div></div>
      <div class="stat"><div class="n">${ev.avg}<span class="muted" style="font-size:14px">/100</span></div><div class="l">평균 조화도 (최저 ${ev.min})</div></div>
      <div class="stat"><div class="n">${people}명</div><div class="l">배정 인원${unsub ? ` · 미제출 ${unsub}` : ""}</div></div>
      <div class="stat"><div class="n" style="color:${ev.errors ? "var(--rose)" : "var(--mint)"}">${ev.errors}건</div><div class="l">제약 위반${ev.warns ? ` · 주의 ${ev.warns}` : ""}</div></div></div>`));

    if (ev.issues.length) wrap.append(el(`<div class="alert ${ev.errors ? "error" : "warn"} mb-16" style="display:block"><b>${ev.errors ? "충족하지 못한 조건이 있습니다" : "참고할 사항이 있습니다"}</b>
      <ul class="issue-list">${ev.issues.map(i => `<li><span class="lv ${i.level}">${i.level === "error" ? "위반" : "주의"}</span><span>${i.team ? `팀 ${i.team} · ` : ""}${esc(i.text)}</span></li>`).join("")}</ul>
      ${readOnly ? "" : `<p class="sm mt-8">학생 카드를 눌러 선택한 뒤 다른 팀 학생을 누르면 서로 교환됩니다. 점수와 위반은 즉시 다시 계산됩니다.</p>`}</div>`));
    else wrap.append(el(`<div class="alert ok mb-16">설정한 하드 제약과 해석된 요구사항을 모두 충족했습니다.</div>`));

    if (sel) { const who = teams.flatMap(t => t.members).find(m => m.id === sel.id); wrap.append(el(`<div class="alert swap-hint mb-16" role="status"><span><b>${esc(who ? who.n : "")}</b> 선택됨 — 교환할 다른 팀의 학생을 누르세요. (Esc로 취소)</span></div>`)); }

    const grid = el(`<div class="team-grid"></div>`);
    teams.forEach((t, i) => { const m = ev.per[i].metrics, is = ev.per[i].issues, cls2 = m.score >= 80 ? "" : m.score >= 65 ? "mid" : "low";
      const card = el(`<article class="team-card ${t.locked ? "locked" : ""} ${is.some(x => x.level === "error") ? "issue" : ""}"><div class="tc-top"><h4>팀 ${t.no}${t.locked ? ' <span class="tag tag-grey">고정</span>' : ""}</h4>
        <div class="score ${cls2}"><span class="s">${m.score}</span><span class="t">/100</span></div></div><div class="score-bar ${cls2}"><i style="width:${m.score}%"></i></div><div class="tc-mem"></div>
        <div class="parts">${[["major", "전공 다양", m.parts.major], ["role", "역할 균형", m.parts.role], ["time", "일정 호환", m.parts.time], ["trait", "성향 호환", m.parts.trait]].map(([k, l, v]) => `<div class="pt ${!ew.equal && ew[k] === 0 ? "off" : ""}"><span>${l}</span><span class="score-bar"><i style="width:${Math.round(v)}%"></i></span><span>${Math.round(v)}</span></div>`).join("")}</div>
        <div class="tc-foot"><span class="tc-fact">전공 ${m.majors}개</span><span class="tc-fact">역할 ${m.rolesCovered}/6</span><span class="tc-fact">전원 가능 ${m.overlap}시간</span><span class="tc-fact">성향 ${m.traitPct}%</span></div>
        ${is.length ? `<ul class="issue-list">${is.map(x => `<li><span class="lv ${x.level}">${x.level === "error" ? "위반" : "주의"}</span><span>${esc(x.text)}</span></li>`).join("")}</ul>` : ""}
        ${readOnly ? "" : `<div class="mt-8"><button class="btn btn-quiet btn-sm" data-a="lock" type="button">${t.locked ? "고정 해제" : "이 팀 고정"}</button></div>`}</article>`);
      t.members.forEach(mm => { const on = sel && sel.id === mm.id;
        const row = el(`<div class="member ${readOnly ? "" : "pick"} ${on ? "sel" : ""}"><span class="avatar" aria-hidden="true">${esc(initial(mm.n))}</span><span class="grow"><span class="m-nm block">${esc(mm.n)}${mm.submitted ? "" : '<span class="miss">설문 미제출</span>'}</span>
          <span class="m-mt">${esc(mm.m)} · ${esc(mm.yearLabel || mm.y + "학년")}</span></span><span class="tag tag-grey m-role">${esc((mm.roles || [])[0] || "역할 미정")}</span></div>`);
        if (!readOnly) { makeClickable(row, () => {
          if (t.locked) return toast("고정된 팀입니다. ‘고정 해제’ 후 교환하세요.");
          if (!sel || sel.no === t.no) { sel = on ? null : { no: t.no, id: mm.id }; return render(); }
          const A = teams.find(x => x.no === sel.no), i1 = A.members.findIndex(x => x.id === sel.id), j1 = t.members.findIndex(x => x.id === mm.id);
          const a1 = A.members[i1]; A.members[i1] = t.members[j1]; t.members[j1] = a1; sel = null; markSaved(); toast(`${a1.n} ↔ ${mm.n} 교환했습니다. 점수를 다시 계산했습니다.`); render();
        }, `${mm.n} 선택`); row.setAttribute("aria-pressed", String(!!on)); }
        $(".tc-mem", card).append(row); });
      const lk = $("[data-a=lock]", card); if (lk) lk.onclick = () => { t.locked = !t.locked; markSaved(); render(); };
      grid.append(card); });
    wrap.append(grid);
    if (window._resEsc) document.removeEventListener("keydown", window._resEsc);
    window._resEsc = e => { if (e.key === "Escape" && sel) { sel = null; render(); } }; document.addEventListener("keydown", window._resEsc);
    window.scrollTo({ top: y });
  };
  render();
}
