/* =================================================================
   router.js — 해시 라우팅 + 사이드바
   · 주소가 #/페이지[/인자] 로 바뀌므로 뒤로가기·새로고침·링크 공유가 동작한다
   · 로그인 안 했거나 권한 없는 화면이면 렌더하지 않는다 (라우트 가드)
   · 렌더 오류가 나도 빈 화면 대신 복구 안내를 보여준다
================================================================= */
const ICONS = {
  dash: '<rect x="3" y="3" width="7" height="8" rx="2"/><rect x="14" y="3" width="7" height="5" rx="2"/><rect x="14" y="11" width="7" height="10" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/>',
  spark: '<path d="M12 3l1.8 4.3L18 9l-4.2 1.7L12 15l-1.8-4.3L6 9l4.2-1.7z"/><path d="M18.5 15.5l.8 1.9 1.9.8-1.9.8-.8 1.9-.8-1.9-1.9-.8 1.9-.8z"/>',
  folder: '<path d="M3 7.5A2.5 2.5 0 015.5 5H9l2 2.5h7.5A2.5 2.5 0 0121 10v7.5A2.5 2.5 0 0118.5 20h-13A2.5 2.5 0 013 17.5z"/>',
  user: '<circle cx="12" cy="8" r="3.6"/><path d="M4.5 20c.6-3.8 3.7-6 7.5-6s6.9 2.2 7.5 6"/>',
  cal: '<rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 9.5h17M8.5 3v4M15.5 3v4"/>',
  sliders: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2.2"/><circle cx="10" cy="17" r="2.2"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  badge: '<circle cx="12" cy="9" r="4"/><path d="M8.5 12.5L7 21l5-2.4L17 21l-1.5-8.5"/>'
};

let lastClassId = null;
/** 라우트 인자 → 수업. 인자가 없으면 직전에 보던 수업, 그것도 없으면 첫 수업 */
function pickClass(arg, list = db.classes) {
  const cls = list.find(c => c.id === arg) || list.find(c => c.id === lastClassId) || list[0] || null;
  if (cls) lastClassId = cls.id; return cls;
}
const classPath = (page, cls) => cls ? `${page}/${cls.id}` : page;

const ROUTES = {
  student: {
    dashboard: { t: "대시보드", s: () => "2026학년도 2학기", r: renderDashboard, i: "dash", cta: ["매칭 준비 확인", "readiness"] },
    readiness: { t: "매칭 준비", s: () => "프로필과 설문을 채우고 준비 완료로 표시하세요", r: renderReadiness, i: "spark" },
    projects: { t: "프로젝트", s: () => "편성이 확정된 팀 공간", r: renderProjects, i: "folder", badge: () => me().projects.length },
    profile: { t: "내 프로필", s: () => "매칭에 사용되는 정보입니다", r: renderProfile, i: "user" },
    schedule: { t: "일정", s: () => "주간 가능 시간을 표시하세요", r: renderSchedule, i: "cal" }
  },
  ta: {
    "ta-roster": { t: "학생 제출 현황", s: () => "조교 권한 · 열람과 리마인드만 가능합니다", r: (c, a) => renderRoster(c, a, { ta: true }), i: "list" },
    "ta-result": { t: "매칭 결과", s: () => "조교 권한 · 확정 후 열람", r: (c, a) => renderProfResult(c, a, { ta: true }), i: "grid" }
  },
  professor: {
    dashboard: { t: "대시보드", s: () => `2026학년도 2학기 · 수업 ${db.classes.length}개`, r: renderProfDashboard, i: "dash", cta: ["편성 설정으로", "setup"] },
    classes: { t: "내 수업", s: () => "수업을 개설하고 참여 코드를 전달하세요", r: renderClasses, i: "folder", badge: () => db.classes.length },
    roster: { t: "학생 제출 현황", s: () => "설문 제출 상태를 확인하고 독려합니다", r: renderRoster, i: "list", cls: true },
    setup: { t: "편성 설정", s: () => "가중치와 반드시 지킬 조건을 정합니다", r: renderSetup, i: "sliders", cls: true },
    result: { t: "매칭 결과", s: () => "편성 근거를 확인하고 확정합니다", r: renderProfResult, i: "grid", cls: true },
    ta: { t: "조교 관리", s: () => "과목 단위로 조교 권한을 부여합니다", r: renderTA, i: "badge", cls: true },
    profile: { t: "내 프로필", s: () => "계정 정보를 확인하고 수정합니다", r: renderProfProfile, i: "user" }
  }
};
const NAV_ORDER = { student: ["dashboard", "readiness", "projects", "profile", "schedule"], professor: ["dashboard", "classes", "roster", "setup", "result", "ta", "profile"], ta: ["ta-roster", "ta-result"] };

function currentRoute() {
  const [, page = "dashboard", arg = ""] = (location.hash || "").replace(/^#/, "").split("/");
  return { page: page || "dashboard", arg: decodeURIComponent(arg) };
}
function nav(path) {
  const t = "#/" + String(path).replace(/^#?\/?/, "");
  if (location.hash === t) renderRoute(); else location.hash = t;
}

/* ---------- 사이드바 ---------- */
const sidebar = $("#sidebar"), scrim = $("#scrim"), burger = $("#burger"), mq = window.matchMedia("(min-width: 981px)");
function syncSidebarA11y() {
  const open = sidebar.classList.contains("open");
  burger.setAttribute("aria-expanded", String(open));
  if (mq.matches) sidebar.removeAttribute("inert"); else open ? sidebar.removeAttribute("inert") : sidebar.setAttribute("inert", "");
}
function openSidebar() { sidebar.classList.add("open"); scrim.classList.add("show"); syncSidebarA11y(); const first = $(".nav-item", sidebar); first && first.focus(); }
function closeSidebar(returnFocus) { const was = sidebar.classList.contains("open"); sidebar.classList.remove("open"); scrim.classList.remove("show"); syncSidebarA11y(); if (was && returnFocus) burger.focus(); }
burger.onclick = openSidebar; scrim.onclick = () => closeSidebar(true);
document.addEventListener("keydown", e => { if (e.key === "Escape" && sidebar.classList.contains("open")) closeSidebar(true); });
mq.addEventListener("change", () => closeSidebar(false));

function routesFor() { const a = me(); if (!a) return {}; return a.role === "professor" ? ROUTES.professor : { ...ROUTES.student, ...(taClasses(a.email).length ? ROUTES.ta : {}) }; }

function renderNav() {
  const a = me(), box = $("#nav"); box.innerHTML = ""; if (!a) return;
  const groups = a.role === "professor" ? [["수업 운영", "professor"]] : [["내 활동", "student"], ...(taClasses(a.email).length ? [["조교 업무", "ta"]] : [])];
  const cur = currentRoute().page;
  groups.forEach(([label, key]) => {
    box.append(el(`<div class="nav-label">${label}</div>`));
    NAV_ORDER[key].forEach(p => {
      const r = ROUTES[key][p];
      const b = el(`<button type="button" class="nav-item" data-page="${p}"${p === cur ? ' aria-current="page"' : ""}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[r.i]}</svg>
        ${r.t}${r.badge ? `<span class="nav-badge" aria-label="${r.badge()}개">${r.badge()}</span>` : ""}</button>`);
      if (p === cur) b.classList.add("active");
      b.onclick = () => nav(r.cls ? classPath(p, classById(lastClassId) || db.classes[0]) : p);
      box.append(b);
    });
  });
}

/* ---------- 렌더 ---------- */
function renderRoute() {
  const a = me();
  if (!a) { $("#appView").classList.add("hidden"); $("#authView").classList.remove("hidden"); return; }
  $("#authView").classList.add("hidden"); $("#appView").classList.remove("hidden");
  const table = routesFor(), { page, arg } = currentRoute(), route = table[page];
  if (!route) {
    const known = Object.values(ROUTES).some(t => t[page]);
    if (known) toast("이 계정으로는 접근할 수 없는 화면입니다.");
    location.replace("#/dashboard"); return;
  }
  const c = $("#content"); c.innerHTML = "";
  $$(".nav-item[data-page]").forEach(b => { const on = b.dataset.page === page; b.classList.toggle("active", on); on ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"); });
  $("#tbTitle").textContent = route.t; $("#tbSub").textContent = route.s();
  document.title = `${route.t} · TeamMatch AI`;
  const cta = $("#tbCta");
  if (route.cta) { cta.textContent = route.cta[0]; cta.onclick = () => nav(route.cls ? classPath(route.cta[1], classById(lastClassId)) : route.cta[1]); cta.classList.remove("hidden"); if (route.cta[1] === "setup") cta.onclick = () => nav(classPath("setup", classById(lastClassId) || db.classes[0])); }
  else cta.classList.add("hidden");
  closeSidebar(false);
  try { route.r(c, arg); }
  catch (err) {
    console.error(err);
    c.append(el(`<div class="card card-pad"><div class="empty"><b>화면을 불러오지 못했습니다</b>저장된 데모 데이터가 손상됐을 수 있습니다.<br><small>${esc(err.message)}</small></div>
      <div class="center mt-16"><button class="btn" id="errReset">데모 데이터 초기화</button></div></div>`));
    $("#errReset").onclick = resetDemo;
  }
  window.scrollTo({ top: 0 }); c.focus({ preventScroll: true });
}

window.addEventListener("hashchange", renderRoute);
syncSidebarA11y();
if (me()) { syncSideUser(); renderNav(); if (!location.hash || location.hash === "#/") location.replace("#/dashboard"); renderRoute(); }
