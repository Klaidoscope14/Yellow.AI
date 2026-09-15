"""Deterministic chatbot over loop-report.json.

Rule 1: the assistant must *retrieve and phrase* facts the pipeline already
computed -- it must never derive a new fact from the logs. So this is a keyword
intent router over the finished report, plus an explicit refusal path for
anything outside the 11 asks or outside what was measured. No LLM, no log access.
"""
from __future__ import annotations

from typing import Any, Dict, List

# Intent -> keyword set. First intent with the most keyword hits wins.
_INTENTS = {
    "failover":     ["failover", "fail over", "fall back to another model", "alternate model"],
    "gaps":         ["can't", "cant", "cannot", "couldn't", "couldnt", "unanswerable",
                     "not measurable", "measure", "gap", "don't know", "dont know"],
    "dismissed":    ["ruled out", "rule out", "dismiss", "lookalike", "look-alike",
                     "false alarm", "decoy", "checked out", "not a problem"],
    "cost":         ["cost", "spend", "spent", "expensive", "money", "budget", "$"],
    "trend":        ["better or worse", "getting worse", "getting better", "trend",
                     "month over month", "improving", "declining"],
    "kb":           ["knowledge", "knowledge base", "kb", "retrieval", "articles",
                     "answering questions"],
    "tool":         ["tool", "api", "integration", "empty", "silent", "error rate"],
    "review":       ["review", "should a human", "look at", "audit"],
    "who":          ["who should", "who needs", "whose job", "responsible", "who acts"],
    "broke":        ["broke", "break", "wrong", "problem", "regression", "what happened",
                     "this week", "issues", "what's broken", "whats broken"],
    "containment":  ["containment", "contained", "without a human", "end to end",
                     "automated", "automation", "self-serve", "self serve",
                     "bot handled", "handle end to end", "share of conversations"],
    "journey":      ["journey", "drop off", "dropping out", "drop-off", "dropoff",
                     "funnel", "returns flow", "returns journey", "stage of the",
                     "where are people dropping"],
    "upgrade":      ["model upgrade", "upgrade", "model change", "new model",
                     "help or hurt", "helped or hurt"],
    "abandon":      ["gave up", "frustration", "frustrated", "abandon", "abandoned",
                     "rage quit", "walked away", "walking away", "left angry",
                     "giving up"],
}

_ROLE_LABEL = {"agent_builder": "the agent builder", "business_owner": "the business owner",
               "platform_owner": "the platform team"}


def _regressions(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [f for f in report.get("findings", []) if f.get("is_regression")]


def _dismissed(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [f for f in report.get("findings", []) if not f.get("is_regression")]


def _finding_link(f: Dict[str, Any]) -> Dict[str, str]:
    return {"screen": "finding", "id": f.get("id")}


def _rank(question: str) -> str:
    q = question.lower().replace("‘", "'").replace("’", "'")
    q = q.replace("“", '"').replace("”", '"')
    best, best_hits = "broke", 0
    for intent, kws in _INTENTS.items():
        hits = sum(1 for kw in kws if kw in q)
        if hits > best_hits:
            best, best_hits = intent, hits
    return best if best_hits > 0 else "unknown"


def _answer_broke(report):
    regs = _regressions(report)
    if not regs:
        return {"answer": "Good news -- nothing is flagged as a regression this week.",
                "based_on": [], "link": None, "refusal": False}
    top = regs[0]
    lines = ["{} problem(s) need attention this week. The most serious:".format(len(regs)),
             "* {}".format(top.get("plain_summary"))]
    if len(regs) > 1:
        for f in regs[1:]:
            lines.append("* {}".format(f.get("plain_summary")))
    return {"answer": "\n".join(lines), "based_on": [f["id"] for f in regs],
            "link": _finding_link(top), "refusal": False}


def _answer_gaps(report):
    gaps = report.get("gaps", [])
    if not gaps:
        return {"answer": "There were no measurement gaps to report.", "based_on": [],
                "link": None, "refusal": False}
    lines = ["Here's what we deliberately did not answer, and why:"]
    for g in gaps:
        lines.append("* {}".format(g.get("why")))
    return {"answer": "\n".join(lines), "based_on": [g.get("ask_id") for g in gaps],
            "link": {"screen": "refusals"}, "refusal": True}


def _answer_failover(report):
    g = next((g for g in report.get("gaps", []) if g.get("ask_id") == "A11"), None)
    if g:
        lines = ["Failover rate is not measurable with current instrumentation."]
        lines.append(g.get("why", ""))
        proxy = g.get("nearest_proxy")
        mislead = g.get("why_the_proxy_misleads")
        if proxy and mislead:
            lines.append("The nearest proxy ({}) is misleading: {}".format(proxy, mislead))
        req = g.get("required_event")
        if req:
            lines.append(
                "To measure it, the runtime would need to emit a '{}' event "
                "recording {} (owner: {}).".format(
                    req["name"], ", ".join(req["fields"]), req.get("owner", "unknown")))
        return {"answer": "\n".join(lines), "based_on": ["A11"],
                "link": {"screen": "refusals"}, "refusal": True}
    return _answer_gaps(report)


def _answer_dismissed(report):
    dis = _dismissed(report)
    if not dis:
        return {"answer": "Nothing was flagged and then dismissed this week.", "based_on": [],
                "link": None, "refusal": False}
    lines = ["We looked at {} thing(s) and ruled them out as normal:".format(len(dis))]
    for f in dis:
        lines.append("* {}".format(f.get("plain_summary")))
    return {"answer": "\n".join(lines), "based_on": [f["id"] for f in dis],
            "link": {"screen": "dismissed"}, "refusal": False}


def _answer_cost(report):
    prompt_reg = next((f for f in _regressions(report)
                       if (f.get("impact", {}) or {}).get("cost_usd")), None)
    if prompt_reg:
        imp = prompt_reg["impact"]
        return {"answer": (
            "The clearest cost issue: {} That has added about ${} in extra model spend "
            "so far across {} conversations.".format(
                prompt_reg.get("plain_summary"),
                imp.get("cost_usd"),
                imp.get("conversations_affected"))),
                "based_on": [prompt_reg["id"]], "link": _finding_link(prompt_reg), "refusal": False}
    m = next((m for m in report.get("metrics", []) if m.get("id") == "m_cost"), None)
    if m:
        return {"answer": (
            "We track cost per conversation on the v3 assistants "
            "(covering {:.0%} of traffic; legacy flows carry no model cost). "
            "No cost regression is flagged this week.".format(m["coverage"]["value"])),
                "based_on": ["A08"], "link": None, "refusal": False}
    return _refusal()


def _answer_trend(report):
    return {"answer": (
        "'Better or worse' depends on which metric and cohort. We avoid a single "
        "blended trend because a shift in the mix of question types can move the "
        "overall number without any real change -- each question type is compared "
        "on its own against its healthy standard instead."),
            "based_on": ["A02"], "link": None, "refusal": False}


def _answer_kb(report):
    kb = next((f for f in _regressions(report)
               if "kb" in str((f.get("cohort"))) or f.get("metric") == "kb_miss_rate"
               or "knowledge" in f.get("plain_summary", "").lower()), None)
    if kb:
        return {"answer": kb.get("plain_summary"), "based_on": [kb["id"]],
                "link": _finding_link(kb), "refusal": False}
    return {"answer": "The knowledge base is answering as expected -- no retrieval gap is flagged.",
            "based_on": ["A06"], "link": None, "refusal": False}


def _answer_tool(report):
    tool = next((f for f in _regressions(report)
                 if "tool" in str(f.get("cohort")) or f.get("metric") == "silent_fail_rate"), None)
    if tool:
        return {"answer": tool.get("plain_summary"), "based_on": [tool["id"]],
                "link": _finding_link(tool), "refusal": False}
    return {"answer": "Tool calls are succeeding at the expected rate -- no tool failure is flagged.",
            "based_on": ["A04"], "link": None, "refusal": False}


def _answer_who(report):
    regs = _regressions(report)
    if not regs:
        return {"answer": "No problems need an owner this week.", "based_on": [], "link": None,
                "refusal": False}
    lines = ["Who needs to act:"]
    for f in regs:
        roles = ", ".join(_ROLE_LABEL.get(a, a) for a in f.get("audience", []))
        lines.append("* {} -> {}.".format(f.get("plain_summary"), roles))
    return {"answer": "\n".join(lines), "based_on": [f["id"] for f in regs],
            "link": _finding_link(regs[0]), "refusal": False}


def _answer_review(report):
    regs = _regressions(report)
    if regs:
        return {"answer": (
            "The conversations worth a human's time are the ones inside this "
            "week's flagged problems -- start with: " + regs[0].get("plain_summary")),
                "based_on": [f["id"] for f in regs], "link": _finding_link(regs[0]),
                "refusal": False}
    return {"answer": "No cohort stands out for human review this week.", "based_on": [],
            "link": None, "refusal": False}


def _answer_containment(report):
    res_regs = [f for f in _regressions(report)
                if f.get("metric") in ("kb_miss_rate", "silent_fail_rate", "resolution_rate")]
    if res_regs:
        top = res_regs[0]
        lines = ["Containment is under pressure this week. {}".format(top.get("plain_summary"))]
        if len(res_regs) > 1:
            for f in res_regs[1:]:
                lines.append("* {}".format(f.get("plain_summary")))
        imp = top.get("impact", {})
        if imp.get("conversations_affected"):
            lines.append("({} conversations affected, {:.1%} of traffic.)".format(
                imp["conversations_affected"], imp.get("share_of_traffic", 0)))
        return {"answer": "\n".join(lines), "based_on": [f["id"] for f in res_regs],
                "link": _finding_link(res_regs[0]), "refusal": False}
    m = next((m for m in report.get("metrics", []) if m.get("id") == "m_containment"), None)
    if m:
        return {"answer": (
            "No containment regression is flagged this week -- the share of "
            "conversations handled end to end without a human is holding steady."),
                "based_on": ["A01"], "link": None, "refusal": False}
    return {"answer": (
        "Containment rate (conversations resolved without a human) is tracked but "
        "no regression was flagged this week."),
            "based_on": ["A01"], "link": None, "refusal": False}


def _answer_journey(report):
    journey_findings = [f for f in report.get("findings", [])
                        if "return" in str(f.get("cohort", {}).get("intent", "")).lower()]
    if journey_findings:
        regs = [f for f in journey_findings if f.get("is_regression")]
        if regs:
            top = regs[0]
            return {"answer": top.get("plain_summary"), "based_on": [top["id"]],
                    "link": _finding_link(top), "refusal": False}
        dis = [f for f in journey_findings if not f.get("is_regression")]
        if dis:
            return {"answer": (
                "The returns flow was checked and nothing abnormal was found: " +
                dis[0].get("plain_summary", "")),
                    "based_on": [dis[0]["id"]], "link": _finding_link(dis[0]), "refusal": False}
    return {"answer": (
        "We track resolution, containment, and abandonment by intent -- but this "
        "report does not break down an individual journey into milestones (e.g. "
        "label-printed -> item-received -> refund-issued). To answer 'where in the "
        "returns journey people drop off', we would need a milestone definition "
        "for the returns flow, not just session-level outcomes."),
            "based_on": ["A05"], "link": None, "refusal": True}


def _answer_upgrade(report):
    judge = [f for f in report.get("findings", [])
             if f.get("metric") == "quality_score"
             or "judge" in str(f.get("not_a_regression_because", "")).lower()
             or (f.get("evidence") and
                 any("judge" in str(e).lower() or "rubric" in str(e).lower()
                     for e in f["evidence"]))]
    prompt_regs = [f for f in _regressions(report) if f.get("metric") == "median_turns"]
    lines = []
    refs = []
    if judge:
        lines.append(judge[0].get("plain_summary", "A quality score shift was observed."))
        refs.append(judge[0]["id"])
    if prompt_regs:
        lines.append(prompt_regs[0].get("plain_summary", ""))
        refs.append(prompt_regs[0]["id"])
    if lines:
        return {"answer": "\n".join(lines), "based_on": refs,
                "link": _finding_link((judge + prompt_regs)[0]), "refusal": False}
    return {"answer": (
        "No model-related regression is flagged this week. Two signals would show "
        "it: a quality-score cliff on all tenants at once (a judge/rubric change, "
        "not the model), or a prompt regression inflating turns. Neither fired."),
            "based_on": ["A07"], "link": None, "refusal": False}


def _answer_abandon(report):
    m = next((m for m in report.get("metrics", []) if m.get("id") == "m_abandon_reason"), None)
    if m:
        lines = ["We track abandonment in two layers:"]
        lines.append(
            "* Session-level abandonment (how many left without resolving) is MEASURED "
            "-- it comes straight from session_end='abandoned'.")
        lines.append(
            "* The reason (frustration vs. got-what-they-needed) is JUDGED -- it "
            "requires a rubric applied to the final turns, so the number carries the "
            "judge's calibration, not just a counter.")
        calib = m.get("calibration")
        if calib:
            lines.append(
                "Current judge calibration: {:.0%} agreement with "
                "human labels over {} sessions (judge {}).".format(
                    calib["agreement"], calib["n"], calib["judge_version"]))
        lines.append("Treat the frustration count as an estimate, not a hard number.")
        return {"answer": "\n".join(lines), "based_on": ["A09"], "link": None, "refusal": False}
    return {"answer": (
        "Abandonment (users who left without resolving) is measured, but "
        "classifying the reason -- frustration vs. satisfied departure -- "
        "requires a judged rubric over the final turns, which this report "
        "includes as an estimate, not a hard count."),
            "based_on": ["A09"], "link": None, "refusal": False}


def _refusal():
    return {"answer": (
        "I can only answer from this week's performance report -- the problems we "
        "found, what we checked and ruled out, and what we couldn't measure. "
        'Try: "What broke this week?", "What can\'t you tell me?", or "How\'s cost?"'),
            "based_on": [], "link": None, "refusal": True}


_HANDLERS = {
    "broke": _answer_broke, "gaps": _answer_gaps, "failover": _answer_failover,
    "dismissed": _answer_dismissed, "cost": _answer_cost, "trend": _answer_trend,
    "kb": _answer_kb, "tool": _answer_tool, "who": _answer_who, "review": _answer_review,
    "containment": _answer_containment, "journey": _answer_journey,
    "upgrade": _answer_upgrade, "abandon": _answer_abandon,
}

SUGGESTIONS = ["What broke this week?", "What can't you tell me?", "How's cost?",
               "What did you rule out?", "How's containment?",
               "Are users giving up out of frustration?"]


def answer(question: str, report: Dict[str, Any]) -> Dict[str, Any]:
    if not question or not question.strip():
        return _refusal()
    intent = _rank(question)
    handler = _HANDLERS.get(intent)
    result = handler(report) if handler else _refusal()
    result["intent"] = intent
    return result
