"""Check BPMN 2.0 files against the modelling conventions in docs/modelling-conventions.md.

Works on any BPMN 2.0 XML export, not only the files generated here.
Errors block release; warnings go to the reviewer.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

B = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
DI = "{http://www.omg.org/spec/BPMN/20100524/DI}"

EVENTS = {"startEvent", "endEvent", "intermediateThrowEvent", "intermediateCatchEvent", "boundaryEvent"}
GATEWAYS = {"exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway", "complexGateway"}
TASKS = {"task", "userTask", "serviceTask", "sendTask", "receiveTask", "manualTask", "scriptTask", "businessRuleTask", "callActivity", "subProcess"}
FLOW_NODES = EVENTS | GATEWAYS | TASKS

RULES = {
    "BPM001": ("error", "Process has no start event"),
    "BPM002": ("error", "Process has no end event"),
    "BPM003": ("error", "Flow node has no incoming flow"),
    "BPM004": ("error", "Flow node has no outgoing flow"),
    "BPM005": ("error", "Outgoing flow of a deciding gateway has no label"),
    "BPM006": ("error", "Element cannot be reached from a start event"),
    "BPM007": ("error", "No end event can be reached from this element"),
    "BPM008": ("error", "Sequence flow points to an element that does not exist"),
    "BPM009": ("warning", "Task name does not start with an approved verb"),
    "BPM010": ("warning", "Deciding gateway name is not a question"),
    "BPM011": ("warning", "Event has no name"),
    "BPM012": ("warning", "Flow node is not assigned to a lane"),
    "BPM013": ("error", "Process documentation is missing owner or version"),
    "BPM014": ("warning", "Model has more flow nodes than allowed; split into sub-processes"),
    "BPM015": ("warning", "Element has no diagram shape and will not be visible"),
    "BPM016": ("warning", "Parallel split and join gateways do not match"),
}


@dataclass
class Finding:
    file: str
    rule: str
    severity: str
    element: str
    message: str


def local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def lint_file(path: Path, verbs: set[str], max_nodes: int = 30) -> list[Finding]:
    root = ET.parse(path).getroot()
    out: list[Finding] = []

    def add(rule, element, detail=""):
        sev, msg = RULES[rule]
        out.append(Finding(path.name, rule, sev, element, msg + (f": {detail}" if detail else "")))

    shapes = {s.get("bpmnElement") for s in root.iter(f"{DI}BPMNShape")} | {e.get("bpmnElement") for e in root.iter(f"{DI}BPMNEdge")}
    for proc in root.iter(f"{B}process"):
        nodes = {el.get("id"): el for el in proc if local(el.tag) in FLOW_NODES}
        flows = [el for el in proc if local(el.tag) == "sequenceFlow"]
        doc = proc.find(f"{B}documentation")
        text = doc.text if doc is not None and doc.text else ""
        if "Owner:" not in text or "Version:" not in text:
            add("BPM013", proc.get("id"))

        succ = {n: [] for n in nodes}
        pred = {n: [] for n in nodes}
        for f in flows:
            s, t = f.get("sourceRef"), f.get("targetRef")
            if s not in nodes or t not in nodes:
                add("BPM008", f.get("id"), f"{s} -> {t}")
                continue
            succ[s].append(f)
            pred[t].append(f)

        starts = [n for n, el in nodes.items() if local(el.tag) == "startEvent"]
        ends = [n for n, el in nodes.items() if local(el.tag) == "endEvent"]
        if not starts:
            add("BPM001", proc.get("id"))
        if not ends:
            add("BPM002", proc.get("id"))
        if len(nodes) > max_nodes:
            add("BPM014", proc.get("id"), f"{len(nodes)} > {max_nodes}")

        lane_members = {ref.text for ref in proc.iter(f"{B}flowNodeRef")}
        has_lanes = proc.find(f"{B}laneSet") is not None

        for nid, el in nodes.items():
            t = local(el.tag)
            name = (el.get("name") or "").strip()
            label = f"{nid} ({name})" if name else nid
            if t != "startEvent" and t != "boundaryEvent" and not pred[nid]:
                add("BPM003", label)
            if t != "endEvent" and not succ[nid]:
                add("BPM004", label)
            if t in TASKS:
                first = name.split(" ")[0].lower() if name else ""
                if first not in verbs:
                    add("BPM009", label)
            if t in EVENTS and not name:
                add("BPM011", label)
            if t in ("exclusiveGateway", "inclusiveGateway") and len(succ[nid]) > 1:
                if not name.endswith("?"):
                    add("BPM010", label)
                for f in succ[nid]:
                    if not (f.get("name") or "").strip():
                        add("BPM005", f.get("id"), f"from {label}")
            if has_lanes and nid not in lane_members:
                add("BPM012", label)
            if nid not in shapes:
                add("BPM015", label)

        # reachability
        seen, stack = set(starts), list(starts)
        while stack:
            u = stack.pop()
            for f in succ[u]:
                v = f.get("targetRef")
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        back, stack = set(ends), list(ends)
        while stack:
            u = stack.pop()
            for f in pred[u]:
                v = f.get("sourceRef")
                if v not in back:
                    back.add(v)
                    stack.append(v)
        for nid, el in nodes.items():
            name = el.get("name") or ""
            label = f"{nid} ({name})" if name else nid
            if starts and nid not in seen and pred[nid]:
                add("BPM006", label)
            if ends and nid not in back and succ[nid]:
                add("BPM007", label)

        splits = sum(1 for n, el in nodes.items() if local(el.tag) == "parallelGateway" and len(succ[n]) > 1)
        joins = sum(1 for n, el in nodes.items() if local(el.tag) == "parallelGateway" and len(pred[n]) > 1)
        if splits != joins:
            add("BPM016", proc.get("id"), f"{splits} splits, {joins} joins")
    return out


def lint_paths(paths: list[Path], verbs: set[str], max_nodes: int = 30) -> list[Finding]:
    findings: list[Finding] = []
    for p in paths:
        findings += lint_file(p, verbs, max_nodes)
    return findings


def element_inventory(path: Path) -> dict[str, int]:
    """Count element types in a model. Used for migration planning between BPM tools."""
    root = ET.parse(path).getroot()
    counts: dict[str, int] = {}
    for el in root.iter():
        t = local(el.tag)
        if el.tag.startswith(B) and (t in FLOW_NODES or t in {"sequenceFlow", "lane", "participant", "dataObjectReference", "dataStoreReference", "textAnnotation", "messageFlow"}):
            counts[t] = counts.get(t, 0) + 1
    return counts

