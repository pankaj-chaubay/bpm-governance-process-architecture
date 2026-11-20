"""Governance checks on the process catalog, and the numbers for the governance dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from .lint import Finding, lint_file

GOV_RULES = {
    "GOV001": ("error", "Process has no owner, or the owner is not a defined role"),
    "GOV002": ("error", "Status is not part of the lifecycle"),
    "GOV003": ("warning", "Review date has passed"),
    "GOV004": ("error", "Linked model file is missing or belongs to another process"),
    "GOV005": ("error", "Released process links to a model that has errors"),
    "GOV006": ("warning", "Process links to no capability, or to one that is not in the capability map"),
    "GOV007": ("warning", "Possible duplicate of another process"),
    "GOV008": ("warning", "Released process has no review date"),
    "GOV009": ("warning", "Review interval is longer than allowed"),
}


@dataclass
class Repo:
    catalog: dict
    governance: dict
    capabilities: dict
    models_dir: Path

    @classmethod
    def load(cls, root: Path) -> "Repo":
        def y(p):
            return yaml.safe_load((root / p).read_text(encoding="utf-8"))

        return cls(y("architecture/process_catalog.yaml"), y("architecture/governance.yaml"), y("architecture/capability_map.yaml"), root / "models")

    def processes(self) -> pd.DataFrame:
        rows = []
        for a in self.catalog["areas"]:
            for g in a["groups"]:
                for p in g["processes"]:
                    rows.append({"area_id": a["id"], "area": a["name"], "area_type": a["type"], "group": g["name"], **p})
        df = pd.DataFrame(rows)
        for c in ["model", "owner", "next_review"]:
            if c not in df:
                df[c] = None
        return df

    @property
    def verbs(self) -> set[str]:
        return set(self.governance["approved_task_verbs"])


def _words(name: str) -> set[str]:
    stop = {"and", "the", "of", "to", "from", "a", "new"}
    out = set()
    for w in name.lower().split():
        if w in stop:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)  # employees -> employee
    return out


def check_catalog(repo: Repo) -> tuple[list[Finding], list[Finding]]:
    """Returns (governance findings, model lint findings)."""
    df = repo.processes()
    rules = repo.governance["rules"]
    as_of = date.fromisoformat(repo.catalog["as_of"])
    roles = set(repo.governance["roles"])
    statuses = set(repo.governance["lifecycle"]["statuses"])
    caps = {c["id"] for c in repo.capabilities["capabilities"]}
    gov: list[Finding] = []
    model_findings: list[Finding] = []

    def add(rule, pid, detail=""):
        sev, msg = GOV_RULES[rule]
        gov.append(Finding("process_catalog.yaml", rule, sev, pid, msg + (f": {detail}" if detail else "")))

    for r in df.itertuples(index=False):
        pid = f"{r.id} {r.name}"
        owner = r.owner if isinstance(r.owner, str) and r.owner.strip() else None
        if owner is None or owner not in roles:
            add("GOV001", pid, owner or "no owner")
        if r.status not in statuses:
            add("GOV002", pid, str(r.status))
        if r.status != "retired":
            if not r.next_review:
                if r.status == "released":
                    add("GOV008", pid)
            else:
                due = date.fromisoformat(str(r.next_review))
                if due < as_of:
                    add("GOV003", pid, f"due {due}")
                months = (due.year - as_of.year) * 12 + due.month - as_of.month
                if months > rules["max_review_interval_months"]:
                    add("GOV009", pid, f"{months} months")
        if not r.capabilities or any(c not in caps for c in r.capabilities):
            add("GOV006", pid)
        if isinstance(r.model, str) and r.model:
            path = repo.models_dir / r.model
            if not path.exists():
                add("GOV004", pid, r.model)
                continue
            text = path.read_text(encoding="utf-8")
            if f"Catalog ID: {r.id}" not in text:
                add("GOV004", pid, f"{r.model} does not carry Catalog ID {r.id}")
            found = lint_file(path, repo.verbs, rules["max_flow_nodes_per_model"])
            model_findings += found
            if r.status == "released" and rules["released_models_must_have_no_errors"] and any(f.severity == "error" for f in found):
                add("GOV005", pid, r.model)

    # duplicates: word overlap between process names
    live = df[df["status"] != "retired"].reset_index(drop=True)
    for i in range(len(live)):
        for j in range(i + 1, len(live)):
            a, b = _words(live.loc[i, "name"]), _words(live.loc[j, "name"])
            sim = len(a & b) / len(a | b)
            if sim >= rules["duplicate_name_similarity"]:
                add("GOV007", f"{live.loc[j, 'id']} {live.loc[j, 'name']}", f"{live.loc[i, 'id']} {live.loc[i, 'name']} ({sim:.0%} word overlap)")
    return gov, model_findings


def dashboard(repo: Repo, gov: list[Finding], model_findings: list[Finding]) -> dict:
    df = repo.processes()
    live = df[df["status"] != "retired"]
    owned = live["owner"].isin(repo.governance["roles"])
    as_of = date.fromisoformat(repo.catalog["as_of"])
    overdue = live["next_review"].map(lambda d: bool(d) and date.fromisoformat(str(d)) < as_of)
    modelled = live["model"].map(lambda m: isinstance(m, str) and bool(m))
    model_files = sorted(repo.models_dir.glob("*.bpmn"))
    err_models = {f.file for f in model_findings if f.severity == "error"}
    return {
        "processes_total": int(len(df)),
        "processes_live": int(len(live)),
        "by_status": ", ".join(f"{v} {k}" for k, v in df["status"].value_counts().items()),
        "owner_coverage_pct": round(100 * owned.mean(), 1),
        "overdue_reviews": int(overdue.sum()),
        "modelled_in_bpmn_pct": round(100 * modelled.mean(), 1),
        "models_without_errors": f"{len(model_files) - len(err_models)} of {len(model_files)}",
        "governance_errors": sum(f.severity == "error" for f in gov),
        "governance_warnings": sum(f.severity == "warning" for f in gov),
        "model_errors": sum(f.severity == "error" for f in model_findings),
        "model_warnings": sum(f.severity == "warning" for f in model_findings),
    }


def capability_heatmap(repo: Repo) -> pd.DataFrame:
    df = repo.processes()
    live = df[df["status"] != "retired"]
    rows = []
    for c in repo.capabilities["capabilities"]:
        procs = live[live["capabilities"].map(lambda caps, cid=c["id"]: cid in (caps or []))]
        released = int((procs["status"] == "released").sum())
        gap = c["importance"] - c["maturity"]
        rows.append(
            {
                "capability": f"{c['id']} {c['name']}",
                "domain": c["domain"],
                "importance": c["importance"],
                "maturity": c["maturity"],
                "gap": gap,
                "processes": int(len(procs)),
                "released": released,
                "systems": ", ".join(sorted({s for ss in procs["systems"] for s in (ss or [])})),
                "priority": "high" if gap >= 2 or (len(procs) == 0 and c["importance"] >= 4) else "medium" if gap == 1 else "low",
            }
        )
    out = pd.DataFrame(rows)
    order = {"high": 0, "medium": 1, "low": 2}
    return out.sort_values(["priority", "gap"], key=lambda s: s.map(order) if s.name == "priority" else -s).reset_index(drop=True)
