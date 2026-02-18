import pytest
from playwright.sync_api import Page, expect


def test_dashboard_loads(page: Page):
    page.goto("http://localhost:5001/")
    expect(page).to_have_title("ROVAC Dashboard")
    expect(page.locator(".control-panel")).to_be_visible()
    expect(page.locator(".dashboard-grid")).to_be_visible()


def test_header_elements_present(page: Page):
    page.goto("http://localhost:5001/")

    # Check header elements
    expect(page.locator(".header h1")).to_contain_text("ROVAC Robot Dashboard")
    expect(page.locator(".status-badge")).to_be_visible()


def test_main_cards_present(page: Page):
    page.goto("http://localhost:5001/")

    # Check all main cards are present
    expect(page.locator(".card").first).to_be_visible()
    expect(page.get_by_text("System Status")).to_be_visible()
    expect(page.get_by_text("Sensor Data")).to_be_visible()
    expect(page.get_by_text("Resource Usage")).to_be_visible()
    expect(page.get_by_text("Object Detection")).to_be_visible()


def test_visualization_sections_present(page: Page):
    page.goto("http://localhost:5001/")

    # Check visualization sections using role-based selectors
    expect(page.get_by_role("heading", name="Camera Feed")).to_be_visible()
    expect(page.get_by_role("heading", name="Map & Navigation")).to_be_visible()


def test_control_sections_present(page: Page):
    page.goto("http://localhost:5001/")

    # Check control sections
    expect(page.get_by_text("Manual Control")).to_be_visible()
    expect(page.get_by_text("Tool Execution")).to_be_visible()
    expect(page.get_by_text("Robot Control")).to_be_visible()
