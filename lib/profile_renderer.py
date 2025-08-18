from PIL import Image, ImageDraw, ImageFilter
import random

def generate_profile_card(player_data, output_path="profile_card.png", size=(800, 1100)):
    # --- 1. Wanted風背景生成 ---
    base_color = (233, 223, 197)
    edge_color = (60, 40, 20)
    noise_level = 25000
    W, H = size
    img = Image.new("RGB", (W, H), base_color)
    draw = ImageDraw.Draw(img)

    # 周囲グラデーション（焦げ感）
    edge_width = 60
    for i in range(edge_width):
        color = (
            int(base_color[0] * (1 - i / edge_width) + edge_color[0] * (i / edge_width)),
            int(base_color[1] * (1 - i / edge_width) + edge_color[1] * (i / edge_width)),
            int(base_color[2] * (1 - i / edge_width) + edge_color[2] * (i / edge_width)),
        )
        bbox = [i, i, W-i, H-i]
        draw.ellipse(bbox, outline=color)

    # 紙質ノイズ
    for _ in range(noise_level):
        x = random.randint(0, W - 1)
        y = random.randint(0, H - 1)
        c = random.randint(200, 250)
        img.putpixel((x, y), (c, c, c))

    # ガウスぼかし
    img = img.filter(ImageFilter.GaussianBlur(1.1))

    # 外枠強調
    border_draw = ImageDraw.Draw(img)
    border_draw.rectangle([10, 10, W-10, H-10], outline=edge_color, width=4)

    # ここに今後プレイヤー情報・スキン描画など追加予定

    img.save(output_path)
    return output_path
