import importlib.util
import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from notebooklm import RPCError
from notebooklm.rpc.types import RPCMethod, ReportFormat


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "notebooklm-podcast-auto" / "generate_podcast.py"
    spec = importlib.util.spec_from_file_location("generate_podcast", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GeneratePodcastTests(unittest.TestCase):
    def test_report_request_payload_includes_report_format(self):
        mod = _load_module()
        args = SimpleNamespace(
            artifact_type="report",
            instructions="Study guide instructions",
            language="en",
            sources_file=None,
            report_format="study-guide",
        )

        payload = mod._build_request_payload(
            created_at="2026-05-03T10:00:00Z",
            notebook_id="nb-1",
            notebook_title="Notebook",
            artifact_id="art-1",
            output_path=Path("/tmp/output.md"),
            args=args,
            sources=[{"kind": "file", "value": "/tmp/source.pdf"}],
            auth_meta={"source": "profile"},
        )

        self.assertEqual(payload["artifact_type"], "report")
        self.assertEqual(payload["report_format"], "study-guide")

    def test_report_format_defaults_to_study_guide(self):
        mod = _load_module()
        self.assertEqual(mod._report_format(None), ReportFormat.STUDY_GUIDE)
        self.assertEqual(mod._report_format("briefing-doc"), ReportFormat.BRIEFING_DOC)

    def test_classifies_create_notebook_missing_result_as_profile_error(self):
        mod = _load_module()
        exc = RPCError(
            "No result found for RPC ID: CCqFvf",
            method_id=RPCMethod.CREATE_NOTEBOOK.value,
        )

        self.assertTrue(mod._is_profile_rotation_error(exc))
        self.assertTrue(mod._should_rotate_profile(exc))
        self.assertEqual(mod._classify_error(exc), "profile_error")

    def test_classifies_create_artifact_missing_result_as_profile_error(self):
        mod = _load_module()
        exc = RPCError(
            "RPC R7cb6c returned null result data (possible server error or parameter mismatch)",
            method_id=RPCMethod.CREATE_ARTIFACT.value,
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

    def test_resolve_notebook_skips_oldest_when_pending_artifacts_exist(self):
        mod = _load_module()

        class FakeArtifacts:
            async def list(self, notebook_id):
                if notebook_id == "nb-oldest":
                    return [
                        SimpleNamespace(
                            id="art-pending",
                            title="Queued audio",
                            is_processing=False,
                            is_pending=True,
                            status_str="pending",
                        )
                    ]
                return []

        class FakeNotebooks:
            def __init__(self):
                self.create_calls = 0
                self.deleted_ids = []

            async def list(self):
                return [
                    SimpleNamespace(
                        id="nb-oldest",
                        title="Oldest",
                        created_at=datetime(2026, 1, 1),
                        is_owner=True,
                    ),
                    SimpleNamespace(
                        id="nb-next",
                        title="Next",
                        created_at=datetime(2026, 1, 2),
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

        client = SimpleNamespace(notebooks=FakeNotebooks(), artifacts=FakeArtifacts())
        notebook = asyncio.run(mod._resolve_notebook(client, "Target", reuse=False))

        self.assertEqual(notebook.id, "nb-created")
        self.assertEqual(client.notebooks.deleted_ids, ["nb-next"])

    def test_resolve_notebook_skips_oldest_when_request_log_output_is_missing(self):
        mod = _load_module()

        class FakeArtifacts:
            async def list(self, notebook_id):
                return []

        class FakeNotebooks:
            def __init__(self):
                self.create_calls = 0
                self.deleted_ids = []

            async def list(self):
                return [
                    SimpleNamespace(
                        id="nb-oldest",
                        title="Oldest",
                        created_at=datetime(2026, 1, 1),
                        is_owner=True,
                    ),
                    SimpleNamespace(
                        id="nb-next",
                        title="Next",
                        created_at=datetime(2026, 1, 2),
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

        client = SimpleNamespace(notebooks=FakeNotebooks(), artifacts=FakeArtifacts())

        with self.subTest("request log blocks deletion when output missing"):
            original_cwd = Path.cwd()
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_root = Path(tmpdir)
                request_log = tmp_root / "pending.mp3.request.json"
                request_log.write_text(
                    json.dumps(
                        {
                            "notebook_id": "nb-oldest",
                            "artifact_id": "art-123",
                            "output_path": str(tmp_root / "pending.mp3"),
                        }
                    ),
                    encoding="utf-8",
                )
                os.chdir(tmp_root)
                try:
                    notebook = asyncio.run(mod._resolve_notebook(client, "Target", reuse=False))
                finally:
                    os.chdir(original_cwd)

        self.assertEqual(notebook.id, "nb-created")
        self.assertEqual(client.notebooks.deleted_ids, ["nb-next"])

    def test_request_log_guard_allows_deletion_when_output_exists(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            output_path = tmp_root / "done.mp3"
            output_path.write_bytes(b"audio")
            request_log = tmp_root / "done.mp3.request.json"
            request_log.write_text(
                json.dumps(
                    {
                        "notebook_id": "nb-safe",
                        "artifact_id": "art-123",
                        "output_path": str(output_path),
                    }
                ),
                encoding="utf-8",
            )
            matches = mod._find_undownloaded_request_logs(tmp_root, "nb-safe")

        self.assertEqual(matches, [])

    def test_build_auth_candidates_falls_back_when_auto_profiles_are_missing(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            profiles_path = tmp_root / "profiles.json"
            profiles_path.write_text(
                json.dumps({"default": str(tmp_root / "missing-storage.json")}),
                encoding="utf-8",
            )
            notebooklm_home = tmp_root / "notebooklm-home"
            notebooklm_home.mkdir()
            expected_storage = (notebooklm_home / "storage_state.json").resolve()
            expected_storage.write_text("{}", encoding="utf-8")

            args = SimpleNamespace(
                storage=None,
                profile=None,
                rotate_on_rate_limit=True,
                profiles_file=str(profiles_path),
                profile_priority=None,
                preferred_profile=None,
                exclude_profiles=None,
            )

            with patch.dict(os.environ, {"NOTEBOOKLM_HOME": str(notebooklm_home)}, clear=False):
                candidates = mod._build_auth_candidates(args)

        self.assertEqual(len(candidates), 1)
        storage_path, auth_meta = candidates[0]
        self.assertEqual(storage_path, str(expected_storage))
        self.assertEqual(auth_meta["source"], "default")
        self.assertIsNone(auth_meta["profile"])

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

    def test_wait_mode_persists_request_log_before_waiting_for_completion(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "episode.mp3"
            wait_client_seen_log: dict[str, object] = {}
            output_exists = False

            class FakeClientContext:
                def __init__(self, client):
                    self._client = client

                async def __aenter__(self):
                    return self._client

                async def __aexit__(self, exc_type, exc, tb):
                    return False

            class FakeArtifacts:
                async def wait_for_completion(self, notebook_id, artifact_id, timeout, initial_interval):
                    request_log = output_path.with_suffix(output_path.suffix + ".request.json")
                    wait_client_seen_log["exists"] = request_log.exists()
                    wait_client_seen_log["payload"] = json.loads(request_log.read_text(encoding="utf-8"))
                    return SimpleNamespace(is_complete=True, task_id=artifact_id)

                async def download_audio(self, notebook_id, output, artifact_id):
                    Path(output).write_bytes(b"audio")

            fake_client = SimpleNamespace(artifacts=FakeArtifacts())
            fake_status = SimpleNamespace(task_id="artifact-123")
            fake_notebook = SimpleNamespace(id="nb-123", title="Notebook")
            from_storage_calls: list[Path | None] = []

            async def fake_from_storage(storage_path):
                from_storage_calls.append(storage_path)
                return FakeClientContext(fake_client)

            args = SimpleNamespace(
                output=str(output_path),
                source=[str(Path(tmpdir) / "source.pdf")],
                sources_file=None,
                skip_existing=False,
                notebook_title="Notebook",
                append_profile_to_notebook_title=False,
                reuse_notebook=False,
                source_timeout=30,
                ensure_sources_ready=False,
                artifact_type="audio",
                instructions="Prompt",
                audio_format="deep-dive",
                audio_length="long",
                language="en",
                artifact_retries=0,
                artifact_retry_backoff=5.0,
                infographic_orientation=None,
                infographic_detail=None,
                quiz_quantity=None,
                quiz_difficulty=None,
                quiz_format="json",
                report_format="study-guide",
                wait=True,
                generation_timeout=30,
                initial_interval=1,
                rotate_on_rate_limit=True,
            )

            with patch.object(mod, "_load_sources", return_value=[{"kind": "file", "value": "source.pdf"}]):
                with patch.object(mod, "_build_auth_candidates", return_value=[(None, {"profile": "good", "source": "profile"})]):
                    with patch.object(mod.NotebookLMClient, "from_storage", side_effect=fake_from_storage):
                        with patch.object(mod, "_resolve_notebook", return_value=fake_notebook):
                            with patch.object(mod, "_add_sources", return_value=None):
                                with patch.object(mod, "_generate_audio_with_retry", return_value=fake_status):
                                    exit_code = asyncio.run(mod._generate_podcast(args))
                                    output_exists = output_path.exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(from_storage_calls, [None, None])
        self.assertTrue(wait_client_seen_log["exists"])
        payload = wait_client_seen_log["payload"]
        self.assertEqual(payload["artifact_id"], "artifact-123")
        self.assertEqual(payload["notebook_id"], "nb-123")
        self.assertTrue(output_exists)


if __name__ == "__main__":
    unittest.main()
