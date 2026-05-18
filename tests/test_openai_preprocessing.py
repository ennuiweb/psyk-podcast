import importlib.util
import subprocess
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MODULE_PATH = REPO_ROOT / "notebooklm_queue/openai_preprocessing.py"
SPEC = importlib.util.spec_from_file_location("openai_preprocessing", MODULE_PATH)
assert SPEC and SPEC.loader
openai_preprocessing = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = openai_preprocessing
SPEC.loader.exec_module(openai_preprocessing)


def test_pdf_text_extraction_falls_back_to_ocr(monkeypatch, tmp_path):
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    class _FakePage:
        def extract_text(self):
            return ""

    class _FakeReader:
        def __init__(self, _path):
            self.pages = [_FakePage(), _FakePage()]

    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=_FakeReader))
    monkeypatch.setattr(openai_preprocessing.shutil, "which", lambda name: "/usr/local/bin/ocrmypdf" if name == "ocrmypdf" else None)

    def fake_run(args, capture_output, text, check, timeout):
        sidecar_path = Path(args[3])
        sidecar_path.write_text("OCR text from sidecar", encoding="utf-8")
        assert timeout == openai_preprocessing.DEFAULT_OPENAI_OCR_TIMEOUT_SECONDS
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(openai_preprocessing.subprocess, "run", fake_run)

    extracted = openai_preprocessing._read_source_text(pdf_path)

    assert extracted == "OCR text from sidecar"


def test_generate_json_retries_timeout_and_passes_request_timeout(monkeypatch):
    calls: list[dict[str, object]] = []

    class _APITimeoutError(Exception):
        pass

    class _FakeResponses:
        def __init__(self):
            self.count = 0

        def create(self, **kwargs):
            self.count += 1
            calls.append(kwargs)
            if self.count == 1:
                raise _APITimeoutError()
            return types.SimpleNamespace(output_text='{"ok": true}')

    backend = openai_preprocessing.OpenAIPreprocessingBackend(
        provider="openai",
        client=types.SimpleNamespace(responses=_FakeResponses()),
        model="gpt-5.5",
    )
    sleeps: list[int] = []
    progress: list[str] = []
    monkeypatch.setattr(openai_preprocessing.time, "sleep", lambda seconds: sleeps.append(seconds))

    payload = openai_preprocessing.generate_json(
        backend=backend,
        system_instruction="Return JSON.",
        user_prompt='Return {"ok": true}.',
        progress_logger=progress.append,
    )

    assert payload == {"ok": True}
    assert len(calls) == 2
    assert calls[0]["timeout"] == openai_preprocessing.DEFAULT_OPENAI_REQUEST_TIMEOUT_SECONDS
    assert sleeps == [openai_preprocessing.OPENAI_TRANSIENT_RETRY_DELAYS_SECONDS[0]]
    assert any("attempt 1/4" in message for message in progress)
    assert any("retrying in 5s" in message for message in progress)
    assert any("succeeded on attempt 2/4" in message for message in progress)
