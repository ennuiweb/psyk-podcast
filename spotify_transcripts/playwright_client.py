"""Playwright-backed Spotify transcript acquisition."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from .constants import (
    DEFAULT_TIMEOUT_MS,
    SPOTIFY_WEB_URL,
    STATUS_AUTH_REQUIRED,
    STATUS_DOWNLOADED,
    STATUS_MARKET_RESTRICTED,
    STATUS_NETWORK_ERROR,
    STATUS_NO_TRANSCRIPT,
    STATUS_PLAYBACK_REQUIRED,
    STATUS_SCHEMA_CHANGED,
    STATUS_UNKNOWN_FAILURE,
    TRANSCRIPT_URL_MARKERS,
)
from .models import AcquisitionResult
from .paths import get_browser_profile_dir, get_storage_state_path, get_home_dir, read_storage_state


def _ensure_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is not installed. Install transcript dependencies with:\n"
            "  .venv/bin/python -m pip install -r requirements-spotify-transcripts.txt\n"
            "  .venv/bin/playwright install chromium"
        ) from exc
    return sync_playwright


def _ensure_chromium_installed() -> None:
    try:
        result = subprocess.run(
            ["playwright", "install", "--dry-run", "chromium"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return
    if "will download" not in result.stdout.lower():
        return
    install = subprocess.run(
        ["playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        check=False,
    )
    if install.returncode != 0:
        raise SystemExit(
            "Unable to install Chromium automatically.\n"
            "Run: playwright install chromium"
        )


def _page_looks_logged_out(page: Any) -> bool:
    url = str(getattr(page, "url", "") or "").lower()
    if "login" in url or "accounts.spotify.com" in url:
        return True
    try:
        body_text = page.locator("body").inner_text(timeout=2_000).lower()
    except Exception:
        return False
    return "log in" in body_text or "log ind" in body_text


def _dismiss_cookie_banner(page: Any) -> None:
    selectors = [
        "button:has-text('Accept')",
        "button:has-text('Accepter')",
        "button[data-testid='onetrust-accept-btn-handler']",
    ]
    for selector in selectors:
        try:
            page.locator(selector).first.click(timeout=1_500)
            return
        except Exception:
            continue


def _click_first(page: Any, selectors: tuple[str, ...] | list[str]) -> bool:
    for selector in selectors:
        try:
            page.locator(selector).first.click(timeout=2_500)
            return True
        except Exception:
            continue
    return False


def _wait_for_result(page: Any, result_box: dict[str, AcquisitionResult], timeout_ms: int) -> AcquisitionResult | None:
    iterations = max(timeout_ms // 250, 1)
    for _ in range(iterations):
        result = result_box.get("result")
        if result is not None:
            return result
        try:
            page.wait_for_timeout(250)
        except Exception as exc:
            return AcquisitionResult(
                status=STATUS_UNKNOWN_FAILURE,
                payload=None,
                error=f"Playwright page closed before transcript capture completed: {exc}",
            )
    return None


def _classify_http_failure(status_code: int, body_text: str) -> tuple[str, str]:
    lowered = body_text.lower()
    if status_code in {401, 403}:
        if any(token in lowered for token in ("market", "region", "country", "available")):
            return STATUS_MARKET_RESTRICTED, "Spotify rejected transcript access for this market/account."
        return STATUS_AUTH_REQUIRED, "Spotify transcript request was rejected. Re-run login."
    if status_code == 404:
        return STATUS_NO_TRANSCRIPT, "Spotify returned 404 for the transcript endpoint."
    if status_code == 429:
        return STATUS_NETWORK_ERROR, "Spotify rate limited the transcript request."
    if status_code >= 500:
        return STATUS_NETWORK_ERROR, f"Spotify transcript endpoint returned HTTP {status_code}."
    return STATUS_UNKNOWN_FAILURE, f"Spotify transcript endpoint returned HTTP {status_code}."


def login_via_browser() -> Path:
    sync_playwright = _ensure_playwright()
    _ensure_chromium_installed()
    get_home_dir(create=True)
    storage_path = get_storage_state_path()
    profile_dir = get_browser_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile_dir.chmod(0o700)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--password-store=basic",
            ],
            ignore_default_args=["--enable-automation"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(SPOTIFY_WEB_URL, wait_until="load")

        print("Complete Spotify login in the browser window, then press ENTER here to save session state.")
        input("[Press ENTER when Spotify login is complete] ")

        context.storage_state(path=str(storage_path))
        storage_path.chmod(0o600)
        context.close()

    return storage_path


def get_auth_status() -> dict[str, Any]:
    storage_path = get_storage_state_path()
    profile_dir = get_browser_profile_dir()
    state = read_storage_state()
    cookies = state.get("cookies") if isinstance(state.get("cookies"), list) else []
    domains = sorted(
        {
            str(cookie.get("domain") or "").strip()
            for cookie in cookies
            if isinstance(cookie, dict) and str(cookie.get("domain") or "").strip()
        }
    )
    return {
        "storage_state_exists": storage_path.exists(),
        "browser_profile_exists": profile_dir.exists(),
        "cookie_count": len(cookies),
        "cookie_domains": domains,
    }


def download_episode_transcript(
    *,
    episode_url: str,
    episode_id: str,
    headless: bool = False,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> AcquisitionResult:
    if not get_browser_profile_dir().exists() and not get_storage_state_path().exists():
        return AcquisitionResult(
            status=STATUS_AUTH_REQUIRED,
            payload=None,
            error="Spotify auth state is missing. Run `python scripts/spotify_transcripts.py login` first.",
        )

    sync_playwright = _ensure_playwright()
    _ensure_chromium_installed()
    get_home_dir(create=True)
    storage_path = get_storage_state_path()
    profile_dir = get_browser_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile_dir.chmod(0o700)

    result_box: dict[str, AcquisitionResult] = {}

    logged_out_hint = False
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--password-store=basic",
            ],
            ignore_default_args=["--enable-automation"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(timeout_ms)

        def on_response(response: Any) -> None:
            url = str(response.url or "")
            if not any(marker in url for marker in TRANSCRIPT_URL_MARKERS):
                return
            if episode_id and episode_id not in url:
                return

            body_text = ""
            try:
                body_text = response.text()
            except Exception:
                body_text = ""

            if int(response.status) != 200:
                status, message = _classify_http_failure(int(response.status), body_text)
                result_box["result"] = AcquisitionResult(
                    status=status,
                    payload=None,
                    http_status=int(response.status),
                    error=message,
                    transcript_url=url,
                )
                return

            try:
                payload = json.loads(body_text)
            except json.JSONDecodeError:
                result_box["result"] = AcquisitionResult(
                    status=STATUS_SCHEMA_CHANGED,
                    payload=None,
                    http_status=int(response.status),
                    error="Spotify transcript response was not valid JSON.",
                    transcript_url=url,
                )
                return

            result_box["result"] = AcquisitionResult(
                status=STATUS_DOWNLOADED,
                payload=payload if isinstance(payload, dict) else {"payload": payload},
                http_status=int(response.status),
                transcript_url=url,
            )

        page.on("response", on_response)

        try:
            page.goto(episode_url, wait_until="domcontentloaded")
        except Exception as exc:
            context.close()
            return AcquisitionResult(
                status=STATUS_NETWORK_ERROR,
                payload=None,
                error=f"Unable to load episode page: {exc}",
            )

        result = _wait_for_result(page, result_box, min(timeout_ms, 4_000))
        if result is None:
            _dismiss_cookie_banner(page)
            _click_first(
                page,
                (
                    "[data-testid='transcript-tab']",
                    "a[data-testid='transcript-tab']",
                    "a:has-text('Transcript')",
                    "a:has-text('Transkript')",
                    "[role='tab']:has-text('Transcript')",
                    "[role='tab']:has-text('Transkript')",
                    "button:has-text('Transcript')",
                    "button:has-text('Transkript')",
                    "[data-testid='transcript-button']",
                    "[aria-label*='Transcript']",
                    "[aria-label*='Transkript']",
                ),
            )
            result = _wait_for_result(page, result_box, min(timeout_ms, 6_000))

        if result is None:
            _click_first(
                page,
                (
                    "button[data-testid='control-button-playpause']",
                    "button[aria-label*='Play']",
                    "button[aria-label*='Afspil']",
                    "[data-testid='play-button'] button",
                    "button:has-text('Play')",
                    "button:has-text('Afspil')",
                ),
            )
            result = _wait_for_result(page, result_box, min(timeout_ms, 8_000))

        if result is None:
            _click_first(
                page,
                (
                    "[data-testid='transcript-tab']",
                    "a[data-testid='transcript-tab']",
                    "a:has-text('Transcript')",
                    "a:has-text('Transkript')",
                    "[role='tab']:has-text('Transcript')",
                    "[role='tab']:has-text('Transkript')",
                    "button:has-text('Transcript')",
                    "button:has-text('Transkript')",
                    "[data-testid='transcript-button']",
                    "[aria-label*='Transcript']",
                    "[aria-label*='Transkript']",
                ),
            )
            result = _wait_for_result(page, result_box, timeout_ms)

        logged_out_hint = _page_looks_logged_out(page)
        try:
            context.storage_state(path=str(storage_path))
            storage_path.chmod(0o600)
        except Exception:
            pass
        finally:
            context.close()

    if result is not None:
        return result
    if logged_out_hint:
        return AcquisitionResult(
            status=STATUS_AUTH_REQUIRED,
            payload=None,
            error="Spotify session appears logged out. Re-run login.",
        )
    return AcquisitionResult(
        status=STATUS_PLAYBACK_REQUIRED,
        payload=None,
        error="No transcript response was observed after loading the episode, starting playback, and probing the transcript UI.",
    )
