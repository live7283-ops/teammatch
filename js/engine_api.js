/* 서버 AI 엔진(POST /api/engine/solve) 호출 + 프론트 데이터 ↔ 엔진 요청 변환
   · DB·로그인 없이 후보 목록을 그대로 보내는 무상태 API 이다.
   · 서버에 닿지 못하면 EngineUnavailable 을 던지고, 호출하는 쪽(runMatching)이 로컬 계산으로 대체한다. */
(function () {
  const { DAYS } = TM;
  class EngineUnavailable extends Error {}

  /** 이번 실행에 서버 엔진을 쓸지 결정 */
  function mode() {
    const q = new URLSearchParams(location.search).get("engine");
    const m = (q === "local" || q === "server") ? q : (window.TM_CONFIG.ENGINE || "auto");
    if (m === "local") return "local";
    if (m === "auto" && !/^https?:$/.test(location.protocol)) return "local"; // file:// 은 CORS 로 어차피 막힌다
    return "server";
  }

  const ALL_SLOTS = DAYS.flatMap((_, d) => Array.from({ length: 12 }, (_, b) => `${d}-${b}`));
  /** "월-5" → "0-5" */
  const slotOf = s => { const [d, b] = String(s).split("-"); const i = DAYS.indexOf(d); return i < 0 ? null : `${i}-${b}`; };

  function toCandidate(p) {
    if (!p.submitted) // 미제출자는 가능 시간을 전부 열어 두어 팀의 공통 시간이 0이 되지 않게 한다
      return { student_id: String(p.id), name: p.n, major: p.m || null, year: Number(p.y) || null, roles: [], free_slots: ALL_SLOTS, traits: {} };
    return { student_id: String(p.id), name: p.n, major: p.m || null, year: Number(p.y) || null,
      roles: (p.roles || []).slice(), free_slots: (p.sched || []).map(slotOf).filter(Boolean), traits: { ...(p.traits || {}) } };
  }

  /** 편성 설정(S) + 참가자 → 요청 본문. 편입생 분산(evenTransfer)은 엔진 태그에 없어 보내지 않는다. */
  function toRequest(people, S, seed) {
    const pairs = S.pairs || [];
    return {
      team_size: S.size, weights: { ...S.weights }, note: S.note || "", starts: 3, seed,
      hard: { same_major_max: S.hard && S.hard.sameMajor ? 2 : null,
        fixed_pairs: pairs.filter(p => p.type === "fix").map(p => [String(p.a), String(p.b)]),
        separate_pairs: pairs.filter(p => p.type === "split").map(p => [String(p.a), String(p.b)]),
        spread_tags: [], role_minimums: {} },
      candidates: people.map(toCandidate),
    };
  }

  /** 서버 엔진 실행. 반환: { feasible:false, precheck, parsed_rules } 또는 { feasible:true, result, trace, swaps, ... } */
  async function solve(people, S, seed) {
    const cfg = window.TM_CONFIG, ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), cfg.TIMEOUT_MS || 30000);
    let res;
    try {
      res = await fetch(cfg.API_BASE.replace(/\/$/, "") + "/api/engine/solve", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(toRequest(people, S, seed)), signal: ctl.signal });
    } catch (e) { throw new EngineUnavailable(e && e.name === "AbortError" ? "응답 시간 초과" : "서버에 연결할 수 없음"); }
    finally { clearTimeout(timer); }
    if (!res.ok) { // 서버가 요청을 거부(422 등)하거나 오류(5xx)
      let msg = "HTTP " + res.status; try { const j = await res.json(); msg = (j.error && j.error.message) || msg; } catch (_) { /* 본문 없음 */ }
      throw new EngineUnavailable(msg);
    }
    return res.json();
  }

  /** 엔진 응답 → 화면에 저장할 요약(res.engine). 팀 순서는 응답의 teams 순서를 따른다. */
  function summarize(data, ms) {
    const r = data.result;
    return {
      source: "server", clientMs: ms, elapsedMs: r.elapsed_ms, seed: r.seed,
      objectiveJ: r.objective_j, avgFit: r.avg_fit, minFit: r.min_fit, violations: r.hard_violations, swaps: data.swaps,
      trace: data.trace, conditions: r.conditions || [], parsedRules: data.parsed_rules || [], weightsUsed: data.weights_used,
      composition: data.precheck && data.precheck.composition,
      teams: r.teams.map(t => ({ ids: t.members.map(m => m.student_id), fit: t.fit_score, isLowest: !!t.is_lowest, summary: t.summary,
        warnings: t.warnings || [], subscores: t.subscores, commonHours: t.common_hours, commonLabels: t.common_labels || [],
        roles: Object.fromEntries(t.members.map(m => [m.student_id, m.assigned_role])),
        ranks: Object.fromEntries(t.members.map(m => [m.student_id, m.preference_rank])) })),
    };
  }

  window.EngineAPI = { mode, solve, summarize, toRequest, EngineUnavailable };
})();
