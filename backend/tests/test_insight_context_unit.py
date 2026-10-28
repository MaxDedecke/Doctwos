"""Scope and bounded-context contracts without an inference provider."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.insight_context import retrieve_insight_context
from services.insight_graph import append_insight_graph


class InsightContextTests(unittest.TestCase):
    def test_no_project_never_queries(self):
        db = MagicMock()
        self.assertEqual(retrieve_insight_context(db, object(), None, "Payment"), "")
        db.query.assert_not_called()

    @patch("services.insight_context.assert_project_visible")
    def test_snapshot_and_budget(self, visible):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            SimpleNamespace(
                id=1,
                title="Payment",
                content="x" * 9000,
                status="verified",
                evidence_json=[{"file": "big.cbl"}],
            ),
            SimpleNamespace(
                id=2,
                title="Payment",
                content="reviewed claim",
                status="verified",
                evidence_json=[{"file": "PAY.cbl"}],
            ),
            SimpleNamespace(
                id=3, title="Payment", content="no evidence", status="verified", evidence_json=[]
            ),
        ]
        user = object()
        context = retrieve_insight_context(db, user, 7, "Payment")
        visible.assert_called_once_with(7, user, db)
        self.assertIn("PAY.cbl", context)
        self.assertIn("reviewed claim", context)
        self.assertNotIn("big.cbl", context)
        self.assertNotIn("no evidence", context)
        self.assertLess(len(context), 8500)

    def test_insight_without_resolvable_evidence_keeps_snapshot(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            SimpleNamespace(
                id=3,
                project_id=7,
                title="Process",
                content="Claim",
                status="draft",
                evidence_json=[{"chat_message_id": 42}],
            )
        ]
        nodes, edges = {}, []
        append_insight_graph(db, [7], nodes, edges, MagicMock(), MagicMock())
        self.assertEqual(nodes["insight:3"]["evidence"], [{"chat_message_id": 42}])
        self.assertEqual(edges, [])
