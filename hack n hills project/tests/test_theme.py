"""Contrast checks for the declared light-theme colors, not a full WCAG audit."""
import pytest

from frontend.theme import ACCENT, CANVAS, INK, MUTED, PALETTE, SURFACE


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4 for channel in channels]
    return sum(weight * value for weight, value in zip((.2126, .7152, .0722), linear))


def contrast(first, second):
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + .05) / (dark + .05)


@pytest.mark.parametrize("foreground,background", [(INK, SURFACE), (INK, CANVAS), (MUTED, SURFACE), (MUTED, CANVAS), (SURFACE, ACCENT)])
def test_body_caption_and_primary_button_contrast(foreground, background):
    assert contrast(foreground, background) >= 4.5


@pytest.mark.parametrize("color", PALETTE)
def test_chart_marks_are_distinguishable_from_white_plot_surface(color):
    assert contrast(color, SURFACE) >= 3
