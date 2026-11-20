# Playbook: moving a process repository to a new BPM platform

A general method for moving a BPMN repository from one modelling platform to another (for example from one BPM suite to another when a licence ends). It is not tied to any vendor. The inventory step runs on the models in this repository: `python -m bpmtools check` writes `reports/migration_inventory.csv`.

## 1. Inventory

Know what you are moving before choosing how.

| Item | How |
|---|---|
| Models per status | Process catalog: released models move first, drafts are reviewed before they move |
| Element types per model | `migration_inventory.csv`: count of tasks, gateways, events, lanes, flows |
| Elements that may not convert cleanly | Complex gateways, ad-hoc sub-processes, non-BPMN shapes, vendor extension attributes, data objects, attachments |
| Users and their roles | Licence list split into modellers, reviewers and readers |
| Integrations | Links to other systems (architecture tools, BI, document management) |

## 2. Map

Write down how each object type in the old platform maps to the new one: BPMN elements, custom attributes (owner, version, catalog ID), dictionaries such as roles and systems, and the folder or architecture structure. Anything without a clean match gets a decision: convert, rebuild by hand, or drop.

## 3. Clean before you move

Moving is the cheapest moment to clean up. Run the checker and fix errors in released models, retire duplicates (GOV007), assign missing owners (GOV001) and drop retired content that nobody needs.

## 4. Pilot

Move one process area end to end. Compare element counts before and after (the inventory again), open each model, and have the process owners confirm the result. Fix the mapping, then repeat for the rest.

## 5. Cut-over

| Step | Detail |
|---|---|
| Freeze | Old platform read-only from a fixed date. Changes wait or are made in the new platform |
| Bulk move | By process area, in the order of the pilot |
| Check | Inventory comparison per area. Checker run on the exported BPMN |
| Switch links | Intranet, document links and integrations point to the new platform |
| Decommission | Old platform archived, then switched off when the contract ends |
| Rollback | Old platform stays read-only until all areas are confirmed |

## 6. Adoption

A new platform is only worth it if people use it.

| Measure | Definition | Example target |
|---|---|---|
| Active users within 30 days | Users who opened or edited a model in the first 30 days / users with access | 80% |
| Modellers trained | Modellers who completed the platform training / all modellers | 100% before cut-over |
| Models changed in the new platform | Released models with at least one approved change after cut-over | grows each month |
| Support tickets per week | Tickets about the new platform | falls after week 4 |

Training by role works better than one session for everyone: modellers need the editor and the conventions, reviewers need the approval flow, readers need search and navigation.
