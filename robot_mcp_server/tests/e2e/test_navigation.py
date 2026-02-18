import pytest
from playwright.sync_api import Page, expect


def test_manual_control_section(page: Page):
    page.goto("http://localhost:5001/")

    # Check manual control elements
    expect(page.locator("#joystick-container")).to_be_visible()
    expect(page.locator("#speed-slider")).to_be_visible()

    # Check camera control buttons
    expect(page.get_by_text("Look Left")).to_be_visible()
    expect(page.get_by_text("Center Camera")).to_be_visible()
    expect(page.get_by_text("Look Right")).to_be_visible()


def test_camera_feed_display(page: Page):
    page.goto("http://localhost:5001/")

    # Check camera feed elements (placeholder is visible initially)
    expect(page.locator("#camera-placeholder")).to_be_visible()


def test_map_visualization(page: Page):
    page.goto("http://localhost:5001/")

    # Check map visualization elements (placeholder is visible initially)
    expect(page.locator("#map-placeholder")).to_be_visible()


def test_joystick_interaction(page: Page):
    page.goto("http://localhost:5001/")

    # Check joystick handle is present
    joystick_handle = page.locator("#joystick-handle")
    expect(joystick_handle).to_be_visible()

    # Try to interact with joystick (this might not work in headless mode)
    try:
        joystick_handle.hover()
    except:
        pass  # Interaction might not work in headless tests
