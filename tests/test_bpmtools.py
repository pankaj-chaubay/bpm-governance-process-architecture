import shutil
from pathlib import Path

import pytest
import yaml

from bpmtools import catalog, generate, lint
from bpmtools.__main__ import cmd_check

ROOT = Path(__file__).resolve().parents[1]
VERBS = set(yaml.safe_load((ROOT / "architecture/governance.yaml").read_text())["approved_task_verbs"])


def spec(**over):
    s = {
        "id": "T1", "name": "Test", "owner": "Owner", "version": "1.0", "lanes": ["A", "B"],
        "nodes": [
            {"id": "s", "type": "startEvent", "name": "Request received", "lane": "A"},
            {"id": "t", "type": "userTask", "name": "Check request", "lane": "A"},
            {"id": "g", "type": "exclusiveGateway", "name": "Request OK?", "lane": "B"},
            {"id": "u", "type": "userTask", "name": "Approve request", "lane": "B"},
            {"id": "e", "type": "endEvent", "name": "Request closed", "lane": "B"},
        ],
        "flows": [["s", "t"], ["t", "g"], ["g", "u", "Yes"], ["g", "t", "No"], ["u", "e"]],
    }
    s.update(over)
    return s


def run(tmp_path, s):
    p = tmp_path / "m.bpmn"
    p.write_text(generate.to_bpmn(s))
    return {f.rule for f in lint.lint_file(p, VERBS)}


def test_clean_model_has_no_findings(tmp_path):
    assert run(tmp_path, spec()) == set()


def test_unlabelled_gateway_flow(tmp_path):
    s = spec(flows=[["s", "t"], ["t", "g"], ["g", "u", "Yes"], ["g", "t"], ["u", "e"]])
    assert "BPM005" in run(tmp_path, s)


def test_dead_end_and_orphan(tmp_path):
    s = spec()
    s["nodes"].append({"id": "x", "type": "userTask", "name": "Check orphan", "lane": "A"})
    rules = run(tmp_path, s)
    assert {"BPM003", "BPM004"} <= rules


def test_endless_loop_is_found(tmp_path):
    s = spec(flows=[["s", "t"], ["t", "g"], ["g", "u", "Yes"], ["g", "t", "No"], ["u", "t"]])
    s["nodes"] = [n for n in s["nodes"] if n["id"] != "e"]
    assert "BPM002" in run(tmp_path, s)


def test_naming_rules(tmp_path):
    s = spec()
    s["nodes"][1]["name"] = "Credit check"
    s["nodes"][2]["name"] = "Request OK"
    rules = run(tmp_path, s)
    assert {"BPM009", "BPM010"} <= rules


def test_missing_documentation(tmp_path):
    p = tmp_path / "m.bpmn"
    p.write_text(generate.to_bpmn(spec()).replace("Owner: Owner; ", ""))
    assert "BPM013" in {f.rule for f in lint.lint_file(p, VERBS)}


def test_generated_files_are_in_sync_with_sources(tmp_path):
    for src in (ROOT / "models/src").glob("*.yaml"):
        expected = generate.to_bpmn(yaml.safe_load(src.read_text()))
        assert (ROOT / "models" / f"{src.stem}.bpmn").read_text() == expected, f"run build-models for {src.name}"


def test_released_models_are_clean():
    repo = catalog.Repo.load(ROOT)
    gov, models = catalog.check_catalog(repo)
    procs = repo.processes()
    released = set(procs.loc[procs["status"] == "released", "model"].dropna())
    assert not [f for f in models if f.file in released and f.severity == "error"]


def test_catalog_findings_match_the_planted_issues():
    gov, _ = catalog.check_catalog(catalog.Repo.load(ROOT))
    rules = {(f.rule, f.element.split(" ")[0]) for f in gov}
    assert ("GOV001", "P06.1.2") in rules          # draft without owner
    assert ("GOV003", "P01.2.1") in rules          # overdue review
    assert ("GOV007", "P04.1.2") in rules          # duplicate of P04.1.1


def test_check_blocks_a_released_process_with_a_broken_model(tmp_path):
    work = tmp_path / "repo"
    shutil.copytree(ROOT / "architecture", work / "architecture")
    shutil.copytree(ROOT / "models", work / "models")
    cat = (work / "architecture/process_catalog.yaml").read_text()
    cat = cat.replace("name: Offboard employee, owner: HR Operations Lead, status: in_review", "name: Offboard employee, owner: HR Operations Lead, status: released")
    (work / "architecture/process_catalog.yaml").write_text(cat)
    assert cmd_check(work, tmp_path / "out") == 1
    assert cmd_check(ROOT, tmp_path / "out2") == 0


def test_inventory_counts_elements():
    inv = lint.element_inventory(ROOT / "models/procure_to_pay.bpmn")
    assert inv["exclusiveGateway"] == 3 and inv["lane"] == 4


def test_capability_heatmap_flags_gaps():
    heat = catalog.capability_heatmap(catalog.Repo.load(ROOT)).set_index("capability")
    assert heat.loc["C06.3 Risk management", "processes"] == 0
    assert heat.loc["C06.3 Risk management", "priority"] == "high"
