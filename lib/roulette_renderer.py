from PIL import Image, ImageDraw, ImageFont
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
    def __init__(self, size=400, polygon_color=(255, 0, 0), pointer_color=(0, 0, 0)):
        self.size = size
        self.center = size // 2
        self.radius = size // 2 - 20  # 少し余白を持たせる
        self.polygon_color = polygon_color
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
                (self.center - 15, 5),     # 左上の頂点
                (self.center + 15, 5),     # 右上の頂点
                (self.center, 40),      # 下の頂点（ルーレットを指す）
            ],
            fill=self.polygon_color,
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

    def _draw_wheel_sector(self, draw, start_angle, end_angle, color, text, frame_image):
        """ルーレットの扇形一つ分と、その中のテキストを描画する"""
        draw.pieslice(
            [(20, 20), (self.size - 20, self.size - 20)],
            start=start_angle, end=end_angle, fill=color, outline="white", width=2
        )
        
        # ▼▼▼【ここから追加】▼▼▼
        # テキストが扇形の幅に収まるようにフォントサイズを自動調整
        font = self.base_font
        # 扇形の描画可能なおおよその幅を計算
        sector_width = self.radius * 0.8 
        while font.getbbox(text)[2] > sector_width and font.size > 10:
            try:
                font = ImageFont.truetype(FONT_PATH, font.size - 2)
            except IOError:
                # フォントファイルが見つからない場合はデフォルトフォントでサイズ変更
                font = ImageFont.load_default(size=font.size - 2)
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲

        text_angle = math.radians(start_angle + (end_angle - start_angle) / 2)
        
        # テキストを画像として一度描き、それを回転させて貼り付ける
        text_image = Image.new('RGBA', font.getbbox(text)[2:], (255, 255, 255, 0))
        text_draw = ImageDraw.Draw(text_image)
        text_draw.text((0, 0), text, font=font, fill="black")
        
        # 文字が円の外側を向くように90度加算して回転
        rotated_text = text_image.rotate(math.degrees(-text_angle) + 90, expand=True)
        
        # 貼り付け位置を計算
        paste_radius = self.radius * 0.6
        paste_x = self.center + int(paste_radius * math.cos(text_angle)) - rotated_text.width // 2
        paste_y = self.center + int(paste_radius * math.sin(text_angle)) - rotated_text.height // 2

        frame_image.paste(rotated_text, (paste_x, paste_y), rotated_text)

    def create_roulette_gif(self, candidates: list, winner_index: int) -> BytesIO | None:
        """
        候補リストと当選者のインデックスを受け取り、GIFアニメーションを生成する。
        """
        logger.info(f"ルーレットGIF生成開始。候補: {candidates}, 当選者: {candidates[winner_index]}")
        num_candidates = len(candidates)
        if num_candidates == 0:
            return None

        angle_per_candidate = 360 / num_candidates
        colors = ["royalblue", "salmon", "palegreen", "wheat", "lightcoral", "skyblue", "gold", "plum"]
        
        frames = []
        total_rotation_degrees = 360 * 4  # 4回転する
        
        # 当選者のセクターが真上に来るための最終的な回転角度を計算
        stop_angle = 270 - (angle_per_candidate * winner_index) - (angle_per_candidate / 2)
        total_rotation_degrees += stop_angle

        num_frames = 120  # GIFのフレーム数（アニメーションの滑らかさ）
        duration_ms = 50 # 1フレームあたりの時間（ミリ秒）

        for i in range(num_frames):
            # アニメーションの進行度 (0.0 -> 1.0)
            progress = i / (num_frames - 1)
            # イージング関数（最初は速く、最後にゆっくり）
            ease_out_progress = 1 - (1 - progress) ** 4
            
            current_rotation = total_rotation_degrees * ease_out_progress

            # 新しいフレームを作成
            frame = Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(frame)

            # 各セクターを描画
            for j, candidate in enumerate(candidates):
                start_angle = angle_per_candidate * j + current_rotation
                end_angle = angle_per_candidate * (j + 1) + current_rotation
                color = colors[j % len(colors)]
                self._draw_wheel_sector(draw, start_angle, end_angle, color, candidate)

            # 固定要素（ポインタなど）を描画
            self._draw_static_elements(draw)
            frames.append(frame)

        last_frame = frames[-1]
        for _ in range(40):
            frames.append(last_frame)
        
        # アニメーションの合計時間を計算（秒単位）
        animation_duration = (num_frames * duration_ms) / 1000.0

        # フレームをGIFに変換
        gif_buffer = BytesIO()

        import imageio
        imageio.mimsave(gif_buffer, frames, format="GIF", duration=(duration_ms/1000))
        gif_buffer.seek(0)
        
        logger.info("✅ ルーレットGIF生成完了。")
        return gif_buffer, animation_duration
