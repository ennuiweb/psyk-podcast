import importlib.util
import unittest
from pathlib import Path

from notebooklm import RPCError
from notebooklm.rpc.types import RPCMethod


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "notebooklm-podcast-auto" / "generate_podcast.py"
    spec = importlib.util.spec_from_file_location("generate_podcast", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GeneratePodcastTests(unittest.TestCase):
    def test_classifies_create_notebook_missing_result_as_profile_error(self):
        mod = _load_module()
        exc = RPCError(
            "No result found for RPC ID: CCqFvf",
            method_id=RPCMethod.CREATE_NOTEBOOK.value,
        )

        self.assertTrue(mod._is_profile_rotation_error(exc))
        self.assertTrue(mod._should_rotate_profile(exc))
        self.assertEqual(mod._classify_error(exc), "profile_error")

    def test_error_details_include_rpc_metadata(self):
        mod = _load_module()
        exc = RPCError(
            "No result found for RPC ID: CCqFvf",
            method_id=RPCMethod.CREATE_NOTEBOOK.value,
            rpc_code=3,
            found_ids=[RPCMethod.CREATE_NOTEBOOK.value],
        )

        self.assertEqual(
            mod._error_details(exc),
            {
                "rpc_method_id": RPCMethod.CREATE_NOTEBOOK.value,
                "rpc_code": 3,
                "rpc_found_ids": [RPCMethod.CREATE_NOTEBOOK.value],
            },
        )

    def test_does_not_classify_unrelated_rpc_error_as_profile_error(self):
        mod = _load_module()
        exc = RPCError(
            "No result found for RPC ID: rLM1Ne",
            method_id="rLM1Ne",
            rpc_code=5,
        )

        self.assertFalse(mod._is_profile_rotation_error(exc))
        self.assertFalse(mod._should_rotate_profile(exc))
        self.assertEqual(mod._classify_error(exc), "other")


if __name__ == "__main__":
    unittest.main()
