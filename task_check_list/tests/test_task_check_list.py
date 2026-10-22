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

    def test_bug_progress_exceeds_100_after_project_gains_checklists(self):
        """
        Regression: marking global items then adding project-specific checklists
        must not cause progress > 100%.
        """
        project_c = self.env["project.project"].create({"name": "Project C"})
        task_c = self.env["project.task"].create(
            {"name": "Task C", "project_id": project_c.id}
        )
        # Mark global item while project has no own checklists (valid use)
        task_c.task_checklist = [(6, 0, [self.checklist_global.id])]
        task_c._compute_checklist_progress()
        self.assertAlmostEqual(task_c.checklist_progress, 100.0)

        # Project gains its first own checklist
        self.env["task.checklist"].create(
            {"name": "Step C1", "project_id": project_c.id}
        )
        task_c._compute_checklist_progress()
        # Bug: currently returns 100% because global item is still counted
        self.assertAlmostEqual(task_c.checklist_progress, 0.0)

    def test_bug_progress_resets_when_project_loses_all_checklists(self):
        """
        Regression: when all project-specific checklists are deleted, checklist_progress
        must reflect the now-empty task_checklist (0%), not the stale stored value.
        """
        project_c = self.env["project.project"].create({"name": "Project C3"})
        task_c = self.env["project.task"].create(
            {"name": "Task C3", "project_id": project_c.id}
        )
        c1 = self.env["task.checklist"].create(
            {"name": "Step C1", "project_id": project_c.id}
        )
        c2 = self.env["task.checklist"].create(
            {"name": "Step C2", "project_id": project_c.id}
        )
        task_c.task_checklist = [(6, 0, [c1.id, c2.id])]
        task_c._compute_checklist_progress()
        self.assertAlmostEqual(task_c.checklist_progress, 100.0)

        # Project loses all its own checklists
        (c1 | c2).unlink()

        # task_checklist should be empty (FK cascade) and progress = 0%
        self.assertFalse(task_c.task_checklist)
        self.assertAlmostEqual(task_c.checklist_progress, 0.0)

    def test_progress_truly_partial(self):
        """1 of 2 project checklists checked → 50%."""
        checklist_a2 = self.env["task.checklist"].create(
            {"name": "Step A2", "project_id": self.project_a.id}
        )
        self.task_a.task_checklist = [(6, 0, [self.checklist_a.id])]
        self.task_a._compute_checklist_progress()
        self.assertAlmostEqual(self.task_a.checklist_progress, 50.0)

    def test_progress_updates_when_project_gains_additional_checklist(self):
        """Adding a 2nd checklist to a project updates progress for existing tasks (denominator grows)."""
        self.task_a.task_checklist = [(6, 0, [self.checklist_a.id])]
        self.task_a._compute_checklist_progress()
        self.assertAlmostEqual(self.task_a.checklist_progress, 100.0)

        self.env["task.checklist"].create(
            {"name": "Step A2", "project_id": self.project_a.id}
        )
        # Denominator is now 2, only 1 checked → 50%
        self.assertAlmostEqual(self.task_a.checklist_progress, 50.0)

    def test_progress_updates_when_one_checklist_deleted(self):
        """Deleting one of two checklists raises progress for tasks that had it checked."""
        checklist_a2 = self.env["task.checklist"].create(
            {"name": "Step A2", "project_id": self.project_a.id}
        )
        self.task_a.task_checklist = [(6, 0, [self.checklist_a.id])]
        self.task_a._compute_checklist_progress()
        self.assertAlmostEqual(self.task_a.checklist_progress, 50.0)

        checklist_a2.unlink()
        # Denominator back to 1, still 1 checked → 100%
        self.assertAlmostEqual(self.task_a.checklist_progress, 100.0)

    def test_all_project_tasks_recomputed_on_checklist_create(self):
        """Adding a checklist recomputes progress for ALL tasks of that project."""
        task_a2 = self.env["project.task"].create(
            {"name": "Task A2", "project_id": self.project_a.id}
        )
        self.task_a.task_checklist = [(6, 0, [self.checklist_a.id])]
        task_a2.task_checklist = [(6, 0, [self.checklist_a.id])]
        self.task_a._compute_checklist_progress()
        task_a2._compute_checklist_progress()

        self.env["task.checklist"].create(
            {"name": "Step A2", "project_id": self.project_a.id}
        )
        self.assertAlmostEqual(self.task_a.checklist_progress, 50.0)
        self.assertAlmostEqual(task_a2.checklist_progress, 50.0)

    def test_bug_stale_globals_removed_when_project_gains_checklists(self):
        """
        Regression: global items must be removed from task_checklist when the
        project gains its first own checklist.
        """
        project_c = self.env["project.project"].create({"name": "Project C2"})
        task_c = self.env["project.task"].create(
            {"name": "Task C2", "project_id": project_c.id}
        )
        task_c.task_checklist = [(6, 0, [self.checklist_global.id])]
        self.assertIn(self.checklist_global, task_c.task_checklist)

        # Project gains its first own checklist
        self.env["task.checklist"].create(
            {"name": "Step C1", "project_id": project_c.id}
        )
        # Bug: global item is still in task_checklist
        self.assertNotIn(self.checklist_global, task_c.task_checklist)
