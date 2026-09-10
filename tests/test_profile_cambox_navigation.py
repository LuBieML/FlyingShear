"""Regression coverage for retaining chart controls during page navigation."""

from types import SimpleNamespace
from unittest.mock import patch

import matplotlib.pyplot as plt

from src.profile_cambox_app import app
from src.profile_cambox_app.domain import ProfileConfig


def test_navigation_keeps_chart_pages_mounted_and_stops_playback():
    roots = []
    page = SimpleNamespace(
        window=SimpleNamespace(), services=[], add=roots.append,
        update=lambda: None,
    )
    with patch.dict(app.os.environ, {"PROFILE_CAMBOX_INPUT": ""}), patch.object(
        app, "load_config", return_value=ProfileConfig()
    ):
        app.main(page)
    try:
        shell = roots[0]
        header, body, _ = shell.controls
        generator_page, simulation_page = body.controls
        generator_nav, simulation_nav = header.content.controls[1].controls
        # Recover the view bound to its playback button, without constructing
        # another control tree or resetting any selected values.
        toolbar = simulation_page.content.content.controls[0]
        view = toolbar.controls[-1].on_click.__self__
        original_generator = generator_page.content
        original_simulator = simulation_page.content
        chart_container = original_generator.controls[1].content.controls[0].content.controls[1]
        original_chart = chart_container.content
        original_chart.figure.axes[0].plot([0, 1, 2], [10, 12, 11])
        view.index = 17
        view.radius.value = "63"

        for _ in range(3):
            simulation_nav.on_click(None)
            assert generator_page.opacity == 0
            assert generator_page.ignore_interactions and generator_page.disabled
            assert simulation_page.opacity == 1
            assert not simulation_page.ignore_interactions
            view.playing = True
            generation = view._play_generation
            generator_nav.on_click(None)
            assert not view.playing
            assert view._play_generation > generation
            assert generator_page.opacity == 1
            assert not generator_page.disabled
            assert simulation_page.opacity == 0
            assert simulation_page.ignore_interactions and simulation_page.disabled
            assert body.controls == [generator_page, simulation_page]
            assert generator_page.content is original_generator
            assert simulation_page.content is original_simulator
            assert chart_container.content is original_chart
            assert list(original_chart.figure.axes[0].lines[-1].get_ydata()) == [10, 12, 11]
            assert view.index == 17
            assert view.radius.value == "63"
    finally:
        plt.close("all")
