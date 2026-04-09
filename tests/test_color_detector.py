"""Tests for the color_detector module."""

from PIL import Image, ImageDraw

from scan2pdf.color_detector import (
    BLACK,
    _is_colored_pixel,
    _is_foreground_pixel,
    _rgb_to_hsv,
    detect_paragraph_color,
    detect_word_color,
    rgb_to_hex,
)


class TestRgbToHsv:
    """Tests for RGB to HSV conversion."""

    def test_pure_red(self):
        h, s, v = _rgb_to_hsv(255, 0, 0)
        assert h == 0
        assert s == 255
        assert v == 255

    def test_pure_green(self):
        h, s, v = _rgb_to_hsv(0, 255, 0)
        assert h == 120
        assert s == 255
        assert v == 255

    def test_pure_blue(self):
        h, s, v = _rgb_to_hsv(0, 0, 255)
        assert h == 240
        assert s == 255
        assert v == 255

    def test_black(self):
        h, s, v = _rgb_to_hsv(0, 0, 0)
        assert h == 0
        assert s == 0
        assert v == 0

    def test_white(self):
        h, s, v = _rgb_to_hsv(255, 255, 255)
        assert h == 0
        assert s == 0
        assert v == 255

    def test_gray(self):
        h, s, v = _rgb_to_hsv(128, 128, 128)
        assert s == 0  # No saturation for gray


class TestIsForegroundPixel:
    """Tests for foreground pixel detection."""

    def test_black_is_foreground(self):
        assert _is_foreground_pixel(0, 0, 0) is True

    def test_dark_gray_is_foreground(self):
        assert _is_foreground_pixel(50, 50, 50) is True

    def test_white_is_not_foreground(self):
        assert _is_foreground_pixel(255, 255, 255) is False

    def test_light_gray_is_not_foreground(self):
        assert _is_foreground_pixel(200, 200, 200) is False

    def test_dark_red_is_foreground(self):
        assert _is_foreground_pixel(150, 0, 0) is True

    def test_dark_blue_is_foreground(self):
        assert _is_foreground_pixel(0, 0, 150) is True

    def test_bright_saturated_red_is_foreground(self):
        """Bright but vivid red should be foreground (colored text)."""
        assert _is_foreground_pixel(220, 30, 30) is True

    def test_bright_saturated_blue_is_foreground(self):
        """Bright but vivid blue should be foreground (colored text)."""
        assert _is_foreground_pixel(50, 80, 210) is True

    def test_bright_saturated_green_is_foreground(self):
        """Bright saturated green should be foreground."""
        assert _is_foreground_pixel(30, 200, 30) is True

    def test_pale_unsaturated_is_not_foreground(self):
        """Very pale / nearly white is background even if slightly tinted."""
        assert _is_foreground_pixel(240, 230, 230) is False


class TestIsColoredPixel:
    """Tests for colored pixel detection (distinguishing from scan noise)."""

    def test_pure_black_not_colored(self):
        """Pure black has no saturation."""
        h, s, v = _rgb_to_hsv(0, 0, 0)
        assert _is_colored_pixel(h, s, v) is False

    def test_near_black_not_colored(self):
        """Near-black with slight color cast (scan noise) should not be colored."""
        # Simulating scan noise: very dark with slight reddish tint
        h, s, v = _rgb_to_hsv(20, 10, 10)
        assert _is_colored_pixel(h, s, v) is False

    def test_dark_gray_not_colored(self):
        """Dark gray (common scan artifact) should not be colored."""
        h, s, v = _rgb_to_hsv(40, 40, 40)
        assert _is_colored_pixel(h, s, v) is False

    def test_vivid_red_is_colored(self):
        """Clearly red text should be detected as colored."""
        h, s, v = _rgb_to_hsv(200, 30, 30)
        assert _is_colored_pixel(h, s, v) is True

    def test_vivid_blue_is_colored(self):
        """Clearly blue text should be detected as colored."""
        h, s, v = _rgb_to_hsv(30, 30, 200)
        assert _is_colored_pixel(h, s, v) is True

    def test_vivid_green_is_colored(self):
        """Clearly green text should be detected as colored."""
        h, s, v = _rgb_to_hsv(30, 150, 30)
        assert _is_colored_pixel(h, s, v) is True

    def test_very_dark_colored_not_detected(self):
        """Very dark colored pixel (V < MIN_COLOR_VALUE) treated as black."""
        # Dark red that's almost black
        h, s, v = _rgb_to_hsv(15, 0, 0)
        assert _is_colored_pixel(h, s, v) is False


class TestDetectWordColor:
    """Tests for word-level color detection from images."""

    def _make_text_image(self, text_color, bg_color=(255, 255, 255), size=(100, 30)):
        """Create a simple image with a colored rectangle simulating text."""
        img = Image.new("RGB", size, bg_color)
        draw = ImageDraw.Draw(img)
        # Draw a filled rectangle in the text area (simulating text pixels)
        margin = 5
        draw.rectangle(
            [margin, margin, size[0] - margin, size[1] - margin],
            fill=text_color,
        )
        return img

    def test_black_text(self):
        """Black text should return BLACK."""
        img = self._make_text_image((0, 0, 0))
        color = detect_word_color(img, (0, 0, 100, 30), sample_step=1)
        assert color == BLACK

    def test_red_text(self):
        """Red text should be detected as colored."""
        img = self._make_text_image((200, 30, 30))
        color = detect_word_color(img, (0, 0, 100, 30), sample_step=1)
        assert color is not None
        assert color != BLACK
        # Should be reddish
        assert color[0] > 100  # R channel dominant

    def test_blue_text(self):
        """Blue text should be detected as colored."""
        img = self._make_text_image((30, 30, 200))
        color = detect_word_color(img, (0, 0, 100, 30), sample_step=1)
        assert color is not None
        assert color != BLACK
        # Should be bluish
        assert color[2] > 100  # B channel dominant

    def test_near_black_scan_noise(self):
        """Near-black with slight color cast should be treated as black."""
        # Simulating scan noise: very dark with slight variation
        img = self._make_text_image((15, 10, 12))
        color = detect_word_color(img, (0, 0, 100, 30), sample_step=1)
        assert color == BLACK

    def test_empty_bbox(self):
        """Empty or invalid bbox should return None."""
        img = Image.new("RGB", (100, 30), (255, 255, 255))
        color = detect_word_color(img, (50, 50, 50, 50), sample_step=1)
        assert color is None

    def test_all_white_bbox(self):
        """All-white bbox (no foreground) should return None."""
        img = Image.new("RGB", (100, 30), (255, 255, 255))
        color = detect_word_color(img, (0, 0, 100, 30), sample_step=1)
        assert color is None

    def test_bbox_clamped_to_image(self):
        """Bbox extending beyond image should be clamped."""
        img = self._make_text_image((200, 30, 30), size=(50, 20))
        # Bbox larger than image
        color = detect_word_color(img, (0, 0, 200, 100), sample_step=1)
        assert color is not None


class TestDetectParagraphColor:
    """Tests for paragraph-level color aggregation."""

    def test_all_black_words(self):
        """All black words should result in black paragraph."""
        colors = [BLACK, BLACK, BLACK, BLACK]
        assert detect_paragraph_color(colors) == BLACK

    def test_all_red_words(self):
        """All red words should result in red paragraph."""
        red = (200, 30, 30)
        colors = [red, red, red, red]
        result = detect_paragraph_color(colors)
        assert result != BLACK
        assert result[0] > 100  # R dominant

    def test_mostly_black_with_one_colored(self):
        """One colored word among many black should stay black."""
        colors = [BLACK, BLACK, BLACK, BLACK, (200, 30, 30), BLACK, BLACK, BLACK, BLACK, BLACK]
        result = detect_paragraph_color(colors)
        assert result == BLACK

    def test_mostly_colored(self):
        """Majority colored words should result in colored paragraph."""
        red = (200, 30, 30)
        colors = [red, red, red, BLACK]
        result = detect_paragraph_color(colors)
        assert result != BLACK

    def test_empty_list(self):
        """Empty word list should return BLACK."""
        assert detect_paragraph_color([]) == BLACK

    def test_all_none(self):
        """All None values should return BLACK."""
        assert detect_paragraph_color([None, None, None]) == BLACK

    def test_mixed_colors_dominant_wins(self):
        """When multiple colors present, the dominant hue group wins."""
        red = (200, 30, 30)
        blue = (30, 30, 200)
        colors = [red, red, red, blue]
        result = detect_paragraph_color(colors)
        # Red is dominant
        assert result[0] > result[2]


class TestRgbToHex:
    """Tests for RGB to hex conversion."""

    def test_black(self):
        assert rgb_to_hex((0, 0, 0)) == "#000000"

    def test_white(self):
        assert rgb_to_hex((255, 255, 255)) == "#FFFFFF"

    def test_red(self):
        assert rgb_to_hex((255, 0, 0)) == "#FF0000"

    def test_arbitrary(self):
        assert rgb_to_hex((18, 52, 86)) == "#123456"


class TestScanNoiseRobustness:
    """Integration tests verifying scan noise doesn't cause false color detection."""

    def _make_noisy_black_text_image(self, size=(200, 40)):
        """
        Create an image simulating black text with scan noise.

        Pixels vary slightly from pure black, simulating real scanner output.
        """
        img = Image.new("RGB", size, (245, 242, 238))  # Slightly off-white background
        draw = ImageDraw.Draw(img)

        # Draw "text" with slight color variations (scan noise)
        import random

        random.seed(42)
        for y in range(8, 32):
            for x in range(10, 190):
                if random.random() < 0.6:  # 60% of pixels are "text"
                    # Add noise: slight color cast
                    r = random.randint(0, 25)
                    g = random.randint(0, 20)
                    b = random.randint(0, 22)
                    draw.point((x, y), fill=(r, g, b))
        return img

    def test_noisy_black_detected_as_black(self):
        """Black text with scan noise should still be detected as black."""
        img = self._make_noisy_black_text_image()
        color = detect_word_color(img, (10, 8, 190, 32), sample_step=1)
        assert color == BLACK

    def _make_genuine_colored_text_image(self, text_color, size=(200, 40)):
        """Create an image with genuinely colored text."""
        img = Image.new("RGB", size, (250, 250, 250))
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 8, 190, 32], fill=text_color)
        return img

    def test_genuine_red_detected(self):
        """Genuinely red text should be detected as colored."""
        img = self._make_genuine_colored_text_image((180, 20, 20))
        color = detect_word_color(img, (10, 8, 190, 32), sample_step=1)
        assert color is not None
        assert color != BLACK

    def test_genuine_blue_detected(self):
        """Genuinely blue text should be detected as colored."""
        img = self._make_genuine_colored_text_image((20, 20, 180))
        color = detect_word_color(img, (10, 8, 190, 32), sample_step=1)
        assert color is not None
        assert color != BLACK

    def test_genuine_dark_green_detected(self):
        """Dark green text should be detected as colored."""
        img = self._make_genuine_colored_text_image((20, 120, 20))
        color = detect_word_color(img, (10, 8, 190, 32), sample_step=1)
        assert color is not None
        assert color != BLACK

    def test_bright_red_text_detected(self):
        """Bright red text (high luminance but saturated) should be detected."""
        img = self._make_genuine_colored_text_image((220, 40, 40))
        color = detect_word_color(img, (10, 8, 190, 32), sample_step=1)
        assert color is not None
        assert color != BLACK
        assert color[0] > 150  # R dominant

    def test_bright_blue_text_detected(self):
        """Bright blue text should be detected as colored."""
        img = self._make_genuine_colored_text_image((40, 60, 220))
        color = detect_word_color(img, (10, 8, 190, 32), sample_step=1)
        assert color is not None
        assert color != BLACK
        assert color[2] > 150  # B dominant

    def test_medium_green_text_detected(self):
        """Medium green text should be detected as colored."""
        img = self._make_genuine_colored_text_image((30, 180, 30))
        color = detect_word_color(img, (10, 8, 190, 32), sample_step=1)
        assert color is not None
        assert color != BLACK
        assert color[1] > 100  # G dominant

    def test_orange_text_detected(self):
        """Orange text (high luminance, saturated) should be detected."""
        img = self._make_genuine_colored_text_image((220, 130, 20))
        color = detect_word_color(img, (10, 8, 190, 32), sample_step=1)
        assert color is not None
        assert color != BLACK
