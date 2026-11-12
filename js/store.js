/* =================================================================
   store.js — 상태 모델 · 시드 데이터 · 저장/복원 · 셀렉터
   원본과의 차이
   · 수업(class)마다 setup / roster / result / tas 를 따로 가진다 (원본은 전역 1개를 공유)
   · 계정 레지스트리(accounts): 가입/로그인이 실제로 계정을 구분한다
   · 제출 수·팀 수 등 모든 수치는 roster에서 계산한다 (하드코딩 제거)
   · 모든 변경은 save()로 저장된다 (디바운스 + pagehide 시 flush)
================================================================= */
const { DAYS, BLOCKS, ROLES, DEV_ROLES, ALL_SLOTS, slotKey, mulberry32 } = TM;

const DB_VERSION = 2;
const DB_KEY = "teammatch-demo-v2";
const SESSION_KEY = "teammatch-session-v2";
const DAY_MS = 864e5;

let db = null;
let session = null; // { email }

/* ---------- 저장 ---------- */
let _saveTimer = null;
function flushSave() {
  clearTimeout(_saveTimer);
  try { localStorage.setItem(DB_KEY, JSON.stringify(db)); return true; }
  catch (err) { console.warn("저장 실패", err); if (typeof toast === "function") toast("브라우저 저장 공간에 저장하지 못했습니다. (시크릿 모드이거나 용량 부족)"); return false; }
}
function save() { clearTimeout(_saveTimer); _saveTimer = setTimeout(flushSave, 120); }
window.addEventListener("pagehide", flushSave);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flushSave(); });

function validDb(d) {
  return !!(d && d.v === DB_VERSION && d.accounts && typeof d.accounts === "object" && Array.isArray(d.classes) && Array.isArray(d.presets)
    && d.classes.every(c => c && c.setup && Array.isArray(c.roster) && Array.isArray(c.tas))
    && Object.values(d.accounts).every(a => a && (a.role === "student" || a.role === "professor")));
}
function resetDemo() {
  try { localStorage.removeItem(DB_KEY); localStorage.removeItem("teammatch-demo-v1"); sessionStorage.removeItem(SESSION_KEY); } catch (e) { /* ignore */ }
  location.hash = ""; location.reload();
}
function loadSession() { try { const s = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null"); return s && db.accounts[s.email] ? s : null; } catch (e) { return null; } }
function setSession(email) { session = email ? { email } : null; try { email ? sessionStorage.setItem(SESSION_KEY, JSON.stringify(session)) : sessionStorage.removeItem(SESSION_KEY); } catch (e) { /* ignore */ } }

/* ---------- 기본값 ---------- */
const NOTE_SAMPLE = "발표 경험이 있는 학생과 개발 경험이 있는 학생을 각 팀에 최소 1명씩 포함해 주세요. 4학년은 한 팀에 몰리지 않게 해주세요.";
function defaultSetup(note = "") {
  return { size: 4, rest: "extra", miss: "default", weights: { major: 3, role: 3, time: 3, trait: 3 },
    hard: { sameMajor: true, fixPair: false, splitPair: false, evenTransfer: false },
    pairs: [], note, parsedOff: {}, presetId: "ps0", seed: 0 };
}
const PRESETS = [
  { id: "ps0", name: "균형 배분", desc: "네 항목을 고르게 반영하는 기본값", own: false, size: 4, rest: "extra", weights: { major: 3, role: 3, time: 3, trait: 3 }, hard: { sameMajor: true, fixPair: false, splitPair: false, evenTransfer: false } },
  { id: "ps1", name: "전공 다양성 우선", desc: "융합 프로젝트처럼 학과가 섞여야 하는 수업", own: false, size: 4, rest: "extra", weights: { major: 5, role: 4, time: 2, trait: 2 }, hard: { sameMajor: true, fixPair: false, splitPair: false, evenTransfer: true } },
  { id: "ps2", name: "역량 균형 우선", desc: "개발·기획 역할이 팀마다 고루 필요한 수업", own: false, size: 4, rest: "extra", weights: { major: 3, role: 5, time: 3, trait: 2 }, hard: { sameMajor: false, fixPair: false, splitPair: false, evenTransfer: false } },
  { id: "ps3", name: "일정 우선", desc: "모일 시간을 맞추기 어려운 야간·대형 수업", own: false, size: 5, rest: "extra", weights: { major: 2, role: 3, time: 5, trait: 2 }, hard: { sameMajor: false, fixPair: false, splitPair: false, evenTransfer: false } },
  { id: "ps4", name: "성향 중심", desc: "한 학기 내내 함께 가는 장기 프로젝트", own: false, size: 4, rest: "extra", weights: { major: 2, role: 3, time: 3, trait: 5 }, hard: { sameMajor: true, fixPair: false, splitPair: false, evenTransfer: false } }
];
const blankStudent = ({ name, email, major, studentId }) => ({
  role: "student", name, email, major, studentId, year: "", bio: "", roles: [], skills: [],
  traits: { pace: 3, prep: 3, lead: 3, comm: 3 }, traitsSet: false, schedule: {}, joined: [], ready: {}, readyAt: {}, projects: []
});

/* ---------- 모의 학생 생성 (시드 고정) ---------- */
const MOCK_NAMES = ["이민준", "박지수", "최준서", "정서연", "한소희", "오지훈", "윤채원", "송지원", "백준혁", "강다은", "임도현", "서민재", "노하린", "장우진", "문가영",
  "김서준", "이하윤", "박시우", "최예린", "정우성", "한지민", "윤서진", "조민석", "신아름", "배준호", "홍가온", "권나연", "황태현", "안유진", "류현서",
  "남도윤", "심채은", "고은비", "표지훈", "하연우", "손예슬", "진하람", "차은우", "구민서", "조하늘", "방시현", "엄정후", "우지안", "선우재"];
const MOCK_MAJORS = ["SW융합", "경영학", "컴퓨터공학", "시각디자인", "전기전자공학", "수리데이터사이언스", "AI소프트웨어", "미디어커뮤니케이션"];
const MAJOR_ROLES = { "SW융합": ["프론트엔드", "백엔드", "기획"], "경영학": ["기획", "발표"], "컴퓨터공학": ["백엔드", "프론트엔드", "데이터"], "시각디자인": ["디자인", "발표", "기획"],
  "전기전자공학": ["백엔드", "데이터", "프론트엔드"], "수리데이터사이언스": ["데이터", "백엔드", "기획"], "AI소프트웨어": ["데이터", "백엔드", "프론트엔드"], "미디어커뮤니케이션": ["발표", "기획", "디자인"] };
const ROLE_SKILLS = { "기획": ["Notion", "Excel", "Figma"], "프론트엔드": ["React", "TypeScript", "Vue"], "백엔드": ["Java", "Node", "SQL"], "데이터": ["Python", "SQL", "Pandas"], "디자인": ["Figma", "Illustrator"], "발표": ["Keynote", "Premiere"] };

function makeMock(i, rng) {
  const m = MOCK_MAJORS[Math.floor(rng() * MOCK_MAJORS.length)];
  const y = [1, 2, 2, 2, 3, 3, 3, 4, 4][Math.floor(rng() * 9)];
  const pool = MAJOR_ROLES[m].concat(ROLES), roles = [];
  while (roles.length < 2) { const r = rng() < 0.7 ? MAJOR_ROLES[m][Math.floor(rng() * MAJOR_ROLES[m].length)] : pool[Math.floor(rng() * pool.length)]; if (!roles.includes(r)) roles.push(r); }
  if (!roles.includes("발표") && rng() < 0.16) roles[1] = "발표"; // 발표 희망자가 지나치게 적지 않도록 (현실적 분포)
  const skills = [...new Set(roles.flatMap(r => ROLE_SKILLS[r].filter(() => rng() < 0.6)))].slice(0, 4);
  const slots = ALL_SLOTS.filter(k => {
    const [d, h] = k.split("-"), weekend = d === "토" || d === "일", p = weekend ? 0.25 : (Number(h) >= 9 ? 0.5 : Number(h) >= 3 ? 0.72 : 0.5);
    return rng() < p;
  });
  return { id: "m" + i, sid: String(2027 - y) + String(100000 + Math.floor(rng() * 899999)), n: MOCK_NAMES[i], m, y, roles, skills,
    traits: { pace: 1 + Math.floor(rng() * 5), prep: 1 + Math.floor(rng() * 5), lead: 1 + Math.floor(rng() * 5), comm: 1 + Math.floor(rng() * 5) },
    sched: slots, transfer: rng() < 0.09 };
}

function buildSeed() {
  const rng = mulberry32(20260916), now = Date.now();
  const mocks = MOCK_NAMES.map((_, i) => makeMock(i, rng));
  const dl = n => { const d = new Date(now + n * DAY_MS); d.setHours(23, 59, 0, 0); return d.toISOString(); };
  const rowsFrom = (list, dueISO, unsubmittedIdx) => list.map((s, k) => {
    const submitted = !unsubmittedIdx.includes(k);
    const upper = Math.min(now, new Date(dueISO).getTime());
    return { ...s, at: submitted ? new Date(upper - (0.2 + rng() * 9) * DAY_MS).toISOString() : null, reminders: submitted ? 0 : (k % 3 === 0 ? 1 : 0) };
  });
  const yes = ["월-5", "월-6", "화-1", "화-5", "화-6", "화-7", "수-6", "수-7", "목-0", "목-5", "금-6", "토-5", "토-6"];
  const no = ["월-0", "수-0", "금-0", "금-9"].concat(Array.from({ length: 12 }, (_, i) => "일-" + i));
  const schedMap = {}; yes.forEach(k => schedMap[k] = "y"); no.forEach(k => schedMap[k] = "n");
  const accounts = {
    "doyoon@hanyang.ac.kr": { ...blankStudent({ name: "김도윤", email: "doyoon@hanyang.ac.kr", major: "데이터사이언스학과", studentId: "2022123456" }),
      year: "3학년", bio: "프론트엔드 개발에 관심이 많고, React로 사이드 프로젝트를 두 번 진행했습니다. 팀에서는 일정 관리도 함께 맡아본 적이 있습니다.",
      roles: ["프론트엔드", "기획"], skills: [{ n: "React", l: 4 }, { n: "Python", l: 3 }, { n: "Figma", l: 2 }, { n: "Git", l: 3 }],
      traits: { pace: 3, prep: 2, lead: 4, comm: 3 }, traitsSet: true, schedule: schedMap, joined: ["c1", "c2"], ready: { c1: false } },
    "sumin.lee@hanyang.ac.kr": { ...blankStudent({ name: "이수민", email: "sumin.lee@hanyang.ac.kr", major: "데이터사이언스학과", studentId: "2025123456" }),
      year: "대학원", roles: ["데이터"], skills: [{ n: "Python", l: 4 }, { n: "SQL", l: 3 }, { n: "Pandas", l: 3 }], traitsSet: true },
    "jiwon.han@hanyang.ac.kr": { role: "professor", name: "한지원", email: "jiwon.han@hanyang.ac.kr", dept: "데이터사이언스학과", school: "한양대학교 ERICA" }
  };
  const c1due = dl(4), c2due = dl(-14), c3due = dl(10);
  const mk = (id, name, code, cap, join, due, kind, roster, note, tas) => ({ id, name, code, term: "2026학년도 2학기", cap, join, deadline: due, kind, createdAt: new Date(now - 30 * DAY_MS).toISOString(),
    setup: defaultSetup(note), roster, result: null, tas: tas || [] });
  const classes = [
    mk("c1", "DS창업캡스톤디자인1", "MAT2082", 45, "A7X9K2", c1due, "개발 프로젝트",
      rowsFrom(mocks.slice(0, 44), c1due, [1, 6, 11, 16, 22, 30, 38]).concat([{ id: "a:doyoon@hanyang.ac.kr", email: "doyoon@hanyang.ac.kr", reminders: 0 }]), NOTE_SAMPLE,
      [{ email: "sumin.lee@hanyang.ac.kr", date: new Date(now - 15 * DAY_MS).toISOString() }]),
    mk("c2", "데이터마이닝", "ITE3082", 32, "K2M4P8", c2due, "학술 세미나",
      rowsFrom(mocks.slice(4, 35), c2due, []).concat([{ id: "a:doyoon@hanyang.ac.kr", email: "doyoon@hanyang.ac.kr", reminders: 0 }]), ""),
    mk("c3", "머신러닝개론", "ITE2013", 41, "Q9F1V5", c3due, "개발 프로젝트",
      rowsFrom(mocks.slice(2, 42), c3due, Array.from({ length: 28 }, (_, i) => i + 12)), "")
  ];
  accounts["doyoon@hanyang.ac.kr"].readyAt = {};
  return { v: DB_VERSION, accounts, classes, presets: PRESETS.map(p => ({ ...p, weights: { ...p.weights }, hard: { ...p.hard } })), seq: 100 };
}

/* ---------- 셀렉터 ---------- */
const majorKey = m => String(m || "").replace(/학과$/, "");
const yearNum = y => { const n = parseInt(y, 10); return Number.isFinite(n) ? n : (String(y).includes("대학원") ? 5 : 0); };
const acct = email => db.accounts[email];
const me = () => session && db.accounts[session.email];
const classById = id => db.classes.find(c => c.id === id);
const sched = a => Object.keys(a.schedule || {}).filter(k => a.schedule[k] === "y");
const nextId = p => p + (++db.seq);

function resolveRow(cls, row) {
  if (row.email) {
    const a = acct(row.email); if (!a) return null;
    const ready = !!(a.ready && a.ready[cls.id]);
    return { id: row.id, sid: a.studentId || "학번 미입력", n: a.name, m: majorKey(a.major) || "전공 미입력", major: a.major || "전공 미입력", y: yearNum(a.year), yearLabel: a.year || "학년 미입력",
      roles: a.roles.slice(), skills: a.skills.map(s => s.n), traits: a.traits, sched: sched(a), submitted: ready,
      at: ready ? (a.readyAt && a.readyAt[cls.id]) || null : null, transfer: false, email: row.email, reminders: row.reminders || 0, linked: true };
  }
  return { id: row.id, sid: row.sid, n: row.n, m: row.m, major: row.m + "학과", y: row.y, yearLabel: row.y + "학년", roles: row.roles, skills: row.skills,
    traits: row.traits, sched: row.sched, submitted: !!row.at, at: row.at, transfer: !!row.transfer, reminders: row.reminders || 0 };
}
const participantsOf = cls => cls.roster.map(r => resolveRow(cls, r)).filter(Boolean);
function rosterStats(cls) {
  const p = participantsOf(cls), done = p.filter(x => x.submitted).length;
  return { total: p.length, done, pending: p.length - done, pct: p.length ? Math.round(done / p.length * 100) : 0 };
}
function classStatus(cls) {
  if (cls.result && cls.result.confirmedAt) return { label: "편성 완료", tone: "tag-mint", key: "done" };
  if (cls.result) return { label: "결과 검토 중", tone: "tag-amber", key: "review" };
  const s = rosterStats(cls);
  if (Date.now() > new Date(cls.deadline).getTime() || (s.total && s.pending === 0)) return { label: "편성 대기", tone: "tag-amber", key: "ready" };
  return { label: "설문 진행 중", tone: "tag-grey", key: "collecting" };
}

/* 학생 프로필 진행도: 필수 5 + 권장 1 */
function profileTodos(a) {
  const y = sched(a).length;
  return [
    { t: "기본 정보 입력 (이름·전공·학번·학년)", ok: !!(a.name && a.major && a.studentId && a.year), req: true, go: "profile" },
    { t: "선호 역할 선택 (1~2순위)", ok: a.roles.length > 0, req: true, go: "profile" },
    { t: "보유 기술 1개 이상 등록", ok: a.skills.length > 0, req: true, go: "profile" },
    { t: "협업 성향 응답", ok: !!a.traitsSet, req: true, go: "profile" },
    { t: "가능한 시간 5시간 이상 표시", ok: y >= 5, req: true, go: "schedule" },
    { t: "자기소개 30자 이상 (권장)", ok: (a.bio || "").length >= 30, req: false, go: "profile" }
  ];
}
const profileScore = a => { const t = profileTodos(a); return Math.round(t.filter(x => x.ok).length / t.length * 100); };
const requiredMissing = a => profileTodos(a).filter(t => t.req && !t.ok);

const taClasses = email => db.classes.filter(c => c.tas.some(t => t.email === email));

/* ---------- 확정 → 학생 프로젝트 생성/회수 ---------- */
function memberSnapshot(m) { return { id: m.id, sid: m.sid, n: m.n, m: m.m, y: m.y, yearLabel: m.yearLabel, roles: m.roles, skills: m.skills, traits: m.traits, sched: m.sched, transfer: !!m.transfer, email: m.email || null, submitted: m.submitted }; }
function publishProjects(cls) {
  const res = cls.result; if (!res) return 0; let created = 0;
  res.teams.forEach(t => t.members.forEach(m => {
    if (!m.email || !acct(m.email)) return;
    const a = acct(m.email), pid = `${cls.id}-t${t.no}`;
    a.projects = a.projects.filter(p => p.id !== pid);
    a.projects.unshift({ id: pid, classId: cls.id, name: `${cls.name} · ${t.no}팀`, course: cls.name, team: t.members.map(memberSnapshot),
      agenda: [false, false, false, false], roleMap: {}, norms: {}, links: { notion: "", github: "" }, createdAt: new Date().toISOString() });
    created++;
  }));
  return created;
}
function withdrawProjects(cls) { Object.values(db.accounts).forEach(a => { if (a.projects) a.projects = a.projects.filter(p => p.classId !== cls.id); }); }

/* ---------- 회원 탈퇴 (데모 구현: 서버에서는 보존·삭제 정책에 따라 처리) ---------- */
function purgeAccount(email) {
  // 이미 만들어진 팀/프로젝트 스냅샷에는 이름 대신 '탈퇴한 학생'만 남긴다 (팀 크기·이력 보존, 개인정보 제거)
  const ghost = m => { if (m.email === email) Object.assign(m, { n: "탈퇴한 학생", sid: "—", m: "—", yearLabel: "", roles: [], skills: [], sched: [], traits: {}, email: null, submitted: false, withdrawn: true }); };
  db.classes.forEach(c => {
    c.roster = c.roster.filter(r => r.email !== email);
    c.tas = c.tas.filter(t => t.email !== email);
    ((c.result && c.result.teams) || []).forEach(t => t.members.forEach(ghost));
  });
  Object.values(db.accounts).forEach(a => (a.projects || []).forEach(p => p.team.forEach(ghost)));
  delete db.accounts[email];
}

/* ---------- 초기화 ---------- */
function initStore() {
  let d = null;
  try { const raw = localStorage.getItem(DB_KEY); if (raw) d = JSON.parse(raw); } catch (e) { d = null; }
  if (validDb(d)) { db = d; }
  else {
    db = buildSeed();
    // 데이터마이닝(c2)은 이미 편성이 확정된 수업으로 시작 → 학생의 기존 프로젝트가 실제 결과에서 만들어진다.
    const c2 = db.classes[1], res = TM.solve(participantsOf(c2).map(p => ({ ...p })), c2.setup, { seed: 3 });
    c2.result = { seed: 3, createdAt: new Date(Date.now() - 12 * DAY_MS).toISOString(), confirmedAt: new Date(Date.now() - 11 * DAY_MS).toISOString(),
      teams: res.teams.map(t => ({ no: t.no, locked: false, members: t.members.map(memberSnapshot) })), settings: JSON.parse(JSON.stringify(c2.setup)) };
    publishProjects(c2);
    const dy = acct("doyoon@hanyang.ac.kr").projects[0]; if (dy) { dy.agenda = [true, true, true, false]; dy.name = "교내 식단 추천 서비스"; }
    flushSave();
  }
  session = loadSession();
}
initStore();
