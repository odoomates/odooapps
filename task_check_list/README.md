# Task Check List

Adds a configurable checklist to project tasks in Odoo 19.0.

**Author:** Odoo Mates, Jenrax
**Version:** 19.0.1.1.0
**License:** Other proprietary

---

## What it does

- Adds a **Checklist** tab to the project task form with selectable checklist items and a progress indicator.
- Adds a **progress bar** column to the task list view.
- Checklist items are managed from **Project → Configuration → Task Checklist**.

### Visibility rules

| Checklist type | When visible in a task |
|----------------|----------------------|
| Project-specific (`project_id` set) | Only in tasks of that project |
| Global (`project_id` empty) | Only in tasks whose project has **no** own checklists (fallback) |

This means a project either uses its own custom checklist or the global one — never both at the same time.

### Progress

`checklist_progress` is computed as:

```
(checked items) / (total available items for the project) × 100
```

The denominator follows the same visibility rule: project-specific items if any exist, otherwise globals.

---

## Configuration

Go to **Project → Configuration → Task Checklist** to manage checklist items.

Each item has:

| Field | Description |
|-------|-------------|
| Name | Label shown in the task checklist |
| Project | Leave empty to make the item global (fallback for all projects) |
| Description | Optional notes about the item |
| Sequence | Controls display order (drag handle in the list) |

The list is grouped by project by default.

---

## Usage

1. Open or create a project task.
2. Go to the **Checklist** tab.
3. Check the items that have been completed.
4. The progress pie updates automatically.

---

## Installation

```bash
"C:/Odoo/jenrax/v19/.venv/Scripts/python.exe" "C:/Odoo/19.0/odoo-bin" \
    -c "C:/Odoo/19.0/odoo_oca_sign.conf" \
    -i task_check_list -d <db_name> --stop-after-init
```

---

## Running tests

```bash
"C:/Odoo/jenrax/v19/.venv/Scripts/python.exe" "C:/Odoo/19.0/odoo-bin" \
    -c "C:/Odoo/19.0/odoo_oca_sign.conf" \
    --test-enable --stop-after-init \
    -i task_check_list -d <db_name>
```
