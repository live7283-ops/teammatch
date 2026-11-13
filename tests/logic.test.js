// 실행: node tests/logic.test.js  (외부 의존성 없음)
const assert = require("assert");
const L = require("../js/logic.js");
let pass = 0; const t = (name, fn) => { try { fn(); pass++; console.log("  ✓", name); } catch (e) { console.error("  ✗", name, "\n   ", e.message); process.exitCode = 1; } };

function makePeople(n, seed = 7) {
  const rng = L.mulberry32(seed), majors = ["SW융합","경영학","컴퓨터공학","시각디자인","전기전자공학","AI소프트웨어","미디어","산업경영"];
  return Array.from({ length: n }, (_, i) => {
    const roles = []; while (roles.length < 2) { const r = L.ROLES[Math.floor(rng() * 6)]; if (!roles.includes(r)) roles.push(r); }
    const sched = L.ALL_SLOTS.filter(() => rng() < 0.55);
    return { id: "s" + i, n: "학생" + i, m: majors[Math.floor(rng() * majors.length)], y: 1 + Math.floor(rng() * 4), roles, sched,
      traits: { pace: 1 + Math.floor(rng() * 5), prep: 1 + Math.floor(rng() * 5), lead: 1 + Math.floor(rng() * 5), comm: 1 + Math.floor(rng() * 5) },
      submitted: true, transfer: rng() < 0.1 };
  });
}
const baseSetup = () => ({ size: 4, rest: "extra", weights: { major: 4, role: 5, time: 3, trait: 3 }, hard: { sameMajor: true }, note: "", pairs: [], parsedOff: {} });

console.log("planTeamCount");
t("38명/4명/extra → 9팀 (5명 팀 2개)", () => { const p = L.planTeamCount(38, 4, "extra"); assert.equal(p.teams, 9); assert.equal(p.sizes.filter(s => s === 5).length, 2); assert.equal(p.sizes.reduce((a, b) => a + b), 38); });
t("38명/4명/fewer → 10팀 (3명 팀 2개)", () => { const p = L.planTeamCount(38, 4, "fewer"); assert.equal(p.teams, 10); assert.equal(p.sizes.filter(s => s === 3).length, 2); });
t("0명, 인원 < 팀 크기", () => { assert.equal(L.planTeamCount(0, 4, "extra").teams, 0); assert.equal(L.planTeamCount(3, 4, "extra").teams, 1); });

console.log("effectiveWeights / parseNote");
t("가중치 1 = 고려하지 않음 → 0", () => { const e = L.effectiveWeights({ major: 1, role: 5, time: 1, trait: 1 }); assert.equal(e.major, 0); assert.equal(e.role, 4); });
t("전부 1이면 균등 가중으로 대체", () => assert.equal(L.effectiveWeights({ major: 1, role: 1, time: 1, trait: 1 }).equal, true));
t("기획안 예시 문장 해석", () => { const c = L.parseNote("발표 경험이 있는 학생과 개발 경험이 있는 학생을 각 팀에 최소 1명씩 포함해 주세요. 4학년은 한 팀에 몰리지 않게 해주세요.").map(x => x.id); assert.deepEqual(c, ["present", "dev", "year4"]); });
t("인식 불가 문장은 조건 0개", () => assert.equal(L.parseNote("서로 친하게 지내면 좋겠어요").length, 0));

console.log("solve");
const people = makePeople(44);
t("모든 인원이 정확히 한 번씩 배정되고 팀 크기가 계획과 같다", () => {
  const s = baseSetup(), r = L.solve(people, s, { seed: 1 });
  const ids = r.teams.flatMap(x => x.members.map(m => m.id)); assert.equal(ids.length, 44); assert.equal(new Set(ids).size, 44);
  assert.deepEqual(r.teams.map(x => x.members.length).sort(), r.plan.sizes.slice().sort());
});
t("같은 시드 → 동일 결과, 다른 시드 → 다른 결과", () => {
  const s = baseSetup(), sig = r => r.teams.map(x => x.members.map(m => m.id).sort().join()).join("|");
  assert.equal(sig(L.solve(people, s, { seed: 3 })), sig(L.solve(people, s, { seed: 3 })));
  assert.notEqual(sig(L.solve(people, s, { seed: 3 })), sig(L.solve(people, s, { seed: 4 })));
});
t("지역 탐색이 그리디 단독보다 목적값을 개선한다", () => {
  const s = baseSetup(), a = L.solve(people, s, { seed: 5, iters: 0, restarts: 1 }), b = L.solve(people, s, { seed: 5, iters: 1500, restarts: 1 });
  assert.ok(b.objective >= a.objective, `${b.objective} < ${a.objective}`);
});
t("같은 학과 2명 이하 제약이 지켜진다", () => { const s = baseSetup(), r = L.solve(people, s, { seed: 2 }), ev = L.evaluate(r.teams, s); assert.equal(ev.issues.filter(i => /최대 2명\)/.test(i.text) && i.level === "error").length, 0); });
t("요구사항(발표·개발 각 팀 1명) 위반 0건", () => { const s = { ...baseSetup(), note: "발표와 개발 경험자를 각 팀에 1명씩" }; const r = L.solve(people, s, { seed: 2 }); assert.equal(L.evaluate(r.teams, s).errors, 0); });
t("고정/분리 쌍이 지켜진다", () => {
  const s = { ...baseSetup(), pairs: [{ a: "s0", b: "s1", type: "fix" }, { a: "s2", b: "s3", type: "split" }, { a: "s1", b: "s4", type: "fix" }] };
  const r = L.solve(people, s, { seed: 9 }), where = {}; r.teams.forEach(x => x.members.forEach(m => where[m.id] = x.no));
  assert.equal(where.s0, where.s1); assert.equal(where.s1, where.s4); assert.notEqual(where.s2, where.s3); assert.equal(L.evaluate(r.teams, s).errors, 0);
});
t("고정된 팀은 재실행해도 구성원이 유지된다", () => {
  const s = baseSetup(), first = L.solve(people, s, { seed: 1 }), keep = first.teams[2];
  const again = L.solve(people, s, { seed: 99, locked: [{ no: keep.no, members: keep.members }] });
  const t = again.teams.find(x => x.no === keep.no); assert.deepEqual(t.members.map(m => m.id).sort(), keep.members.map(m => m.id).sort());
  assert.equal(again.teams.flatMap(x => x.members).length, 44);
});
t("불가능한 제약은 숨기지 않고 위반으로 보고한다 (발표 희망자 3명, 4팀)", () => {
  const ppl = makePeople(16).map(p => ({ ...p, roles: p.roles.filter(r => r !== "발표").concat(["기획"]).slice(0, 2) }));
  [0, 1, 2].forEach(i => ppl[i].roles = ["발표", "기획"]);
  const s = { ...baseSetup(), note: "발표 가능한 사람이 각 팀에 한 명씩" }, r = L.solve(ppl, s, { seed: 1 }), ev = L.evaluate(r.teams, s);
  assert.equal(r.teams.length, 4); assert.equal(ev.errors, 1); assert.ok(ev.issues.some(i => /발표/.test(i.text)));
});
t("가중치 1(고려하지 않음)인 항목은 점수에 영향이 없다", () => {
  const m = people.slice(0, 4), a = L.teamMetrics(m, { major: 1, role: 5, time: 1, trait: 1 }), b = L.teamMetrics(m.map(x => ({ ...x, traits: { pace: 1, prep: 5, lead: 1, comm: 5 } })), { major: 1, role: 5, time: 1, trait: 1 });
  assert.equal(a.score, b.score);
});
t("인원 0명·1명도 예외 없이 처리", () => { assert.equal(L.solve([], baseSetup(), {}).teams.length, 0); assert.equal(L.solve(makePeople(1), baseSetup(), {}).teams.length, 1); });
t("평가는 팀 교환 후에도 재계산 가능 (공통 시간은 실제 교집합)", () => {
  const s = baseSetup(), r = L.solve(people, s, { seed: 1 }), t0 = r.teams[0];
  const m = L.teamMetrics(t0.members, s.weights); const manual = L.ALL_SLOTS.filter(k => t0.members.every(x => x.sched.includes(k))).length;
  assert.equal(m.overlap, manual);
});
t("성능: 45명 편성 < 1.5초", () => { const t0 = Date.now(); L.solve(people, baseSetup(), { seed: 1 }); const dt = Date.now() - t0; console.log("     소요", dt, "ms"); assert.ok(dt < 1500); });
console.log(`\n${pass}개 통과`);
