"""Build BPMN 2.0 XML, with diagram layout, from a short YAML definition.

The output is standard BPMN 2.0 XML with diagram interchange, checked with the
bpmn.io parser. Layout is simple on purpose: one pool, one row per lane,
nodes placed in columns by their earliest position in the flow.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

import yaml

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
}
SIZE = {"event": (36, 36), "gateway": (50, 50), "task": (110, 70)}
COL_W, LANE_H, LANE_LABEL_W, POOL_LABEL_W, X0, Y0 = 160, 140, 30, 30, 160, 80


def kind(node_type: str) -> str:
    if node_type.endswith("Event"):
        return "event"
    if node_type.endswith("Gateway"):
        return "gateway"
    return "task"


def columns(nodes: list[dict], flows: list[list]) -> dict[str, int]:
    """Longest-path column per node, ignoring back edges (loops)."""
    succ: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for f in flows:
        succ[f[0]].append(f[1])
    starts = [n["id"] for n in nodes if n["type"] == "startEvent"] or [nodes[0]["id"]]
    # find back edges with a DFS
    order, back, state = [], set(), {}

    def dfs(u):
        state[u] = 1
        for v in succ[u]:
            if state.get(v) == 1:
                back.add((u, v))
            elif v not in state:
                dfs(v)
        state[u] = 2
        order.append(u)

    for s in starts:
        if s not in state:
            dfs(s)
    for n in nodes:
        if n["id"] not in state:
            dfs(n["id"])
    col = {n["id"]: 0 for n in nodes}
    for u in reversed(order):
        for v in succ[u]:
            if (u, v) not in back:
                col[v] = max(col[v], col[u] + 1)
    return col


def to_bpmn(spec: dict) -> str:
    nodes, flows, lanes = spec["nodes"], spec["flows"], spec["lanes"]
    pid = "Process_" + spec["id"].replace(".", "_")
    col = columns(nodes, flows)
    lane_idx = {name: i for i, name in enumerate(lanes)}
    # nodes that share a lane and a column are stacked; lanes grow to fit
    stacks: dict[tuple, list[str]] = {}
    for n in nodes:
        stacks.setdefault((lane_idx[n["lane"]], col[n["id"]]), []).append(n["id"])
    lane_h = [max([LANE_H] + [len(v) * 95 + 30 for (li, _), v in stacks.items() if li == i]) for i in range(len(lanes))]
    lane_y = [Y0 + sum(lane_h[:i]) for i in range(len(lanes))]
    types = {n["id"]: n["type"] for n in nodes}
    pos = {}
    for (li, c), ids in stacks.items():
        for k, nid in enumerate(ids):
            w, h = SIZE[kind(types[nid])]
            cx = X0 + c * COL_W + 60
            cy = lane_y[li] + lane_h[li] / 2 + (k - (len(ids) - 1) / 2) * 95
            pos[nid] = (cx - w / 2, cy - h / 2, w, h)
    width = X0 + (max(col.values()) + 1) * COL_W + 60 - (X0 - POOL_LABEL_W - LANE_LABEL_W - 40)

    incoming = {n["id"]: [] for n in nodes}
    outgoing = {n["id"]: [] for n in nodes}
    flow_ids = []
    for i, f in enumerate(flows, 1):
        fid = f"Flow_{i}"
        flow_ids.append(fid)
        outgoing[f[0]].append(fid)
        incoming[f[1]].append(fid)

    doc = f"Owner: {spec['owner']}; Version: {spec['version']}; Catalog ID: {spec['id']}"
    x = ['<?xml version="1.0" encoding="UTF-8"?>']
    x.append(
        f'<bpmn:definitions xmlns:bpmn="{NS["bpmn"]}" xmlns:bpmndi="{NS["bpmndi"]}" xmlns:dc="{NS["dc"]}" '
        f'xmlns:di="{NS["di"]}" id="Defs_{pid}" targetNamespace="https://example.org/aurora/processes">'
    )
    x.append(f'  <bpmn:collaboration id="Collab_{pid}">')
    x.append(f'    <bpmn:participant id="Pool_{pid}" name="{escape(spec["name"])}" processRef="{pid}" />')
    x.append("  </bpmn:collaboration>")
    x.append(f'  <bpmn:process id="{pid}" name="{escape(spec["name"])}" isExecutable="false">')
    x.append(f"    <bpmn:documentation>{escape(doc)}</bpmn:documentation>")
    x.append(f'    <bpmn:laneSet id="LaneSet_{pid}">')
    for i, lane in enumerate(lanes):
        x.append(f'      <bpmn:lane id="Lane_{i}" name="{escape(lane)}">')
        for n in nodes:
            if n["lane"] == lane:
                x.append(f"        <bpmn:flowNodeRef>{n['id']}</bpmn:flowNodeRef>")
        x.append("      </bpmn:lane>")
    x.append("    </bpmn:laneSet>")
    for n in nodes:
        name = f' name="{escape(n["name"])}"' if n.get("name") else ""
        x.append(f'    <bpmn:{n["type"]} id="{n["id"]}"{name}>')
        x += [f"      <bpmn:incoming>{f}</bpmn:incoming>" for f in incoming[n["id"]]]
        x += [f"      <bpmn:outgoing>{f}</bpmn:outgoing>" for f in outgoing[n["id"]]]
        x.append(f"    </bpmn:{n['type']}>")
    for fid, f in zip(flow_ids, flows):
        name = f' name="{escape(f[2])}"' if len(f) > 2 else ""
        x.append(f'    <bpmn:sequenceFlow id="{fid}" sourceRef="{f[0]}" targetRef="{f[1]}"{name} />')
    x.append("  </bpmn:process>")

    # ---- diagram interchange -------------------------------------------------
    pool_x = X0 - LANE_LABEL_W - POOL_LABEL_W - 40
    pool_w = width
    x.append(f'  <bpmndi:BPMNDiagram id="Diagram_{pid}">')
    x.append(f'    <bpmndi:BPMNPlane id="Plane_{pid}" bpmnElement="Collab_{pid}">')
    x.append(f'      <bpmndi:BPMNShape id="Pool_{pid}_di" bpmnElement="Pool_{pid}" isHorizontal="true">')
    x.append(f'        <dc:Bounds x="{pool_x}" y="{Y0}" width="{pool_w}" height="{sum(lane_h)}" />')
    x.append("      </bpmndi:BPMNShape>")
    for i, _ in enumerate(lanes):
        x.append(f'      <bpmndi:BPMNShape id="Lane_{i}_di" bpmnElement="Lane_{i}" isHorizontal="true">')
        x.append(f'        <dc:Bounds x="{pool_x + POOL_LABEL_W}" y="{lane_y[i]}" width="{pool_w - POOL_LABEL_W}" height="{lane_h[i]}" />')
        x.append("      </bpmndi:BPMNShape>")
    for n in nodes:
        bx, by, w, h = pos[n["id"]]
        marker = ' isMarkerVisible="true"' if n["type"] == "exclusiveGateway" else ""
        x.append(f'      <bpmndi:BPMNShape id="{n["id"]}_di" bpmnElement="{n["id"]}"{marker}>')
        x.append(f'        <dc:Bounds x="{bx:.0f}" y="{by:.0f}" width="{w}" height="{h}" />')
        x.append("      </bpmndi:BPMNShape>")
    for fid, f in zip(flow_ids, flows):
        sx, sy, sw, sh = pos[f[0]]
        tx, ty, tw, th = pos[f[1]]
        p1 = (sx + sw, sy + sh / 2)
        p4 = (tx, ty + th / 2)
        if p4[0] <= p1[0]:  # loop back: go below the shapes
            low = max(sy + sh, ty + th) + 20
            pts = [(sx + sw / 2, sy + sh), (sx + sw / 2, low), (tx + tw / 2, low), (tx + tw / 2, ty + th)]
        elif abs(p1[1] - p4[1]) < 1:
            pts = [p1, p4]
        else:
            mid = (p1[0] + p4[0]) / 2
            pts = [p1, (mid, p1[1]), (mid, p4[1]), p4]
        x.append(f'      <bpmndi:BPMNEdge id="{fid}_di" bpmnElement="{fid}">')
        x += [f'        <di:waypoint x="{px:.0f}" y="{py:.0f}" />' for px, py in pts]
        x.append("      </bpmndi:BPMNEdge>")
    x.append("    </bpmndi:BPMNPlane>")
    x.append("  </bpmndi:BPMNDiagram>")
    x.append("</bpmn:definitions>")
    return "\n".join(x) + "\n"


def build_all(src_dir: Path, out_dir: Path) -> list[Path]:
    out = []
    for f in sorted(src_dir.glob("*.yaml")):
        spec = yaml.safe_load(f.read_text(encoding="utf-8"))
        target = out_dir / f"{f.stem}.bpmn"
        target.write_text(to_bpmn(spec), encoding="utf-8")
        out.append(target)
    return out
