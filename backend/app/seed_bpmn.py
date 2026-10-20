# -*- coding: utf-8 -*-
"""سازنده BPMN برای داده‌های اولیه نمونه (فاز ۸).

خروجی: رشته XML سازگار با موتور SpiffWorkflow و طراح bpmn-js — شامل DI کامل
(مختصات اشکال و نقاط شکستن خطوط) تا نمودار بدون نیاز به ترسیم دستی نمایش داده شود.
"""
from dataclasses import dataclass, field as dc_field
from xml.sax.saxutils import escape

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"

# ابعاد استاندارد عناصر
SIZE = {
    "startEvent": (36, 36),
    "endEvent": (36, 36),
    "userTask": (120, 80),
    "serviceTask": (120, 80),
    "exclusiveGateway": (50, 50),
    "inclusiveGateway": (50, 50),
    "parallelGateway": (50, 50),
}


@dataclass
class Node:
    id: str
    type: str  # startEvent | endEvent | userTask | serviceTask | exclusiveGateway | ...
    name: str
    x: int
    y: int
    default_flow: str | None = None  # فقط دروازه‌ها
    attrs: dict = dc_field(default_factory=dict)  # نام‌های دیگر XML

    @property
    def w(self) -> int:
        return SIZE[self.type][0]

    @property
    def h(self) -> int:
        return SIZE[self.type][1]


@dataclass
class Flow:
    id: str
    src: str
    dst: str
    name: str = ""
    cond: str | None = None  # عبارت شرط (پایتون امن موتور)


def _element_xml(node: Node, incoming: list[str], outgoing: list[str]) -> str:
    attrs = f' id="{node.id}" name="{escape(node.name)}"'
    if node.default_flow:
        attrs += f' default="{node.default_flow}"'
    for k, v in node.attrs.items():
        attrs += f' {k}="{escape(str(v))}"'
    lines = [f"    <bpmn:{node.type}{attrs}>"]
    for i in incoming:
        lines.append(f"      <bpmn:incoming>{i}</bpmn:incoming>")
    for o in outgoing:
        lines.append(f"      <bpmn:outgoing>{o}</bpmn:outgoing>")
    lines.append(f"    </bpmn:{node.type}>")
    return "\n".join(lines)


def _flow_xml(flow: Flow) -> str:
    attrs = f' id="{flow.id}"'
    if flow.name:
        attrs += f' name="{escape(flow.name)}"'
    attrs += f' sourceRef="{flow.src}" targetRef="{flow.dst}"'
    if flow.cond:
        return (f'    <bpmn:sequenceFlow{attrs}>\n'
                f'      <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">'
                f'{escape(flow.cond)}</bpmn:conditionExpression>\n'
                f'    </bpmn:sequenceFlow>')
    return f'    <bpmn:sequenceFlow{attrs}/>'


def _waypoints(nodes: dict[str, Node], flow: Flow) -> list[tuple[int, int]]:
    s, t = nodes[flow.src], nodes[flow.dst]
    sx, sy = s.x + s.w, s.y + s.h // 2   # خروجی از سمت چپ عنصر مبدأ (چیدمان چپ‌به‌راست)
    tx, ty = t.x, t.y + t.h // 2
    if abs(sy - ty) < 6:
        return [(sx, sy), (tx, ty)]
    mx = (sx + tx) // 2
    return [(sx, sy), (mx, sy), (mx, ty), (tx, ty)]


def _edge_xml(nodes: dict[str, Node], flow: Flow) -> str:
    wps = _waypoints(nodes, flow)
    pts = "\n".join(f'        <di:waypoint x="{x}" y="{y}"/>' for x, y in wps)
    label = ""
    if flow.name:
        lx, ly = wps[len(wps) // 2]
        label = (f'\n        <bpmndi:BPMNLabel><dc:Bounds x="{lx - 10}" y="{ly - 24}" '
                 f'width="{max(30, len(flow.name) * 8)}" height="14"/></bpmndi:BPMNLabel>')
    return (f'      <bpmndi:BPMNEdge id="{flow.id}_di" bpmnElement="{flow.id}">\n'
            f'{pts}{label}\n      </bpmndi:BPMNEdge>')


def build_bpmn(defs_id: str, target_ns: str, process_id: str, process_name: str,
               nodes: list[Node], flows: list[Flow]) -> str:
    """تولید کامل BPMN با DI — سازگار با پارسر موتور و bpmn-js."""
    nd = {n.id: n for n in nodes}
    incoming: dict[str, list[str]] = {n.id: [] for n in nodes}
    outgoing: dict[str, list[str]] = {n.id: [] for n in nodes}
    for f in flows:
        outgoing[f.src].append(f.id)
        incoming[f.dst].append(f.id)

    node_xml = "\n".join(_element_xml(n, incoming[n.id], outgoing[n.id]) for n in nodes)
    flow_xml = "\n".join(_flow_xml(f) for f in flows)
    shape_xml = []
    for n in nodes:
        marker = ' isMarkerVisible="true"' if n.type == "exclusiveGateway" else ""
        shape_xml.append(
            f'      <bpmndi:BPMNShape id="{n.id}_di" bpmnElement="{n.id}"{marker}>\n'
            f'        <dc:Bounds x="{n.x}" y="{n.y}" width="{n.w}" height="{n.h}"/>\n'
            f'      </bpmndi:BPMNShape>')
    edge_xml = "\n".join(_edge_xml(nd, f) for f in flows)

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="{BPMN_NS}"
                  xmlns:bpmndi="{BPMNDI_NS}"
                  xmlns:dc="{DC_NS}"
                  xmlns:di="{DI_NS}"
                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                  id="{defs_id}" targetNamespace="{target_ns}">
  <bpmn:process id="{process_id}" name="{escape(process_name)}" isExecutable="true">
{node_xml}
{flow_xml}
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_{defs_id}">
    <bpmndi:BPMNPlane id="BPMNPlane_{defs_id}" bpmnElement="{process_id}">
{chr(10).join(shape_xml)}
{edge_xml}
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
'''
