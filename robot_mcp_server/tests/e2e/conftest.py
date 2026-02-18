import pytest
from playwright.sync_api import Playwright


@pytest.fixture(scope="session")
def browser_context_args():
    return {
        "viewport": {"width": 1280, "height": 720},
        "record_video_dir": "test-results/videos",
    }


@pytest.fixture
def dashboard_page(page):
    page.goto("http://localhost:5001/")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def mock_robot(page):
    """Mock robot API responses for isolated testing"""
    page.route(
        "**/api/command",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"status": "ok", "result": "mocked"}',
        ),
    )
    return page
