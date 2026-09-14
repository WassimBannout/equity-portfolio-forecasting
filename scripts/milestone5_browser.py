"""Explicit Chrome smoke check against the disposable integration dashboard."""

import argparse
import json
from pathlib import Path


def main() -> None:
    # Playwright is an optional verification tool in an isolated /tmp environment.
    from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/usr/bin/google-chrome", headless=True
        )
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(args.url)
            page.get_by_text("Portfolio overview", exact=True).wait_for()
            page.wait_for_function(
                "document.querySelectorAll('.js-plotly-plot').length === 2"
            )
            assert page.get_by_text("Bad record", exact=False).count() == 0
            page.get_by_text("Portfolio overview", exact=True).evaluate(
                "el => el.scrollIntoView({block: 'start'})"
            )
            page.screenshot(path=str(args.output / "dashboard.png"), full_page=True)
            chart = page.locator(".js-plotly-plot").nth(1)
            chart.scroll_into_view_if_needed()
            labels = chart.locator(".xtick").all_text_contents()
            assert labels == ["2026-09-08"], labels
            point = chart.locator(".scatterlayer .point").first
            point.hover(force=True)
            page.wait_for_function(
                "document.querySelectorAll('.hoverlayer .hovertext').length > 0"
            )
            hover = chart.locator(".hoverlayer").text_content()
            assert hover is not None
            assert "Revision" in hover and "2026" in hover
            before = chart.evaluate("el => el.layout.yaxis.range")
            slider = page.get_by_role("slider").first
            slider.focus()
            slider.press("ArrowRight")
            page.wait_for_function(
                "previous => { const el = "
                "document.querySelectorAll('.js-plotly-plot')[1]; "
                "return el && el.layout && el.layout.yaxis.range[0] > previous; }",
                arg=before[0],
                timeout=15000,
            )
            chart = page.locator(".js-plotly-plot").nth(1)
            after = chart.evaluate("el => el.layout.yaxis.range")
            assert after[0] > before[0] and after[1] == before[1]
            chart.scroll_into_view_if_needed()
            page.screenshot(path=str(args.output / "chart-range.png"), full_page=True)
            # Exercise native drag-to-zoom on the rendered plot.
            area = chart.locator(".nsewdrag").bounding_box()
            assert area is not None
            page.mouse.move(
                area["x"] + area["width"] * 0.25, area["y"] + area["height"] * 0.25
            )
            page.mouse.down()
            page.mouse.move(
                area["x"] + area["width"] * 0.75,
                area["y"] + area["height"] * 0.75,
                steps=10,
            )
            page.mouse.up()
            zoomed = chart.evaluate("el => el._fullLayout.yaxis.range")
            assert zoomed[1] - zoomed[0] < after[1] - after[0]
            assert not errors, errors
            result = {
                "hover": hover,
                "session_axis_labels": labels,
                "range_before": before,
                "range_after_slider": after,
                "range_after_zoom": zoomed,
                "browser_errors": errors,
                "chrome": browser.version,
                "result": "PASS",
            }
            (args.output / "browser.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
            print(
                "PASS: Chrome chart hover, Streamlit range slider, "
                "Plotly zoom; no browser errors"
            )
        finally:
            browser.close()


if __name__ == "__main__":
    main()
