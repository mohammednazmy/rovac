import pytest
from playwright.sync_api import Page, expect


def test_emergency_stop_button(page: Page):
    page.goto("http://localhost:5001/")

    # Click emergency stop button
    page.click("button:has-text('Emergency Stop')")

    # Verify modal appears
    expect(page.locator("#emergency-stop-modal")).to_be_visible()


def test_start_systems_button(page: Page):
    page.goto("http://localhost:5001/")

    # Click start systems button
    page.click("button:has-text('Start Systems')")

    # Verify command was logged (check first matching element)
    expect(page.locator(".log-entry").first).to_be_visible()


def test_speed_slider(page: Page):
    page.goto("http://localhost:5001/")

    # Adjust speed slider
    page.locator("#speed-slider").fill("0.8")

    # Verify speed value updates
    expect(page.locator("#speed-value")).to_have_text("0.8")

    # Verify log entry (check last log entry contains speed info)
    page.wait_for_timeout(1000)  # Wait for log to update
    expect(page.locator(".log-entry").last).to_contain_text("0.8x")


def test_tool_execution(page: Page):
    page.goto("http://localhost:5001/")

    # Enter command in tool execution input
    page.fill("#command-input", "get_distance")

    # Click execute button
    page.click("button:has-text('Execute')")

    # Verify command was logged (check last log entry contains tool info)
    page.wait_for_timeout(1000)  # Wait for log to update
    expect(page.locator(".log-entry").last).to_contain_text("get_distance")
