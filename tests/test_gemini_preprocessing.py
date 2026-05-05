from pathlib import Path
from unittest import mock

from notebooklm_queue import gemini_preprocessing as gemini


def test_parse_json_response_accepts_fenced_json():
    assert gemini.parse_json_response('```json\n{"ok": true}\n```') == {"ok": True}


def test_gemini_api_key_reads_local_secret_store(monkeypatch, tmp_path):
    secret_path = tmp_path / "secrets.json"
    secret_path.write_text('{"google": {"gemini": {"api_key": "secret-value"}}}', encoding="utf-8")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OSKAR_MEMORY_BRIDGE_SECRETS_FILE", str(secret_path))

    assert gemini.gemini_api_key() == "secret-value"


def test_non_retryable_zero_quota_error_is_summarized(tmp_path):
    fake_client = mock.Mock()
    fake_client.models.generate_content.side_effect = RuntimeError(
        "429 RESOURCE_EXHAUSTED free_tier_input_token_count, limit: 0"
    )
    fake_support = mock.Mock()
    fake_support.GenerateContentConfig.side_effect = lambda **kwargs: kwargs
    fake_support.Part.from_text.side_effect = lambda *, text: {"type": "text", "text": text}

    try:
        gemini.generate_json(
            backend=gemini.GeminiPreprocessingBackend(
                provider="gemini",
                client=fake_client,
                support=fake_support,
                model="gemini-test",
            ),
            system_instruction="system",
            user_prompt="user",
            retry_count=2,
        )
    except gemini.GeminiPreprocessingGenerationError as exc:
        assert "free-tier limit 0" in str(exc)
    else:
        raise AssertionError("expected GeminiPreprocessingGenerationError")
    fake_client.models.generate_content.assert_called_once()


def test_preflight_gemini_json_generation_uses_tiny_json_request():
    fake_client = mock.Mock()
    fake_client.models.generate_content.return_value = mock.Mock(text='{"ok": true}')
    fake_support = mock.Mock()
    fake_support.GenerateContentConfig.side_effect = lambda **kwargs: kwargs
    fake_support.ThinkingConfig.side_effect = lambda **kwargs: {"type": "thinking", **kwargs}
    fake_support.Part.from_text.side_effect = lambda *, text: {"type": "text", "text": text}

    payload = gemini.preflight_gemini_json_generation(
        backend=gemini.GeminiPreprocessingBackend(
            provider="gemini",
            client=fake_client,
            support=fake_support,
            model="gemini-test",
        )
    )

    assert payload == {"ok": True}
    call = fake_client.models.generate_content.call_args.kwargs
    assert call["config"]["max_output_tokens"] == 512
    assert call["config"]["response_mime_type"] == "application/json"
    assert call["config"]["thinking_config"] == {"type": "thinking", "thinking_level": "high"}
    assert call["config"]["response_json_schema"] == {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    assert "temperature" not in call["config"]
    assert call["contents"] == [{"type": "text", "text": 'Return exactly this JSON object: {"ok": true}'}]


def test_generate_json_passes_structured_output_schema_and_high_thinking():
    fake_client = mock.Mock()
    fake_client.models.generate_content.return_value = mock.Mock(text='{"analysis": {"ok": true}}')
    fake_support = mock.Mock()
    fake_support.GenerateContentConfig.side_effect = lambda **kwargs: kwargs
    fake_support.ThinkingConfig.side_effect = lambda **kwargs: {"type": "thinking", **kwargs}
    fake_support.Part.from_text.side_effect = lambda *, text: {"type": "text", "text": text}
    schema = {
        "type": "object",
        "properties": {"analysis": {"type": "object"}},
        "required": ["analysis"],
    }

    payload = gemini.generate_json(
        backend=gemini.GeminiPreprocessingBackend(
            provider="gemini",
            client=fake_client,
            support=fake_support,
            model="gemini-test",
        ),
        system_instruction="system",
        user_prompt="user",
        response_json_schema=schema,
    )

    assert payload == {"analysis": {"ok": True}}
    call = fake_client.models.generate_content.call_args.kwargs
    assert call["config"]["response_json_schema"] == schema
    assert call["config"]["thinking_config"] == {"type": "thinking", "thinking_level": "high"}
    assert "temperature" not in call["config"]


def test_generate_json_reports_response_diagnostics_for_truncated_json():
    fake_client = mock.Mock()
    response = mock.Mock(text="Here")
    response.prompt_feedback = None
    candidate = mock.Mock()
    candidate.finish_reason = "MAX_TOKENS"
    candidate.finish_message = ""
    response.candidates = [candidate]
    fake_client.models.generate_content.return_value = response
    fake_support = mock.Mock()
    fake_support.GenerateContentConfig.side_effect = lambda **kwargs: kwargs
    fake_support.Part.from_text.side_effect = lambda *, text: {"type": "text", "text": text}

    try:
        gemini.generate_json(
            backend=gemini.GeminiPreprocessingBackend(
                provider="gemini",
                client=fake_client,
                support=fake_support,
                model="gemini-test",
            ),
            system_instruction="system",
            user_prompt="user",
            retry_count=0,
        )
    except gemini.GeminiPreprocessingGenerationError as exc:
        assert "MAX_TOKENS" in str(exc)
    else:
        raise AssertionError("expected GeminiPreprocessingGenerationError")


def test_generate_json_uploads_pdf_and_deletes_upload(tmp_path):
    pdf_path = tmp_path / "Source File.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    fake_client = mock.Mock()
    uploaded = mock.Mock()
    uploaded.name = "files/source"
    uploaded.uri = "gs://gemini/source.pdf"
    uploaded.mime_type = "application/pdf"
    uploaded.state = None
    fake_client.files.upload.return_value = uploaded
    fake_client.models.generate_content.return_value = mock.Mock(text='{"analysis": {"ok": true}}')

    fake_support = mock.Mock()
    fake_support.GenerateContentConfig.side_effect = lambda **kwargs: kwargs
    fake_support.Part.from_text.side_effect = lambda *, text: {"type": "text", "text": text}
    fake_support.Part.from_uri.side_effect = (
        lambda *, file_uri, mime_type: {"type": "file", "file_uri": file_uri, "mime_type": mime_type}
    )

    payload = gemini.generate_json(
        backend=gemini.GeminiPreprocessingBackend(
            provider="gemini",
            client=fake_client,
            support=fake_support,
            model="gemini-test",
        ),
        system_instruction="system",
        user_prompt="user",
        source_paths=[pdf_path],
    )

    assert payload == {"analysis": {"ok": True}}
    fake_client.files.upload.assert_called_once()
    fake_client.files.delete.assert_called_once_with(name="files/source")
    call = fake_client.models.generate_content.call_args.kwargs
    assert call["model"] == "gemini-test"
    assert call["config"]["response_mime_type"] == "application/json"
    assert any(part.get("type") == "file" for part in call["contents"])
