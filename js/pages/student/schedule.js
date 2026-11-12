/* 일정(학생) — 84칸을 클릭 한 칸씩 바꾸지 않아도 되도록 '칠하기' 도구 + 드래그 + 요일/시간 일괄 적용 */
function renderSchedule(c) {
  const a = me(); a.schedule = a.schedule || {};
  const label = { y: "가능", n: "불가", "": "미정" }; let mode = "y", painting = false, last = null, dirty = false;
  const wrap = el(`<div class="page stack"></div>`);
  const card = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">주간 시간표 (1시간 단위)</h3>
    <p class="card-sub">도구를 고른 뒤 칸을 누르거나 드래그해 칠하세요. 요일·시간 머리글을 누르면 한 줄이 한 번에 칠해집니다. 변경은 자동 저장됩니다.</p></div>
    <button class="btn btn-ghost btn-sm" id="clr" type="button">전체 지우기</button></div>
    <div class="paint-bar" role="radiogroup" aria-label="칠하기 도구"><span class="lab">도구</span></div>
    <div class="scroll-x"><table class="sched" aria-label="주간 가능 시간표"><thead><tr><th><span class="sr">시간</span></th>${DAYS.map(d => `<th scope="col"><button type="button" class="hd" data-day="${d}" aria-label="${d}요일 전체 칠하기">${d}</button></th>`).join("")}</tr></thead>
    <tbody>${BLOCKS.map(([lb, nm], i) => `<tr><th scope="row"><button type="button" class="hd" data-row="${i}" aria-label="${lb}시 전체 칠하기">${lb}<br><small>${nm}</small></button></th>${DAYS.map(d => `<td><button type="button" class="slot" data-k="${slotKey(d, i)}"></button></td>`).join("")}</tr>`).join("")}</tbody></table></div>
    <div class="legend"><span><i style="background:var(--mint-050);border:1.5px solid var(--mint)"></i>가능</span><span><i style="background:var(--rose-050);border:1.5px solid var(--rose)"></i>불가</span>
    <span><i style="background:var(--surface-2);border:1.5px solid var(--line-strong)"></i>미정</span><span class="muted" id="cnt" style="margin-left:auto"></span></div></div>`);
  const tools = [["y", "가능으로 칠하기"], ["n", "불가로 칠하기"], ["", "지우기"]];
  tools.forEach(([m, t]) => { const b = el(`<button type="button" class="chip" role="radio" aria-checked="${m === mode}" aria-pressed="${m === mode}">${t}</button>`);
    b.onclick = () => { mode = m; $$(".paint-bar .chip", card).forEach(x => { const on = x === b; x.setAttribute("aria-pressed", on); x.setAttribute("aria-checked", on); }); }; $(".paint-bar", card).append(b); });

  const paint = (btn) => { const k = btn.dataset.k; if (mode === "") delete a.schedule[k]; else a.schedule[k] = mode;
    const s = a.schedule[k] || ""; btn.dataset.s = s; btn.textContent = label[s] === "미정" ? "" : label[s]; btn.setAttribute("aria-label", `${slotLabel(k)} ${label[s]}`); dirty = true; };
  const count = () => { const v = Object.values(a.schedule); const y = v.filter(x => x === "y").length, n = v.filter(x => x === "n").length; $("#cnt", card).textContent = `가능 ${y} · 불가 ${n} · 미정 ${ALL_SLOTS.length - y - n}`; };
  const end = () => { if (dirty) { markSaved(); dirty = false; } painting = false; last = null; count(); };
  $$(".slot", card).forEach(b => { const s = a.schedule[b.dataset.k] || ""; b.dataset.s = s; b.textContent = label[s] === "미정" ? "" : label[s]; b.setAttribute("aria-label", `${slotLabel(b.dataset.k)} ${label[s]}`); });
  const table = $(".sched", card);
  table.addEventListener("pointerdown", e => { const b = e.target.closest(".slot"); if (!b) return; e.preventDefault(); painting = true; last = b; paint(b); try { table.setPointerCapture(e.pointerId); } catch (x) { /* noop */ } });
  table.addEventListener("pointermove", e => { if (!painting) return; const t = document.elementFromPoint(e.clientX, e.clientY), b = t && t.closest && t.closest(".slot"); if (b && b !== last && table.contains(b)) { last = b; paint(b); } });
  ["pointerup", "pointercancel"].forEach(ev => table.addEventListener(ev, end));
  table.addEventListener("click", e => { const b = e.target.closest(".slot"); if (b && e.detail === 0) { paint(b); end(); } }); // 키보드 Enter/Space
  $$("[data-day]", card).forEach(h => h.onclick = () => { BLOCKS.forEach((_, i) => paint($(`.slot[data-k="${slotKey(h.dataset.day, i)}"]`, card))); end(); });
  $$("[data-row]", card).forEach(h => h.onclick = () => { DAYS.forEach(d => paint($(`.slot[data-k="${slotKey(d, +h.dataset.row)}"]`, card))); end(); });
  $("#clr", card).onclick = async () => { if (await confirmDialog({ title: "시간표 지우기", message: "표시한 모든 가능·불가 시간을 지웁니다.", okText: "지우기", danger: true })) { a.schedule = {}; markSaved(); renderRoute(); } };
  count(); wrap.append(card);

  /* 참여 중인 팀의 공통 가능 시간 (실제 계산) */
  if (a.projects.length) {
    const box = el(`<div class="card card-pad"><div class="card-head"><div><h3 class="card-title">내 팀의 공통 가능 시간</h3><p class="card-sub">내 시간표를 바꾸면 결과가 함께 바뀝니다</p></div></div></div>`);
    a.projects.forEach(p => { const m = liveMembers(p), ov = TM.intersect(m.map(x => x.sched || [])), w = bestWindows(ov);
      box.append(el(`<div class="proj-item"><span class="pi-ico" aria-hidden="true">${esc(initial(p.name))}</span><div class="grow"><h4>${esc(p.name)}</h4>
        <div class="meta">전원 가능 ${ov.length}시간${w.length ? " · 추천: " + esc(w[0]) : " · 겹치는 시간 없음"}</div></div></div>`)); });
    wrap.append(box);
  }
  c.append(wrap);
}
