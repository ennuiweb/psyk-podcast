import importlib.util
import unittest
from pathlib import Path
from unittest import mock


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "podcast-tools" / "gdrive_podcast_feed.py"
    spec = importlib.util.spec_from_file_location("gdrive_podcast_feed", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeHttpError(Exception):
    def __init__(self, status: int, content: bytes):
        super().__init__(f"http {status}")
        self.resp = type("Resp", (), {"status": status})()
        self.content = content


class _FakeRequest:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def execute(self):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class GDriveRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_is_retryable_http_error_by_status(self):
        with mock.patch.object(self.mod, "HttpError", _FakeHttpError):
            self.assertTrue(self.mod._is_retryable_http_error(_FakeHttpError(500, b"{}")))
            self.assertTrue(self.mod._is_retryable_http_error(_FakeHttpError(429, b"{}")))
            self.assertFalse(self.mod._is_retryable_http_error(_FakeHttpError(404, b"{}")))

    def test_is_retryable_http_error_by_reason(self):
        payload = b'{"error":{"errors":[{"reason":"internalError"}]}}'
        with mock.patch.object(self.mod, "HttpError", _FakeHttpError):
            self.assertTrue(self.mod._is_retryable_http_error(_FakeHttpError(400, payload)))

    def test_execute_with_retry_retries_then_succeeds(self):
        transient = _FakeHttpError(500, b'{"error":{"errors":[{"reason":"internalError"}]}}')
        request = _FakeRequest([transient, transient, {"ok": True}])
        with (
            mock.patch.object(self.mod, "HttpError", _FakeHttpError),
            mock.patch.object(self.mod.time, "sleep", return_value=None),
            mock.patch.object(self.mod.random, "uniform", return_value=0.0),
        ):
            result = self.mod._execute_with_retry(request)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(request.calls, 3)

    def test_execute_with_retry_does_not_retry_non_retryable_error(self):
        fatal = _FakeHttpError(400, b'{"error":{"errors":[{"reason":"invalid"}]}}')
        request = _FakeRequest([fatal])
        with (
            mock.patch.object(self.mod, "HttpError", _FakeHttpError),
            mock.patch.object(self.mod.time, "sleep", return_value=None),
        ):
            with self.assertRaises(_FakeHttpError):
                self.mod._execute_with_retry(request)
        self.assertEqual(request.calls, 1)


if __name__ == "__main__":
    unittest.main()
