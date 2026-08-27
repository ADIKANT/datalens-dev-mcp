from __future__ import annotations

import tempfile
import unittest

from datalens_dev_mcp.pipeline.execution_authorization import (
    authorizes_write,
    resolve_execution_authorization,
    validate_execution_authorization,
)
from datalens_dev_mcp.pipeline.task_contract import DeliveryContract, WorkspaceContract, create_task_contract


class ExecutionAuthorizationTests(unittest.TestCase):
    def contract(self, delivery: DeliveryContract):
        with tempfile.TemporaryDirectory() as tmp:
            return create_task_contract(
                raw_request="Synthetic authorization contract",
                mode="update" if delivery.save else "review",
                route="unresolved",
                workspace=WorkspaceContract(project_root=tmp),
                delivery=delivery,
            ).to_dict()

    def test_explicit_write_is_hash_bound_and_run_boundary_is_irrelevant(self) -> None:
        contract = self.contract(DeliveryContract(save=True, publish=True))
        grant = resolve_execution_authorization(contract)
        self.assertFalse(validate_execution_authorization(grant, contract))
        self.assertEqual(grant["mode"], "automatic_from_explicit_request")
        self.assertTrue(authorizes_write(grant))
        self.assertTrue(authorizes_write(grant, publish=True))

    def test_read_only_and_destructive_modes_do_not_gain_ordinary_write(self) -> None:
        read_only = resolve_execution_authorization(self.contract(DeliveryContract()))
        destructive = resolve_execution_authorization(self.contract(DeliveryContract(save=True, destructive=True)))
        self.assertFalse(authorizes_write(read_only))
        self.assertFalse(authorizes_write(destructive))
        self.assertEqual(destructive["mode"], "destructive_exact_token")

    def test_mutation_or_wrong_contract_is_rejected(self) -> None:
        contract = self.contract(DeliveryContract(save=True))
        grant = resolve_execution_authorization(contract)
        grant["authorized_delivery"]["save"] = False
        self.assertIn("execution authorization hash mismatch", validate_execution_authorization(grant, contract))


if __name__ == "__main__":
    unittest.main()
