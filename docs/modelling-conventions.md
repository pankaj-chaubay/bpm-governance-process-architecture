# BPMN modelling conventions

Short rules so that every model in the repository reads the same way. Rules marked with an ID are checked by `python -m bpmtools lint` on any BPMN 2.0 file.

## Structure

* One pool per end-to-end process, one lane per role (not per person or department name that may change).
* Every flow node sits in a lane. (BPM012)
* At least one start event and one end event. (BPM001, BPM002)
* Every element has an incoming and an outgoing flow, except start and end events. (BPM003, BPM004)
* Every element can be reached from a start event, and an end event can be reached from every element. No dead ends, no endless loops. (BPM006, BPM007)
* A parallel split is closed by a parallel join. (BPM016)
* No more than 30 flow nodes in one model. Above that, use sub-processes. (BPM014)
* Every element has a diagram shape, so nothing is hidden. (BPM015)

## Naming

* **Tasks**: verb + object, starting with an approved verb ("Create purchase order", not "Purchase order creation"). The list is in `architecture/governance.yaml`. (BPM009)
* **Deciding gateways**: a yes/no question ending in "?" ("Three-way match OK?"). (BPM010)
* **Gateway outgoing flows**: labelled with the answer ("Yes", "No", "Above limit"). (BPM005)
* **Events**: named as a state, in past tense ("Invoice paid", "Vacancy approved"). (BPM011)
* Merging gateways have no name.

## Process documentation

The process element's documentation holds `Owner: <role>; Version: <x.y>; Catalog ID: <id>`. (BPM013) The catalog ID links the model to `architecture/process_catalog.yaml`, and the checker confirms the link (GOV004).

## Task types

| Type | Use for |
|---|---|
| User task | A person does the work in a system |
| Service task | A system does the work without a person |
| Send / receive task | A message goes to or comes from an outside party |
| Manual task | Work without a system |
| Task (untyped) | Work by an outside party in another pool or lane, for example a supplier |

## Levels

| Level | Content | Notation |
|---|---|---|
| 1 Process area | Core, support and management areas | Process house |
| 2 Process group | Groups inside an area | Process house |
| 3 End-to-end process | From trigger to outcome, across roles | BPMN 2.0 collaboration |
| 4 Work instruction | Steps inside one task | Text or checklist, linked from the task |
