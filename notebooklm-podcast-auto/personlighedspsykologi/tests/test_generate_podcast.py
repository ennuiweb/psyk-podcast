import importlib.util
import asyncio
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

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

    def test_resolve_notebook_deletes_oldest_owned_notebook_and_retries(self):
        mod = _load_module()

        class FakeNotebooks:
            def __init__(self):
                self.create_calls = 0
                self.deleted_ids = []

            async def list(self):
                return [
                    SimpleNamespace(
                        id="nb-newer",
                        title="Newer",
                        created_at=datetime(2026, 2, 1),
                        is_owner=True,
                    ),
                    SimpleNamespace(
                        id="nb-oldest",
                        title="Oldest",
                        created_at=datetime(2026, 1, 1),
                        is_owner=True,
                    ),
                ]

            async def create(self, title):
                self.create_calls += 1
                if self.create_calls == 1:
                    raise RPCError(
                        "No result found for RPC ID: CCqFvf",
                        method_id=RPCMethod.CREATE_NOTEBOOK.value,
                    )
                return SimpleNamespace(id="nb-created", title=title)

            async def delete(self, notebook_id):
                self.deleted_ids.append(notebook_id)
                return True

        client = SimpleNamespace(notebooks=FakeNotebooks())

        notebook = asyncio.run(mod._resolve_notebook(client, "Target", reuse=False))

        self.assertEqual(notebook.id, "nb-created")
        self.assertEqual(client.notebooks.deleted_ids, ["nb-oldest"])
        self.assertEqual(client.notebooks.create_calls, 2)

    def test_resolve_notebook_keeps_original_error_when_no_owned_notebooks_exist(self):
        mod = _load_module()

        class FakeNotebooks:
            async def list(self):
                return [
                    SimpleNamespace(
                        id="nb-shared",
                        title="Shared",
                        created_at=datetime(2026, 1, 1),
                        is_owner=False,
                    )
                ]

            async def create(self, title):
                raise RPCError(
                    "No result found for RPC ID: CCqFvf",
                    method_id=RPCMethod.CREATE_NOTEBOOK.value,
                )

            async def delete(self, notebook_id):
                raise AssertionError("delete should not be called")

        client = SimpleNamespace(notebooks=FakeNotebooks())

        with self.assertRaises(RPCError):
            asyncio.run(mod._resolve_notebook(client, "Target", reuse=False))

    def test_resolve_notebook_does_not_delete_on_unrelated_create_error(self):
        mod = _load_module()

        class FakeNotebooks:
            def __init__(self):
                self.deleted = False

            async def list(self):
                return []

            async def create(self, title):
                raise RuntimeError("boom")

            async def delete(self, notebook_id):
                self.deleted = True
                return True

        client = SimpleNamespace(notebooks=FakeNotebooks())

        with self.assertRaisesRegex(RuntimeError, "boom"):
            asyncio.run(mod._resolve_notebook(client, "Target", reuse=False))
        self.assertFalse(client.notebooks.deleted)


if __name__ == "__main__":
    unittest.main()
