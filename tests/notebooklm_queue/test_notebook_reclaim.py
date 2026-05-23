from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace

from notebooklm_queue.notebook_reclaim import NotebookReclaimOptions, reclaim_notebooks
from notebooklm_queue.store import QueueStore


class FakeClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeNotebooks:
    def __init__(self, notebooks: list[SimpleNamespace], *, limit: int | None = 5):
        self._notebooks = notebooks
        self._limit = limit
        self.deleted_ids: list[str] = []

    async def list(self):
        return list(self._notebooks)

    async def delete(self, notebook_id: str):
        self.deleted_ids.append(notebook_id)
        return True

    async def _get_account_limits(self):
        return SimpleNamespace(notebook_limit=self._limit)


class FakeArtifacts:
    def __init__(self, pending_ids: set[str] | None = None):
        self.pending_ids = pending_ids or set()

    async def list(self, notebook_id: str):
        if notebook_id in self.pending_ids:
            return [
                SimpleNamespace(
                    id="artifact-pending",
                    title="Queued audio",
                    is_processing=False,
                    is_pending=True,
                    status_str="pending",
                )
            ]
        return []


def _notebook(notebook_id: str, title: str, created: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=notebook_id,
        title=title,
        created_at=datetime.fromisoformat(created),
        is_owner=True,
    )


def _write_profiles_file(tmp_path: Path, storage: Path) -> Path:
    profiles_file = tmp_path / "profiles.host.json"
    profiles_file.write_text(json.dumps({"profiles": {"default": str(storage)}}), encoding="utf-8")
    return profiles_file


def _client_factory(client):
    async def factory(_storage_path: Path):
        return FakeClientContext(client)

    return factory


def test_reclaim_notebooks_dry_run_selects_oldest_without_deleting(tmp_path: Path) -> None:
    storage = tmp_path / "default.json"
    storage.write_text("{}", encoding="utf-8")
    profiles_file = _write_profiles_file(tmp_path, storage)
    notebooks = [
        _notebook("nb-newest", "Newest", "2026-01-04T00:00:00"),
        _notebook("nb-oldest", "Oldest", "2026-01-01T00:00:00"),
        _notebook("nb-next", "Next", "2026-01-02T00:00:00"),
        _notebook("nb-third", "Third", "2026-01-03T00:00:00"),
    ]
    fake_notebooks = FakeNotebooks(notebooks, limit=5)
    client = SimpleNamespace(notebooks=fake_notebooks, artifacts=FakeArtifacts())

    result = reclaim_notebooks(
        store=QueueStore(tmp_path / "queue"),
        options=NotebookReclaimOptions(
            profiles_file=profiles_file,
            profile_state_file=tmp_path / "profile_state.json",
            profiles=("default",),
            repo_root=tmp_path,
            target_free_slots=3,
            max_deletions=5,
            dry_run=True,
            use_lock=False,
        ),
        client_factory=_client_factory(client),
    )

    profile = result["profiles"][0]
    assert profile["status"] == "dry_run"
    assert profile["deleted_count"] == 2
    assert [item["id"] for item in profile["deleted_notebooks"]] == ["nb-oldest", "nb-next"]
    assert fake_notebooks.deleted_ids == []
    assert Path(result["report_path"]).exists()


def test_reclaim_notebooks_apply_skips_pending_and_missing_outputs(tmp_path: Path) -> None:
    storage = tmp_path / "default.json"
    storage.write_text("{}", encoding="utf-8")
    profiles_file = _write_profiles_file(tmp_path, storage)
    output_root = tmp_path / "notebooklm-podcast-auto" / "personlighedspsykologi" / "output"
    output_root.mkdir(parents=True)
    request_log = output_root / "missing.mp3.request.json"
    request_log.write_text(
        json.dumps({"notebook_id": "nb-missing-output", "output_path": str(output_root / "missing.mp3")}),
        encoding="utf-8",
    )
    notebooks = [
        _notebook("nb-pending", "Pending", "2026-01-01T00:00:00"),
        _notebook("nb-missing-output", "Missing Output", "2026-01-02T00:00:00"),
        _notebook("nb-delete-1", "Delete 1", "2026-01-03T00:00:00"),
        _notebook("nb-delete-2", "Delete 2", "2026-01-04T00:00:00"),
        _notebook("nb-keep", "Keep", "2026-01-05T00:00:00"),
    ]
    fake_notebooks = FakeNotebooks(notebooks, limit=5)
    client = SimpleNamespace(
        notebooks=fake_notebooks,
        artifacts=FakeArtifacts(pending_ids={"nb-pending"}),
    )

    result = reclaim_notebooks(
        store=QueueStore(tmp_path / "queue"),
        options=NotebookReclaimOptions(
            profiles_file=profiles_file,
            profile_state_file=tmp_path / "profile_state.json",
            profiles=("default",),
            repo_root=tmp_path,
            target_free_slots=2,
            max_deletions=4,
            dry_run=False,
            use_lock=False,
        ),
        client_factory=_client_factory(client),
    )

    profile = result["profiles"][0]
    assert profile["status"] == "reclaimed"
    assert fake_notebooks.deleted_ids == ["nb-delete-1", "nb-delete-2"]
    assert [item["id"] for item in profile["skipped_notebooks"]] == [
        "nb-pending",
        "nb-missing-output",
    ]
    assert profile["target_reached"] is True


def test_reclaim_notebooks_skips_when_headroom_exists(tmp_path: Path) -> None:
    storage = tmp_path / "default.json"
    storage.write_text("{}", encoding="utf-8")
    profiles_file = _write_profiles_file(tmp_path, storage)
    fake_notebooks = FakeNotebooks(
        [_notebook("nb-one", "One", "2026-01-01T00:00:00")],
        limit=5,
    )
    client = SimpleNamespace(notebooks=fake_notebooks, artifacts=FakeArtifacts())

    result = reclaim_notebooks(
        store=QueueStore(tmp_path / "queue"),
        options=NotebookReclaimOptions(
            profiles_file=profiles_file,
            profile_state_file=tmp_path / "profile_state.json",
            profiles=("default",),
            repo_root=tmp_path,
            target_free_slots=2,
            dry_run=False,
            use_lock=False,
        ),
        client_factory=_client_factory(client),
    )

    profile = result["profiles"][0]
    assert profile["status"] == "skipped_has_headroom"
    assert fake_notebooks.deleted_ids == []
