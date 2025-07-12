from PIL import Image, ImageDraw, ImageFont
import imageio
import math
from io import BytesIO
import os
import logging

logger = logging.getLogger(__name__)

# このファイルの場所を基準に、プロジェクトのルートパスを取得
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# フォントファイルのパス（後でassetsフォルダに配置します）
FONT_PATH = os.path.join(project_root, "assets", "fonts", "NotoSansJP-Bold.ttf")


class RouletteRenderer:
    """
    ルーレットのGIFアニメーションを生成する専門家。
    """
    def __init__(self, size=480, pointer_color=(0, 0, 0)):
        self.size = size
        self.center = size // 2
        self.radius = size // 2 - 20  # 少し余白を持たせる
        self.pointer_color = pointer_color
        try:
            # フォントを読み込む。サイズは後で調整
            self.font = ImageFont.truetype(FONT_PATH, 30)
        except IOError:
            logger.warning(f"フォントファイルが見つかりません: {FONT_PATH}。デフォルトフォントを使用します。")
            self.font = ImageFont.load_default()

    def _draw_static_elements(self, draw):
        """ルーレットの動かない部分（外枠や中心の円、ポインタ）を描画する"""
        # ポインタ（三角形）を描画
        draw.polygon(
            [
                (self.center, self.size - 2),          # 下の頂点
                (self.center - 15, self.size - 35),    # 左上の頂点
                (self.center + 15, self.size - 35),    # 右上の頂点
            ],
            fill=self.pointer_color,
        )
        # 中心に円を描画
        draw.ellipse(
            (
                self.center - 20,
                self.center - 20,
                self.center + 20,
                self.center + 20,
            ),
            fill=self.pointer_color,
        )

    def _draw_wheel_sector(self, draw, start_angle, end_angle, color, text):
        """ルーレットの扇形一つ分と、その中のテキストを描画する"""
        # 扇形を描画
        draw.pieslice(
            [(20, 20), (self.size - 20, self.size - 20)],
            start=start_angle,
            end=end_angle,
            fill=color,
            outline="white",
            width=2,
        )

        # テキストを描画する角度と位置を計算
        text_angle = math.radians(start_angle + (end_angle - start_angle) / 2)
        text_x = self.center + int(self.radius * 0.6 * math.cos(text_angle))
        text_y = self.center + int(self.radius * 0.6 * math.sin(text_angle))

        # テキストを描画
        draw.text((text_x, text_y), text, font=self.font, fill="black", anchor="mm")

    def create_roulette_gif(self, candidates: list, winner_index: int, title: str) -> BytesIO | None:
        """
        候補リスト、当選者のインデックス、そしてタイトルを受け取り、GIFアニメーションを生成する。
        """
        logger.info(f"ルーレットGIF生成開始。タイトル: {title}, 候補: {candidates}, 当選者: {candidates[winner_index]}")
        num_candidates = len(candidates)
        if num_candidates == 0:
            return None

        angle_per_candidate = 360 / num_candidates
        colors = ["royalblue", "salmon", "palegreen", "wheat", "lightcoral", "skyblue", "gold", "plum"]
        
        frames = []
        total_rotation_degrees = 360 * 4
        
        stop_angle = 270 - (angle_per_candidate * winner_index) - (angle_per_candidate / 2)
        total_rotation_degrees += stop_angle

        num_frames = 120

        title_font = ImageFont.truetype(FONT_PATH, 40) # タイトル用フォント

        for i in range(num_frames):
            progress = i / (num_frames - 1)
            ease_out_progress = 1 - (1 - progress) ** 4
            current_rotation = total_rotation_degrees * ease_out_progress

            frame = Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(frame)

            # タイトルを描画
            if title:
                draw.text((self.center, 45), title, font=title_font, fill="white", anchor="ms")

            for j, candidate in enumerate(candidates):
                start_angle = angle_per_candidate * j + current_rotation
                end_angle = angle_per_candidate * (j + 1) + current_rotation
                color = colors[j % len(colors)]
                self._draw_wheel_sector(draw, start_angle, end_angle, color, candidate)

            self._draw_static_elements(draw)
            frames.append(frame)

        gif_buffer = BytesIO()
        imageio.mimsave(gif_buffer, frames, format="GIF", duration=50, loop=0)
        gif_buffer.seek(0)
        
        logger.info("✅ ルーレットGIF生成完了。")
        return gif_buffer
