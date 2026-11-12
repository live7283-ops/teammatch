/* =================================================================
   logic.js — DOM에 의존하지 않는 순수 로직 (Node에서 테스트 가능)
   · 편성 알고리즘: 그리디 초기 배정 + 2-교환 지역 탐색 (시드 고정 난수, 다중 재시작)
   · 점수/제약 검증/팀 수 계획/요구사항 키워드 해석
   ※ "AI"가 아니라 데모용 휴리스틱입니다. 실제 서비스에서는 서버/LLM으로 대체됩니다.
================================================================= */
(function (root) {
  const DAYS = ["월", "화", "수", "목", "금", "토", "일"];
  const BLOCKS = [
    ["09–10", "오전"], ["10–11", "오전"], ["11–12", "오전"], ["12–13", "점심"],
    ["13–14", "오후"], ["14–15", "오후"], ["15–16", "오후"], ["16–17", "오후"], ["17–18", "오후"],
    ["18–19", "저녁"], ["19–20", "저녁"], ["20–21", "저녁"]
  ];
  const ROLES = ["기획", "프론트엔드", "백엔드", "데이터", "디자인", "발표"];
  const DEV_ROLES = ["프론트엔드", "백엔드"];
  const slotKey = (d, i) => d + "-" + i;
  const ALL_SLOTS = DAYS.flatMap(d => BLOCKS.map((_, i) => slotKey(d, i)));

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0;
  const std = a => { const m = mean(a); return Math.sqrt(mean(a.map(x => (x - m) ** 2))); };

  /* ---------- 가중치: 1 = 고려하지 않음(0), 5 = 매우 중요(4) ---------- */
  function effectiveWeights(W) {
    const e = {
      major: Math.max(0, (W.major || 1) - 1), role: Math.max(0, (W.role || 1) - 1),
      time: Math.max(0, (W.time || 1) - 1), trait: Math.max(0, (W.trait || 1) - 1)
    };
    const s = e.major + e.role + e.time + e.trait;
    if (s === 0) return { major: 1, role: 1, time: 1, trait: 1, equal: true, sum: 4 };
    return { ...e, equal: false, sum: s };
  }

  /* ---------- 팀 수 계획 (미리보기와 실제 편성이 같은 함수를 쓴다) ---------- */
  function planTeamCount(n, size, rest) {
    if (n <= 0) return { teams: 0, sizes: [] };
    size = Math.max(2, Number(size) || 4);
    let teams = rest === "fewer" ? Math.ceil(n / size) : Math.max(1, Math.floor(n / size));
    teams = Math.min(teams, n);
    const base = Math.floor(n / teams), extra = n % teams;
    return { teams, sizes: Array.from({ length: teams }, (_, i) => base + (i < extra ? 1 : 0)) };
  }
  function describePlan(plan) {
    const c = {}; plan.sizes.forEach(s => c[s] = (c[s] || 0) + 1);
    return Object.keys(c).sort((a, b) => b - a).map(s => `${s}명 팀 ${c[s]}개`).join(" · ");
  }

  /* ---------- 요구사항 키워드 해석 (데모용, LLM 아님) ---------- */
  function parseNote(text) {
    const t = String(text || ""), out = [];
    if (/발표/.test(t)) out.push({ id: "present", kind: "hard", text: "각 팀에 ‘발표’ 역할 희망자 1명 이상", role: "발표" });
    if (/개발|코딩|구현/.test(t)) out.push({ id: "dev", kind: "hard", text: "각 팀에 개발(프론트엔드·백엔드) 역할 희망자 1명 이상" });
    if (/디자인|UI|UX/.test(t)) out.push({ id: "design", kind: "hard", text: "각 팀에 ‘디자인’ 역할 희망자 1명 이상", role: "디자인" });
    const ys = new Set(); let m; const re = /([1-4])\s*학년[^.。\n]*?(몰리|분산|최대|이하|고르게)/g;
    while ((m = re.exec(t))) ys.add(Number(m[1]));
    [...ys].sort().forEach(y => out.push({ id: "year" + y, kind: "soft", text: `${y}학년은 팀당 최대 2명`, year: y }));
    return out;
  }

  /* ---------- 팀 지표/점수 ---------- */
  const setCache = new WeakMap();
  const setOf = arr => { let s = setCache.get(arr); if (!s) { s = new Set(arr); setCache.set(arr, s); } return s; };
  function intersect(lists) {
    if (!lists.length) return [];
    const sets = lists.map(setOf).sort((a, b) => a.size - b.size);
    return [...sets[0]].filter(x => sets.every(s => s.has(x)));
  }
  function teamMetrics(members, W) {
    const subs = members.filter(m => m.submitted);
    const majors = new Set(members.map(m => m.m)).size;
    const rolesCovered = new Set(subs.flatMap(m => m.roles)).size;
    const overlapSlots = subs.length ? intersect(subs.map(m => m.sched || [])) : [];
    let traitPct = 70;
    if (subs.length >= 2) {
      const ds = [];
      for (let i = 0; i < subs.length; i++) for (let j = i + 1; j < subs.length; j++) {
        let d = 0; for (const k of ["pace", "prep", "lead", "comm"]) d += Math.abs((subs[i].traits?.[k] ?? 3) - (subs[j].traits?.[k] ?? 3));
        ds.push(1 - d / 16);
      }
      traitPct = Math.round(mean(ds) * 100);
    }
    const parts = {
      major: members.length ? (majors / members.length) * 100 : 0,
      role: Math.min(1, rolesCovered / 6) * 100,
      time: Math.min(1, overlapSlots.length / 8) * 100,
      trait: traitPct
    };
    const ew = effectiveWeights(W);
    const score = Math.round((parts.major * ew.major + parts.role * ew.role + parts.time * ew.time + parts.trait * ew.trait) / ew.sum);
    return { majors, rolesCovered, overlapSlots, overlap: overlapSlots.length, traitPct, parts, score, size: members.length, unsubmitted: members.length - subs.length };
  }

  /* ---------- 제약 검증 (결과는 항상 현재 팀 구성에서 재계산) ---------- */
  function activeConditions(setup) {
    const off = setup.parsedOff || {};
    return parseNote(setup.note).filter(c => !off[c.id]);
  }
  function teamIssues(members, setup, conds) {
    const issues = [];
    const subs = members.filter(m => m.submitted);
    if (setup.hard?.sameMajor) {
      const cnt = {}; members.forEach(m => cnt[m.m] = (cnt[m.m] || 0) + 1);
      Object.entries(cnt).filter(([, n]) => n > 2).forEach(([m, n]) => issues.push({ level: "error", text: `${m} ${n}명 (최대 2명)` }));
    }
    for (const c of conds) {
      if (c.id === "present" || c.id === "design") {
        if (!subs.some(m => m.roles.includes(c.role))) issues.push({ level: "error", text: `‘${c.role}’ 희망자 없음` });
      } else if (c.id === "dev") {
        if (!subs.some(m => m.roles.some(r => DEV_ROLES.includes(r)))) issues.push({ level: "error", text: "개발 역할 희망자 없음" });
      } else if (c.year) {
        const n = members.filter(m => Number(m.y) === c.year).length;
        if (n > 2) issues.push({ level: "warn", text: `${c.year}학년 ${n}명 (권장 최대 2명)` });
      }
    }
    return issues;
  }
  function globalIssues(teams, setup) {
    const issues = [], where = {};
    teams.forEach(t => t.members.forEach(m => where[m.id] = t.no));
    const nameOf = id => { for (const t of teams) for (const m of t.members) if (m.id === id) return m.n; return id; };
    (setup.pairs || []).forEach(p => {
      if (where[p.a] == null || where[p.b] == null) return;
      const same = where[p.a] === where[p.b];
      if (p.type === "fix" && !same) issues.push({ level: "error", text: `같은 팀 고정 위반: ${nameOf(p.a)} · ${nameOf(p.b)} (팀 ${where[p.a]} / 팀 ${where[p.b]})` });
      if (p.type === "split" && same) issues.push({ level: "error", text: `분리 배정 위반: ${nameOf(p.a)} · ${nameOf(p.b)} (모두 팀 ${where[p.a]})` });
    });
    if (setup.hard?.evenTransfer && teams.length > 1) {
      const c = teams.map(t => t.members.filter(m => m.transfer).length);
      if (Math.max(...c) - Math.min(...c) > 1) issues.push({ level: "error", text: `편입·유학생 분포 편차 ${Math.max(...c) - Math.min(...c)}명 (허용 1명)` });
    }
    return issues;
  }
  function evaluate(teams, setup) {
    const conds = activeConditions(setup);
    const per = teams.map(t => ({ no: t.no, metrics: teamMetrics(t.members, setup.weights), issues: teamIssues(t.members, setup, conds) }));
    const glob = globalIssues(teams, setup);
    const all = [...per.flatMap(p => p.issues.map(i => ({ ...i, team: p.no }))), ...glob];
    const scores = per.map(p => p.metrics.score);
    return {
      per, global: glob, issues: all,
      errors: all.filter(i => i.level === "error").length, warns: all.filter(i => i.level === "warn").length,
      avg: scores.length ? Math.round(mean(scores)) : 0, min: scores.length ? Math.min(...scores) : 0
    };
  }

  /* ---------- 편성 ---------- */
  function objective(teams, setup) {
    const conds = activeConditions(setup);
    const sc = [], pen = { e: 0, w: 0 };
    teams.forEach(t => {
      sc.push(teamMetrics(t.members, setup.weights).score);
      teamIssues(t.members, setup, conds).forEach(i => i.level === "error" ? pen.e++ : pen.w++);
    });
    globalIssues(teams, setup).forEach(i => i.level === "error" ? pen.e++ : pen.w++);
    return mean(sc) - 0.5 * std(sc) - 1000 * pen.e - 5 * pen.w;
  }

  function buildUnits(people, setup) {
    const parent = {}; people.forEach(p => parent[p.id] = p.id);
    const find = x => parent[x] === x ? x : (parent[x] = find(parent[x]));
    (setup.pairs || []).filter(p => p.type === "fix" && parent[p.a] != null && parent[p.b] != null)
      .forEach(p => { parent[find(p.a)] = find(p.b); });
    const g = {}; people.forEach(p => (g[find(p.id)] = g[find(p.id)] || []).push(p));
    return Object.values(g);
  }

  function greedyInit(free, sizes, setup, rng) {
    const conds = activeConditions(setup), ew = effectiveWeights(setup.weights);
    const teams = sizes.map((s, i) => ({ cap: s, members: [], idx: i }));
    const units = buildUnits(free, setup);
    const scarcity = u => (u.some(p => p.roles.includes("발표")) ? 2 : 0) + (u.some(p => p.roles.some(r => DEV_ROLES.includes(r))) ? 1 : 0);
    units.forEach(u => u._r = rng());
    units.sort((a, b) => b.length - a.length || scarcity(b) - scarcity(a) || a._r - b._r);
    const splitWith = (id) => (setup.pairs || []).filter(p => p.type === "split" && (p.a === id || p.b === id)).map(p => p.a === id ? p.b : p.a);
    for (const u of units) {
      let best = null, bestGain = -Infinity;
      for (const t of teams) {
        const room = t.cap - t.members.length;
        let gain = room >= u.length ? 0 : -5000 - (u.length - room) * 100;
        const after = t.members.concat(u), before = teamMetrics(t.members, setup.weights), now = teamMetrics(after, setup.weights);
        gain += (now.parts.role - before.parts.role) * ew.role * 0.6 + (now.parts.major - before.parts.major) * ew.major * 0.5;
        gain += (now.parts.time - before.parts.time) * ew.time * 0.6 + (now.parts.trait - before.parts.trait) * ew.trait * 0.3;
        gain += room * 0.5; // 아직 빈자리가 많은 팀을 약간 우대
        for (const c of conds) {
          const need = c.id === "dev" ? (m => m.roles.some(r => DEV_ROLES.includes(r))) : c.role ? (m => m.roles.includes(c.role)) : null;
          if (need && !t.members.some(m => m.submitted && need(m)) && u.some(m => m.submitted && need(m))) gain += 40;
        }
        if (setup.hard?.sameMajor) u.forEach(p => { if (after.filter(m => m.m === p.m).length > 2) gain -= 3000; });
        u.forEach(p => splitWith(p.id).forEach(o => { if (t.members.some(m => m.id === o)) gain -= 4000; }));
        gain += rng() * 0.01;
        if (gain > bestGain) { bestGain = gain; best = t; }
      }
      best.members.push(...u);
    }
    return teams.map((t, i) => ({ no: i + 1, locked: false, members: t.members }));
  }

  function improve(teams, setup, rng, iters, lockedNos) {
    const movable = teams.filter(t => !lockedNos.has(t.no));
    if (movable.length < 2) return;
    const conds = activeConditions(setup);
    const evalTeam = t => {
      const sc = teamMetrics(t.members, setup.weights).score; let e = 0, w = 0;
      teamIssues(t.members, setup, conds).forEach(i => i.level === "error" ? e++ : w++);
      return { sc, e, w };
    };
    const cache = new Map(teams.map(t => [t, evalTeam(t)]));
    const glob = () => { let e = 0, w = 0; globalIssues(teams, setup).forEach(i => i.level === "error" ? e++ : w++); return { e, w }; };
    const total = g => {
      const vals = [...cache.values()], sc = vals.map(v => v.sc);
      return mean(sc) - 0.5 * std(sc) - 1000 * (vals.reduce((a, v) => a + v.e, 0) + g.e) - 5 * (vals.reduce((a, v) => a + v.w, 0) + g.w);
    };
    let g = glob(), cur = total(g);
    for (let k = 0; k < iters; k++) {
      const a = movable[Math.floor(rng() * movable.length)], b = movable[Math.floor(rng() * movable.length)];
      if (a === b || !a.members.length || !b.members.length) continue;
      const i = Math.floor(rng() * a.members.length), j = Math.floor(rng() * b.members.length);
      const ca = cache.get(a), cb = cache.get(b);
      let tmp = a.members[i]; a.members[i] = b.members[j]; b.members[j] = tmp;
      cache.set(a, evalTeam(a)); cache.set(b, evalTeam(b));
      const g2 = glob(), o = total(g2);
      if (o > cur + 1e-9) { cur = o; g = g2; }
      else { tmp = a.members[i]; a.members[i] = b.members[j]; b.members[j] = tmp; cache.set(a, ca); cache.set(b, cb); }
    }
  }

  /** participants: [{id,n,m,y,roles,sched,traits,submitted,transfer}] */
  function solve(participants, setup, opts = {}) {
    const seed = opts.seed || 1, restarts = opts.restarts || 5, iters = opts.iters || 1500;
    const lockedIn = (opts.locked || []).map(l => ({ no: l.no, locked: true, members: l.members.slice() }));
    const lockedIds = new Set(lockedIn.flatMap(l => l.members.map(m => m.id)));
    const free = participants.filter(p => !lockedIds.has(p.id));
    const plan = planTeamCount(free.length, setup.size, setup.rest);
    const lockedNos = new Set(lockedIn.map(l => l.no));
    const freeNos = []; for (let n = 1; freeNos.length < plan.teams; n++) if (!lockedNos.has(n)) freeNos.push(n);
    let best = null, bestObj = -Infinity;
    for (let r = 0; r < restarts; r++) {
      const rng = mulberry32(seed * 1009 + r * 7919 + 17);
      const fresh = greedyInit(free, plan.sizes, setup, rng).map((t, i) => ({ ...t, no: freeNos[i] }));
      const all = lockedIn.concat(fresh).sort((x, y) => x.no - y.no);
      improve(all, setup, rng, iters, lockedNos);
      const o = objective(all, setup);
      if (o > bestObj) { bestObj = o; best = all; }
    }
    return { teams: best || lockedIn, objective: bestObj, plan };
  }

  const api = {
    DAYS, BLOCKS, ROLES, DEV_ROLES, ALL_SLOTS, slotKey, mulberry32, mean,
    effectiveWeights, planTeamCount, describePlan, parseNote, activeConditions,
    teamMetrics, evaluate, solve, intersect
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TM = Object.assign(root.TM || {}, api);
})(typeof window !== "undefined" ? window : globalThis);
