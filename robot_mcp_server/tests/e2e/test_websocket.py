import pytest
from playwright.sync_api import Page, expect


def test_websocket_connection_status(page: Page):
    page.goto("http://localhost:5001/")

    # Check connection status elements
    expect(page.locator("#connection-status-dot")).to_be_visible()
    expect(page.locator("#connection-status-text")).to_be_visible()


def test_sensor_data_display(page: Page):
    page.goto("http://localhost:5001/")

    # Check sensor data elements are present
    expect(page.locator("#lidar-points")).to_be_visible()
    expect(page.locator("#distance")).to_be_visible()
    expect(page.locator("#battery")).to_be_visible()


def test_resource_usage_bars(page: Page):
    page.goto("http://localhost:5001/")

    # Check resource usage elements
    expect(page.locator("#cpu-bar")).to_be_visible()
    expect(page.locator("#memory-bar")).to_be_visible()
    expect(page.locator("#battery-bar")).to_be_visible()

    # Check percentage displays
    expect(page.locator("#cpu-percent")).to_be_visible()
    expect(page.locator("#memory-percent")).to_be_visible()
    expect(page.locator("#battery-percent")).to_be_visible()


def test_system_status_indicators(page: Page):
    page.goto("http://localhost:5001/")

    # Check system status indicators
    expect(page.locator("#health-status")).to_be_visible()
    expect(page.locator("#sensor-status")).to_be_visible()
    expect(page.locator("#obstacle-status")).to_be_visible()
    expect(page.locator("#navigation-status")).to_be_visible()
    expect(page.locator("#communication-status")).to_be_visible()


def test_log_console_present(page: Page):
    page.goto("http://localhost:5001/")

    # Check log console is present
    expect(page.locator("#log-console")).to_be_visible()
    # Check that at least one log entry is visible
    expect(page.locator(".log-entry").first).to_be_visible()
