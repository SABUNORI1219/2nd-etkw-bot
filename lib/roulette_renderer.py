from PIL import Image, ImageDraw, ImageFont
import math
from io import BytesIO
import os
import logging
import random
import time

logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(project_root, "assets", "fonts", "NotoSansJP-Bold.ttf")


class RouletteRenderer:
    """
    ルーレット画像・GIF生成担当
    - 軽量化
    - ランダム性強化
    - 静止画生成対応
    """
    def __init__(self, size=240):
        self.size = size
        self.center = size // 2
        self.radius = size // 2 - 18
        try:
            self.font = ImageFont.truetype(FONT_PATH, 18)
        except IOError:
            logger.warning(f"フォントファイルが見つかりません: {FONT_PATH}")
            self.font = ImageFont.load_default()

    def _draw_static_elements(self, draw):
        # ポインタ（三角形）
        draw.polygon(
            [
                (self.center - 12, 5),
                (self.center + 12, 5),
                (self.center, 32),
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

    def _draw_wheel_sector(self, draw, start_angle, end_angle, color, text):
        draw.pieslice(
            [(18, 18), (self.size - 18, self.size - 18)],
            start=start_angle, end=end_angle, fill=color, outline="white", width=2
        )
        font = self.font
        sector_width = self.radius * 0.8
        while font.getbbox(text)[2] > sector_width and font.size > 10:
            try:
                font = ImageFont.truetype(FONT_PATH, font.size - 2)
            except IOError:
                font = ImageFont.load_default(size=font.size - 2)

        text_angle = math.radians(start_angle + (end_angle - start_angle) / 2)
        text_radius = self.radius * 0.6
        text_x = self.center + int(text_radius * math.cos(text_angle))
        text_y = self.center + int(text_radius * math.sin(text_angle))
        draw.text((text_x, text_y), text, font=font, fill="black", anchor="mm")

    def create_roulette_gif(self, candidates: list, winner_index: int) -> tuple[BytesIO, float]:
        """
        軽量GIF生成・ランダム性強化
        """
        logger.info(f"ルーレットGIF生成開始。候補: {candidates}, 当選者: {candidates[winner_index]}")
        num_candidates = len(candidates)
        if num_candidates == 0:
            return None, 0

        colors = ["royalblue", "salmon", "palegreen", "wheat", "lightcoral", "skyblue", "gold", "plum"]

        # --- ランダム性強化 ---
        # サーバー時刻, プロセスID, 乱数, ユーザーIDなどをseedに
        seed = int(time.time() * 1000) ^ os.getpid() ^ random.randint(0, 999999)
        random.seed(seed)
        spin_count = random.randint(3, 8)  # 3～8回転
        spin_offset = random.uniform(-0.3, 0.3)  # 偏りを減らす微調整

        angle_per_candidate = 360 / num_candidates
        stop_angle = 270 - (angle_per_candidate * winner_index) - (angle_per_candidate / 2) + spin_offset * angle_per_candidate
        total_rotation_degrees = 360 * spin_count + stop_angle

        num_frames = random.randint(40, 60)
        duration_ms = random.randint(40, 70)  # 1フレームあたりの時間

        frames = []
        for i in range(num_frames):
            progress = i / (num_frames - 1)
            ease_out_progress = 1 - (1 - progress) ** 4
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
        for _ in range(15):
            frames.append(last_frame)

        animation_duration = (num_frames * duration_ms) / 1000.0

        gif_buffer = BytesIO()
        import imageio
        imageio.mimsave(gif_buffer, frames, format="GIF", duration=(duration_ms/1000))
        gif_buffer.seek(0)
        logger.info("✅ ルーレットGIF生成完了。")
        return gif_buffer, animation_duration

    def create_result_image(self, candidates: list, winner_index: int) -> BytesIO:
        """
        回転後の静止画像（PNGで返却）
        """
        num_candidates = len(candidates)
        angle_per_candidate = 360 / num_candidates
        colors = ["royalblue", "salmon", "palegreen", "wheat", "lightcoral", "skyblue", "gold", "plum"]

        # 当選者のセクターが真上に来る
        stop_angle = 270 - (angle_per_candidate * winner_index) - (angle_per_candidate / 2)

        frame = Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)
        for j, candidate in enumerate(candidates):
            start_angle = angle_per_candidate * j + stop_angle
            end_angle = angle_per_candidate * (j + 1) + stop_angle
            color = colors[j % len(colors)]
            self._draw_wheel_sector(draw, start_angle, end_angle, color, candidate)
        self._draw_static_elements(draw)

        # PNG出力
        png_buffer = BytesIO()
        frame.save(png_buffer, format='PNG')
        png_buffer.seek(0)
        return png_buffer
