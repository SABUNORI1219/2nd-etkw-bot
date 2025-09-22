from PIL import Image, ImageDraw, ImageFont
import math
from io import BytesIO
import os
import logging
import random
import time
import textwrap

logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(project_root, "assets", "fonts", "NotoSansJP-Bold.ttf")

class RouletteRenderer:
    def __init__(self, size=260):
        self.size = size
        self.center = size // 2
        self.radius = self.center - 22
        try:
            self.base_font = ImageFont.truetype(FONT_PATH, 18)
        except IOError:
            logger.warning(f"フォントファイルが見つかりません: {FONT_PATH}")
            self.base_font = ImageFont.load_default()

    def _draw_static_elements(self, draw):
        # ポインタ（三角形）
        draw.polygon(
            [
                (self.center - 12, 12),
                (self.center + 12, 12),
                (self.center, 36),
            ],
            fill=(255, 0, 0),
        )
        # 中心円
        draw.ellipse(
            (
                self.center - 14,
                self.center - 14,
                self.center + 14,
                self.center + 14,
            ),
            fill=(0, 0, 0),
        )

    def _fit_text(self, text, font, max_width, max_height, max_lines=2):
        text = text.strip()
        orig_text = text

        for size in range(font.size, 9, -1):
            try:
                fnt = ImageFont.truetype(FONT_PATH, size)
            except IOError:
                fnt = ImageFont.load_default()
            wrapped = textwrap.wrap(text, width=max(1, int(max_width // (size * 0.7))))
            if len(wrapped) > max_lines:
                wrapped = wrapped[:max_lines]
            test_text = "\n".join(wrapped)
            bbox = fnt.getbbox(test_text)
            if bbox[2] <= max_width and bbox[3] <= max_height:
                return test_text, fnt

        for trunc in range(len(orig_text) - 1, 0, -1):
            truncated = orig_text[:trunc] + "..."
            try:
                fnt = ImageFont.truetype(FONT_PATH, 9)
            except IOError:
                fnt = ImageFont.load_default()
            wrapped = textwrap.wrap(truncated, width=max(1, int(max_width // (9 * 0.7))))
            wrapped = wrapped[:max_lines]
            test_text = "\n".join(wrapped)
            bbox = fnt.getbbox(test_text)
            if bbox[2] <= max_width and bbox[3] <= max_height:
                return test_text, fnt

        return "…", ImageFont.truetype(FONT_PATH, 9) if os.path.exists(FONT_PATH) else ImageFont.load_default()

    def _draw_wheel_sector(self, draw, start_angle, end_angle, color, text):
        draw.pieslice(
            [(22, 22), (self.size - 22, self.size - 22)],
            start=start_angle, end=end_angle, fill=color, outline="white", width=2
        )
        text_angle = math.radians(start_angle + (end_angle - start_angle) / 2)
        text_radius = self.radius * 0.65
        text_x = self.center + int(text_radius * math.cos(text_angle))
        text_y = self.center + int(text_radius * math.sin(text_angle))

        angle = abs(end_angle - start_angle)
        arc_length = 2 * math.pi * text_radius * (angle / 360)

        max_width = int(arc_length * 0.85)
        max_height = 32

        fit_text, fit_font = self._fit_text(
            text,
            self.base_font,
            max_width=max_width,
            max_height=max_height,
            max_lines=2
        )
        draw.multiline_text((text_x, text_y), fit_text, font=fit_font, fill="black", anchor="mm", spacing=0)

    def create_roulette_gif(self, candidates: list, winner_index: int) -> tuple[BytesIO, float]:
        logger.info(f"ルーレットGIF生成開始。候補: {candidates}, 当選者: {candidates[winner_index]}")
        num_candidates = len(candidates)
        if num_candidates == 0:
            return None, 0

        colors = [
            "royalblue", "salmon", "palegreen", "wheat",
            "lightcoral", "skyblue", "gold", "plum", "lime", "mediumorchid"
        ]

        seed = int(time.time() * 1000) ^ os.getpid() ^ random.randint(0, 999999)
        random.seed(seed)
        spin_count = random.randint(4, 6)
        spin_offset = random.uniform(-0.35, 0.35)

        angle_per_candidate = 360 / num_candidates
        stop_angle = 270 - (angle_per_candidate * winner_index) - (angle_per_candidate / 2) + spin_offset * angle_per_candidate
        total_rotation_degrees = 360 * spin_count + stop_angle

        num_frames = random.randint(90, 130)
        duration_ms = random.randint(26, 36)

        frames = []
        for i in range(num_frames):
            progress = i / (num_frames - 1)
            ease_out_progress = 1 - (1 - progress) ** 15
            current_rotation = total_rotation_degrees * ease_out_progress

            frame = Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(frame)
            for j, candidate in enumerate(candidates):
                start_angle = angle_per_candidate * j + current_rotation
                end_angle = angle_per_candidate * (j + 1) + current_rotation
                color = colors[j % len(colors)]
                self._draw_wheel_sector(draw, start_angle, end_angle, color, candidate)
            self._draw_static_elements(draw)
            frames.append(frame)
        
        last_frame = frames[-1]
        for _ in range(18):
            frames.append(last_frame)

        animation_duration = (num_frames * duration_ms) / 1000.0

        gif_buffer = BytesIO()
        import imageio
        imageio.mimsave(gif_buffer, frames, format="GIF", duration=(duration_ms/1000))
        gif_buffer.seek(0)
        return gif_buffer, animation_duration

    def create_result_image(self, candidates: list, winner_index: int) -> BytesIO:
        num_candidates = len(candidates)
        angle_per_candidate = 360 / num_candidates
        colors = [
            "royalblue", "salmon", "palegreen", "wheat",
            "lightcoral", "skyblue", "gold", "plum", "lime", "mediumorchid"
        ]

        stop_angle = 270 - (angle_per_candidate * winner_index) - (angle_per_candidate / 2)

        frame = Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)
        for j, candidate in enumerate(candidates):
            start_angle = angle_per_candidate * j + stop_angle
            end_angle = angle_per_candidate * (j + 1) + stop_angle
            color = colors[j % len(colors)]
            self._draw_wheel_sector(draw, start_angle, end_angle, color, candidate)
        self._draw_static_elements(draw)

        png_buffer = BytesIO()
        frame.save(png_buffer, format='PNG')
        png_buffer.seek(0)
        return png_buffer
