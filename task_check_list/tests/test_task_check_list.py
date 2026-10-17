from odoo.tests.common import TransactionCase


class TestTaskCheckList(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project_a = cls.env["project.project"].create({"name": "Project A"})
        cls.project_b = cls.env["project.project"].create({"name": "Project B"})
        cls.checklist_global = cls.env["task.checklist"].create({"name": "Global Step"})
        cls.checklist_a = cls.env["task.checklist"].create(
            {"name": "Step A", "project_id": cls.project_a.id}
        )
        cls.checklist_b = cls.env["task.checklist"].create(
            {"name": "Step B", "project_id": cls.project_b.id}
        )
        cls.task_a = cls.env["project.task"].create(
            {"name": "Task A", "project_id": cls.project_a.id}
        )

    def _relevant_total(self, task):
        has_project = self.env["task.checklist"].search_count(
            [("project_id", "=", task.project_id.id)]
        )
        domain = (
            [("project_id", "=", task.project_id.id)]
            if has_project
            else [("project_id", "=", False)]
        )
        return self.env["task.checklist"].search_count(domain)

    def test_progress_zero_no_items_selected(self):
        self.task_a.task_checklist = [(5,)]
        self.task_a._compute_checklist_progress()
        self.assertEqual(self.task_a.checklist_progress, 0.0)

    def test_progress_partial(self):
        # Project A has checklist_a → only checklist_a counts in the total
        self.task_a.task_checklist = [(6, 0, [self.checklist_a.id])]
        self.task_a._compute_checklist_progress()
        total = self._relevant_total(self.task_a)
        self.assertEqual(total, 1)  # only checklist_a
        self.assertAlmostEqual(self.task_a.checklist_progress, 100.0)

    def test_progress_full(self):
        # Two project-specific checklists
        checklist_a2 = self.env["task.checklist"].create(
            {"name": "Step A2", "project_id": self.project_a.id}
        )
        self.task_a.task_checklist = [(6, 0, [self.checklist_a.id, checklist_a2.id])]
        self.task_a._compute_checklist_progress()
        total = self._relevant_total(self.task_a)
        self.assertEqual(total, 2)
        self.assertAlmostEqual(self.task_a.checklist_progress, 100.0)

    def test_progress_excludes_other_project_checklists(self):
        """Only the task's own project checklists count; other projects are excluded."""
        task_b = self.env["project.task"].create(
            {"name": "Task B", "project_id": self.project_b.id}
        )
        task_b.task_checklist = [(6, 0, [self.checklist_b.id])]
        task_b._compute_checklist_progress()
        total = self._relevant_total(task_b)
        # Project B has checklist_b → only that counts, not globals or checklist_a
        self.assertEqual(total, 1)
        self.assertNotIn(self.checklist_a.id, [c.id for c in task_b.task_checklist])
        self.assertAlmostEqual(task_b.checklist_progress, 100.0)

    def test_global_fallback_when_project_has_no_checklists(self):
        """A project with no own checklists falls back to global (no project_id) checklists."""
        project_c = self.env["project.project"].create({"name": "Project C"})
        task_c = self.env["project.task"].create(
            {"name": "Task C", "project_id": project_c.id}
        )
        task_c._compute_available_checklist_ids()
        available_ids = task_c.available_checklist_ids.ids
        self.assertIn(self.checklist_global.id, available_ids)
        self.assertNotIn(self.checklist_a.id, available_ids)
        self.assertNotIn(self.checklist_b.id, available_ids)

    def test_project_checklists_hide_globals(self):
        """A project with its own checklists does NOT show global checklists."""
        self.task_a._compute_available_checklist_ids()
        available_ids = self.task_a.available_checklist_ids.ids
        self.assertIn(self.checklist_a.id, available_ids)
        self.assertNotIn(self.checklist_global.id, available_ids)

    def test_sequence_ordering(self):
        """Items are returned in sequence order."""
        items = self.env["task.checklist"].search(
            [("project_id", "=", self.project_a.id)]
        )
        sequences = items.mapped("sequence")
        self.assertEqual(sequences, sorted(sequences))
