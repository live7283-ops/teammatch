/* =================================================================
   auth.js — 로그인 / 회원가입 (프론트엔드 데모)
   · 비밀번호는 검증도 저장도 하지 않는다 (서버가 없으므로 의미 있는 검증이 불가능)
   · 이메일은 계정 레지스트리(db.accounts)에서 찾는다 → 존재하지 않으면 로그인 실패
================================================================= */
let authRole = "student";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const DEMO_ACCOUNTS = [
  { email: "doyoon@hanyang.ac.kr", role: "student", label: "학생 · 김도윤" },
  { email: "sumin.lee@hanyang.ac.kr", role: "student", label: "조교 · 이수민 (학생 탭)" },
  { email: "jiwon.han@hanyang.ac.kr", role: "professor", label: "교수 · 한지원" }
];

function setRole(r) {
  authRole = r; const prof = r === "professor";
  $$("#liRole button, #suRole button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.role === r)));
  $("#liTitle").textContent = prof ? "교수 로그인" : "학생 로그인";
  $("#suTitle").textContent = prof ? "교수 회원가입" : "학생 회원가입";
  $("#liSub").textContent = prof ? "학교 이메일로 로그인하면 수업을 개설하고 팀을 편성할 수 있습니다." : "학교 이메일로 로그인하면 프로필과 설문을 채우고 팀 매칭을 준비할 수 있습니다.";
  $("#suSub").textContent = prof ? "가입 후 수업을 개설하고 참여 코드를 학생에게 전달하세요." : "가입 후 프로필을 채우고 수업 참여 코드를 입력하면 팀 매칭 준비가 시작됩니다.";
  $("#liEmail").placeholder = prof ? "jiwon.han@hanyang.ac.kr" : "doyoon@hanyang.ac.kr";
  $("#suName").placeholder = prof ? "한지원" : "김도윤";
  $("#suEmail").placeholder = prof ? "jiwon.han@hanyang.ac.kr" : "doyoon@hanyang.ac.kr";
  $("#suMajorLabel").textContent = prof ? "소속 학과" : "전공";
  $("#suStudentIdField").classList.toggle("hidden", prof);
  $("#suCodeField").classList.toggle("hidden", prof);
  $("#suSchoolField").classList.toggle("hidden", !prof);
  $("#suRow2").classList.toggle("one", prof);
  $("#liDemo").innerHTML = "<b>데모 안내</b> · 이메일 형식만 맞으면 어떤 주소로든 입장할 수 있고, 처음 쓰는 주소는 데모 계정이 자동으로 만들어집니다. 비밀번호는 검증·저장하지 않으며, 입력한 내용은 <b>이 브라우저에만</b> 저장되고 서버로 전송되지 않습니다.";
  $("#demoChips").innerHTML = "";
  DEMO_ACCOUNTS.filter(a => (a.role === r)).forEach(a => {
    const b = el(`<button type="button" class="chip">${esc(a.label)}</button>`);
    b.onclick = () => { $("#liEmail").value = a.email; $("#liPw").value = "demo1234"; $("#liErr").classList.remove("show"); $("#loginBtn").focus(); };
    $("#demoChips").append(b);
  });
}
$$("#liRole button, #suRole button").forEach(b => b.onclick = () => setRole(b.dataset.role));
const showCard = which => { $("#loginCard").classList.toggle("hidden", which !== "login"); $("#signupCard").classList.toggle("hidden", which !== "signup"); (which === "login" ? $("#liEmail") : $("#suName")).focus(); };
$("#toSignup").onclick = () => showCard("signup");
$("#toLogin").onclick = () => showCard("login");
$$(".pw-toggle").forEach(b => b.onclick = () => {
  const i = $("#" + b.dataset.for), show = i.type === "password"; i.type = show ? "text" : "password";
  b.textContent = show ? "숨김" : "표시"; b.setAttribute("aria-label", show ? "비밀번호 숨김" : "비밀번호 표시");
});
$("#resetDemo").onclick = async () => {
  if (await confirmDialog({ title: "데모 데이터 초기화", message: "이 브라우저에 저장된 모든 데모 데이터(가입한 계정, 프로필, 일정, 편성 결과)를 지우고 처음 상태로 되돌립니다.", okText: "초기화", danger: true })) resetDemo();
};

function showErr(id, msg, input) { const e = $(id); e.textContent = msg; e.classList.add("show"); if (input) input.focus(); }

/* =================================================================
   백엔드 연결 지점 ★
   서버가 생기면 이 객체의 두 함수만 fetch 호출로 교체하면 된다. (submit 핸들러에는 await만 추가)
   반환 형태는 유지: { ok:true, email, ... } | { ok:false, field?, message }
   지금은 서버가 없으므로 "일시적 데모 구현"이다 — 인증·중복 검사·이메일 소유 확인은 서버의 몫이다.
================================================================= */
const AuthApi = {
  /** 데모: 이메일 형식만 맞으면 입장. 처음 쓰는 이메일이면 해당 역할의 데모 계정을 자동 생성한다.
      역할은 (기존 계정이면) 계정이 정한다 — 탭 선택은 새 계정을 만들 때만 쓰인다. */
  login({ email, role }) {
    if (acct(email)) return { ok: true, email, created: false };
    const name = email.split("@")[0];
    db.accounts[email] = role === "professor" ? { role, name, email, dept: "", school: "" }
      : blankStudent({ name, email, major: "", studentId: "" });
    save(); return { ok: true, email, created: true };
  },
  /** 데모: 이미 있는 이메일이면 덮어쓰지 않고 로그인으로 안내. 참여 코드는 데모 수업 목록에서 조회. */
  signup(v) {
    if (acct(v.email)) return { ok: true, email: v.email, existed: true };
    let joinCls = null;
    if (v.role === "student" && v.code) {
      joinCls = db.classes.find(c => c.join === v.code);
      if (!joinCls) return { ok: false, field: "suCode", message: "유효하지 않은 참여 코드입니다. 코드를 다시 확인하세요." };
    }
    if (v.role === "professor") db.accounts[v.email] = { role: "professor", name: v.name, email: v.email, dept: v.major, school: v.school };
    else { db.accounts[v.email] = blankStudent({ name: v.name, email: v.email, major: v.major, studentId: v.sid }); if (joinCls) joinClass(db.accounts[v.email], joinCls); }
    save(); return { ok: true, email: v.email, joinCls };
  },
  /** 데모: 계정과 개인정보를 삭제하고 남은 기록은 익명화한다. 서버에서는 보존 기간·이관 정책에 따라 처리. */
  withdraw({ email }) {
    if (!acct(email)) return { ok: false, message: "이미 탈퇴했거나 존재하지 않는 계정입니다." };
    purgeAccount(email); flushSave(); return { ok: true };
  }
};

/** 학생·교수 프로필 하단의 '계정 관리' 카드 (회원 탈퇴) */
function withdrawCard(a) {
  const prof = a.role === "professor";
  const card = el(`<div class="card card-pad danger-zone"><div class="card-head"><div><h3 class="card-title">계정 관리</h3><p class="card-sub">회원 탈퇴는 되돌릴 수 없습니다</p></div></div>
    <ul class="bullets">${prof
      ? "<li><b>삭제:</b> 계정 정보(이름·이메일·학교·소속 학과)</li><li><b>유지:</b> 개설한 수업 데이터는 삭제되지 않고 남습니다 (데모에서는 수업 데이터를 모든 교수 계정이 공유합니다)</li>"
      : "<li><b>삭제:</b> 프로필·기술·성향·가능 시간, 준비 완료 표시, 팀 공간(체크리스트·역할 분배·협업 규범 응답)</li><li><b>익명화:</b> 수업 명단과 이미 만들어진 편성 결과에는 이름 대신 ‘탈퇴한 학생’으로 남습니다</li>"}</ul>
    <button class="btn btn-danger-outline" id="wd" type="button">회원 탈퇴</button></div>`);
  $("#wd", card).onclick = async () => {
    if (!await confirmDialog({ title: "정말 탈퇴하시겠습니까?", message: `${a.name} (${a.email}) 계정을 삭제합니다.\n삭제된 계정과 데이터는 복구할 수 없습니다.`, okText: "회원 탈퇴", danger: true, requireText: "탈퇴" })) return;
    const r = AuthApi.withdraw({ email: a.email });
    if (!r.ok) return toast(r.message || "탈퇴하지 못했습니다.");
    setSession(null); closeSidebar(false); $("#appView").classList.add("hidden"); $("#authView").classList.remove("hidden");
    location.hash = ""; showCard("login"); toast("회원 탈퇴가 완료되었습니다. 이용해 주셔서 감사합니다.");
  };
  return card;
}

/* ---------- 로그인 (입력 형식 검증은 UX용으로 프론트에 남긴다) ---------- */
$("#loginCard").addEventListener("submit", ev => {
  ev.preventDefault();
  const emI = $("#liEmail"), pwI = $("#liPw"), em = emI.value.trim().toLowerCase();
  $("#liErr").classList.remove("show"); clearAllErr($("#loginCard"));
  if (!em) { setErr(emI, "이메일을 입력하세요."); emI.focus(); return; }
  if (!EMAIL_RE.test(em)) { setErr(emI, "이메일 형식이 올바르지 않습니다."); emI.focus(); return; }
  if (!pwI.value) { setErr(pwI, "비밀번호를 입력하세요."); pwI.focus(); return; }
  const r = AuthApi.login({ email: em, role: authRole });
  if (!r.ok) { showErr("#liErr", r.message, emI); return; }
  setSession(r.email); pwI.value = "";
  const a = acct(r.email);
  enterApp(`${a.name}${a.role === "professor" ? " 교수님" : "님"}, ${r.created ? "데모 계정을 만들어 " : ""}로그인했습니다.`);
});

/* ---------- 회원가입 ---------- */
$("#signupCard").addEventListener("submit", ev => {
  ev.preventDefault();
  const prof = authRole === "professor", f = id => $("#" + id);
  const v = { role: authRole, name: f("suName").value.trim(), email: f("suEmail").value.trim().toLowerCase(), pw: f("suPw").value, pw2: f("suPw2").value,
    major: f("suMajor").value.trim(), sid: f("suStudentId").value.trim(), school: f("suSchool").value.trim(), code: f("suCode").value.trim().toUpperCase() };
  $("#suErr").classList.remove("show"); clearAllErr($("#signupCard"));
  const bad = (id, msg) => { setErr(f(id), msg); f(id).focus(); return true; };
  if (!v.name) return bad("suName", "이름을 입력하세요.");
  if (!EMAIL_RE.test(v.email)) return bad("suEmail", "이메일 형식이 올바르지 않습니다.");
  if (v.pw.length < 8) return bad("suPw", "비밀번호는 8자 이상이어야 합니다.");
  if (v.pw !== v.pw2) return bad("suPw2", "비밀번호가 일치하지 않습니다.");
  if (!v.major) return bad("suMajor", prof ? "소속 학과를 입력하세요." : "전공을 입력하세요.");
  if (prof && !v.school) return bad("suSchool", "학교를 입력하세요.");
  if (!prof && !/^\d{8,10}$/.test(v.sid)) return bad("suStudentId", "학번은 숫자 8~10자리로 입력하세요.");
  if (!f("suTerms").checked) { showErr("#suErr", "이용약관 및 개인정보 처리방침에 동의해야 가입할 수 있습니다.", f("suTerms")); return; }
  const r = AuthApi.signup(v);
  if (!r.ok) return bad(r.field, r.message);
  $("#signupCard").reset(); showCard("login"); $("#liEmail").value = v.email; $("#liPw").value = ""; $("#liPw").focus();
  toast(r.existed ? "이미 있는 계정입니다. 로그인해 주세요." : `가입이 완료되었습니다. 로그인해 주세요.${r.joinCls ? ` (${r.joinCls.name} 참여)` : ""}`);
});

/** 학생이 수업에 합류: roster에 연결 행을 추가한다 */
function joinClass(a, cls) {
  if (!a.joined.includes(cls.id)) a.joined.push(cls.id);
  if (!cls.roster.some(r => r.email === a.email)) cls.roster.push({ id: "a:" + a.email, email: a.email, reminders: 0 });
}

/* ---------- 앱 진입/로그아웃 ---------- */
function enterApp(msg) {
  $("#authView").classList.add("hidden"); $("#appView").classList.remove("hidden");
  renderNav(); syncSideUser();
  if (!location.hash || location.hash === "#/") location.hash = "#/dashboard"; else renderRoute();
  if (msg) toast(msg);
}
$("#logoutBtn").onclick = () => {
  setSession(null); closeSidebar();
  $("#appView").classList.add("hidden"); $("#authView").classList.remove("hidden");
  location.hash = ""; showCard("login"); toast("로그아웃했습니다.");
};

function syncSideUser() {
  const a = me(); if (!a) return;
  const prof = a.role === "professor", ta = !prof && taClasses(a.email).length;
  $("#sideName").textContent = prof ? a.name + " 교수" : a.name;
  $("#sideMajor").textContent = prof ? (a.dept || "") : [a.major, a.year, ta ? "조교" : ""].filter(Boolean).join(" · ");
  $("#sideAvatar").textContent = initial(a.name);
}

/* ---------- 저장 상태 표시 (상단바) ---------- */
let _ssT;
function markSaved() {
  save(); const s = $("#saveStatus"); if (!s) return;
  s.textContent = "자동 저장됨"; s.classList.add("show"); clearTimeout(_ssT); _ssT = setTimeout(() => s.classList.remove("show"), 1800);
}

setRole("student");
