import pytest
from playwright.sync_api import Page, expect


def test_keyboard_navigation(page: Page):
    page.goto("http://localhost:5001/")

    # Tab through controls
    page.keyboard.press("Tab")
    focused_element = page.locator(":focus")
    expect(focused_element).to_be_visible()

    # Activate with Enter
    page.keyboard.press("Enter")


def test_screen_reader_labels(page: Page):
    page.goto("http://localhost:5001/")

    # Check that buttons have text content for screen readers
    emergency_stop_btn = page.get_by_role("button", name="Emergency Stop")
    expect(emergency_stop_btn).to_be_visible()
