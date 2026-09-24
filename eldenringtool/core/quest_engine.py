from __future__ import annotations
from typing import Any, Callable


def eval_condition(expr: Any, flags=None, found: set[str] | None = None) -> bool:
    found = found or set()
    if expr is None: return True
    if isinstance(expr, bool): return expr
    if isinstance(expr, list): return all(eval_condition(x, flags, found) for x in expr)
    if not isinstance(expr, dict): return False
    if "flag" in expr:
        want = bool(expr.get("value", True))
        try: return flags is not None and flags.get(int(expr["flag"])) == want
        except Exception: return False
    if "marker" in expr:
        return (str(expr["marker"]) in found) == bool(expr.get("value", True))
    if "all" in expr: return all(eval_condition(x, flags, found) for x in expr["all"])
    if "any" in expr: return any(eval_condition(x, flags, found) for x in expr["any"])
    if "none" in expr: return all(not eval_condition(x, flags, found) for x in expr["none"])
    if "not" in expr: return not eval_condition(expr["not"], flags, found)
    return expr.get("always") is True


def local_text(value, locale="zh"):
    if isinstance(value, str): return value
    if not isinstance(value, dict): return ""
    return value.get(locale) or value.get("en") or value.get("zh") or next(iter(value.values()), "")


def manual_eligible(step):
    return bool(step and (step.get("guideOnly") or step.get("manual") is True))


def evaluate_quest(quest: dict, flags=None, found=None,
                   manual_done: Callable[[str, str], bool] | None = None) -> dict:
    found = set(found or ())
    steps = quest.get("steps") or []
    by_id = {str(s.get("id")): i for i, s in enumerate(steps)}
    direct = [bool(s.get("completeWhen")) and eval_condition(s.get("completeWhen"), flags, found) for s in steps]
    manual = []
    for s in steps:
        ok = False
        if manual_eligible(s) and manual_done:
            try: ok = manual_done(str(quest.get("id")), str(s.get("id"))) is True
            except Exception: ok = False
        manual.append(ok)
    failed = bool(quest.get("failWhen")) and eval_condition(quest.get("failWhen"), flags, found)
    explicit = bool(quest.get("completeWhen")) and eval_condition(quest.get("completeWhen"), flags, found)

    later_tracked = [False] * len(steps)
    seen = explicit
    for i in range(len(steps)-1, -1, -1):
        later_tracked[i] = seen
        if not steps[i].get("guideOnly") and direct[i]: seen = True
    # Required guides are retrospective: a later automatic milestone must not
    # leave them waiting for a manual click. Optional/branch choices need their
    # own evidence; never select mutually exclusive routes by list position.
    implied = [not direct[i] and not manual[i] and bool(s.get("guideOnly"))
               and s.get("inferFromLater") is not False
               and not s.get("exclusiveGroup")
               and (not s.get("optional") or s.get("inferFromLater") is True)
               and not any(s.get(k) for k in ("impliedBySteps", "implyWhen", "supersededBySteps", "supersedeWhen"))
               and later_tracked[i] for i, s in enumerate(steps)]

    groups: dict[str, dict[str, dict[str, bool]]] = {}
    for i, s in enumerate(steps):
        if not (s.get("exclusiveGroup") and s.get("exclusiveOption") and (direct[i] or manual[i] or implied[i])): continue
        e = groups.setdefault(str(s["exclusiveGroup"]), {}).setdefault(str(s["exclusiveOption"]),
                                                                        {"direct":False,"manual":False,"inferred":False})
        e["direct"] |= direct[i]; e["manual"] |= manual[i]; e["inferred"] |= implied[i]
    selected = {}
    for g, opts in groups.items():
        for kind in ("direct", "manual", "inferred"):
            vals = {o for o,e in opts.items() if e[kind]}
            if vals: selected[g] = vals; break
    missed = [bool(s.get("exclusiveGroup") and s.get("exclusiveOption") and
                   str(s["exclusiveGroup"]) in selected and
                   str(s["exclusiveOption"]) not in selected[str(s["exclusiveGroup"])]) for s in steps]
    superseded = [False] * len(steps)

    def ref_resolved(sid):
        j = by_id.get(str(sid))
        return j is not None and not missed[j] and (direct[j] or manual[j] or implied[j] or superseded[j])

    for _ in range(max(1, len(steps))):
        changed = False
        for i,s in enumerate(steps):
            if missed[i] or direct[i] or manual[i]: continue
            refs = s.get("impliedBySteps") if isinstance(s.get("impliedBySteps"), list) else []
            suprefs = s.get("supersededBySteps") if isinstance(s.get("supersededBySteps"), list) else []
            if not implied[i] and ((s.get("implyWhen") and eval_condition(s["implyWhen"], flags, found)) or any(ref_resolved(x) for x in refs)):
                implied[i] = True; superseded[i] = False; changed = True; continue
            if not implied[i] and not superseded[i] and ((s.get("supersedeWhen") and eval_condition(s["supersedeWhen"], flags, found)) or any(ref_resolved(x) for x in suprefs)):
                superseded[i] = True; changed = True
        if not changed: break

    done = [not missed[i] and (direct[i] or manual[i] or implied[i]) for i in range(len(steps))]
    resolved = [done[i] or missed[i] or superseded[i] for i in range(len(steps))]
    prev_required = True
    states=[]
    for i,s in enumerate(steps):
        guide=bool(s.get("guideOnly")); sup=superseded[i] and not done[i] and not missed[i]
        inf=implied[i] and done[i] and not direct[i] and not manual[i]
        avail=False
        if not done[i] and not missed[i] and not sup and not failed:
            avail=(eval_condition(s.get("availableWhen"),flags,found) if s.get("availableWhen") else True) and prev_required
        state = "missed" if missed[i] else "superseded" if sup else "implied" if inf else "done" if done[i] else "available" if avail else "blocked" if failed else "future"
        if not guide and not s.get("optional") and not resolved[i]: prev_required=False
        source="auto" if direct[i] and done[i] else "manual" if manual[i] and done[i] else "inferred" if inf else "superseded" if sup else "branch" if missed[i] else None
        states.append({"id":s.get("id"),"state":state,"complete":done[i],"resolved":resolved[i],"available":avail,
                       "missed":missed[i],"superseded":sup,"guideOnly":guide,"manualEligible":manual_eligible(s),
                       "manual":manual[i],"inferred":inf,"source":source})

    tracked=[i for i,s in enumerate(steps) if not s.get("guideOnly")]
    tracked_required=[i for i in tracked if not steps[i].get("optional") and not missed[i]]
    all_tracked = quest.get("autoCompleteWhenTracked") is not False and bool(tracked_required) and all(resolved[i] for i in tracked_required)
    any_tracked=any(direct[i] for i in tracked)
    any_progress=any(resolved) or any(done)
    required=[i for i,s in enumerate(steps) if not s.get("optional") and not missed[i]]
    all_required=bool(required) and all(resolved[i] for i in required)
    mca=quest.get("manualCompleteAny") if isinstance(quest.get("manualCompleteAny"),list) else []
    allow_manual=quest.get("manualCompletion") is True or bool(mca)
    mca_ok=not mca or any((by_id.get(str(x)) is not None and resolved[by_id[str(x)]]) for x in mca)
    manual_complete=all_required and mca_ok
    guide_only=not tracked
    started=(eval_condition(quest.get("startWhen"),flags,found) if quest.get("startWhen") else any_tracked) or any_progress
    first_action=next((x for x in states if x["available"]),None)
    available_start=eval_condition(quest.get("availableWhen"),flags,found) if quest.get("availableWhen") else bool(first_action)
    if failed: status="failed"
    elif explicit or all_tracked or (quest.get("autoCompleteWhenTracked") is False and allow_manual and manual_complete) or (guide_only and manual_complete): status="completed"
    elif started: status="active"
    elif available_start: status="available"
    else: status="locked"

    risks=[]
    for rule in quest.get("lockouts") or []:
        if rule.get("exclusiveGroup") and str(rule["exclusiveGroup"]) in selected: continue
        declared=rule.get("affects") or []
        affected=[sid for sid in declared if str(sid) in by_id and not resolved[by_id[str(sid)]]]
        if not affected and not (rule.get("global") and not declared): continue
        if rule.get("onlyWhen") and not eval_condition(rule["onlyWhen"],flags,found): continue
        risks.append({"id":rule.get("id"),"severity":rule.get("severity","warning"),
                      "triggered":eval_condition(rule.get("triggerWhen"),flags,found),"affected":affected})
    return {"id":quest.get("id"),"status":status,"steps":states,"current":[x["id"] for x in states if x["available"]],
            "completeCount":sum(direct[i] for i in tracked),"totalCount":len(tracked),"manualCount":sum(x["manual"] and not x["missed"] for x in states),
            "missedCount":sum(x["missed"] for x in states),"supersededCount":sum(x["superseded"] for x in states),
            "inferredCount":sum(x["inferred"] for x in states),"resolvedCount":sum(x["resolved"] for x in states),
            "stepCount":len(steps),"guideCount":len(steps)-len(tracked),"risks":risks}


def evaluate_document(doc, character, found_ids=(), manual_done=None):
    flags = character.get("_flags") if isinstance(character,dict) else getattr(character,"_flags",None)
    states={}; summary={"available":0,"active":0,"locked":0,"completed":0,"failed":0,"warnings":0,"missed":0}
    for q in doc.get("quests",[]):
        s=evaluate_quest(q,flags,set(found_ids),manual_done); states[str(q.get("id"))]=s; summary[s["status"]]=summary.get(s["status"],0)+1
        for risk in s["risks"]: summary["missed" if risk["triggered"] else "warnings"] += 1
    return {"states":states,"summary":summary}
