from PIL import Image, ImageDraw, ImageFilter
import random
import numpy as np

def generate_profile_card(player_data, output_path="profile_card.png", size=(800, 1100)):
    # 📜絵文字風の色設定
    base_color = (247, 231, 180)      # メインの紙色
    edge_color = (227, 201, 133)      # 端のベージュ
    border_color = (193, 164, 108)    # 外枠・破れ部分

    W, H = size
    img = Image.new("RGBA", (W, H), base_color)
    draw = ImageDraw.Draw(img)

    # --- 1. 端のベージュのグラデーション ---
    for side in range(4):
        if side == 0:  # 上
            for x in range(W):
                burn = random.randint(16, 36)
                for y in range(burn):
                    alpha = random.randint(120, 200)
                    color = (
                        int(base_color[0] * 0.7 + edge_color[0] * 0.3),
                        int(base_color[1] * 0.7 + edge_color[1] * 0.3),
                        int(base_color[2] * 0.7 + edge_color[2] * 0.3),
                        alpha
                    )
                    img.putpixel((x, y), color)
        if side == 1:  # 下
            for x in range(W):
                burn = random.randint(16, 36)
                for y in range(H-1, H-burn, -1):
                    alpha = random.randint(120, 200)
                    color = (
                        int(base_color[0] * 0.7 + edge_color[0] * 0.3),
                        int(base_color[1] * 0.7 + edge_color[1] * 0.3),
                        int(base_color[2] * 0.7 + edge_color[2] * 0.3),
                        alpha
                    )
                    img.putpixel((x, y), color)
        if side == 2:  # 左
            for y in range(H):
                burn = random.randint(16, 36)
                for x in range(burn):
                    alpha = random.randint(120, 200)
                    color = (
                        int(base_color[0] * 0.7 + edge_color[0] * 0.3),
                        int(base_color[1] * 0.7 + edge_color[1] * 0.3),
                        int(base_color[2] * 0.7 + edge_color[2] * 0.3),
                        alpha
                    )
                    img.putpixel((x, y), color)
        if side == 3:  # 右
            for y in range(H):
                burn = random.randint(16, 36)
                for x in range(W-1, W-burn, -1):
                    alpha = random.randint(120, 200)
                    color = (
                        int(base_color[0] * 0.7 + edge_color[0] * 0.3),
                        int(base_color[1] * 0.7 + edge_color[1] * 0.3),
                        int(base_color[2] * 0.7 + edge_color[2] * 0.3),
                        alpha
                    )
                    img.putpixel((x, y), color)

    # --- 2.紙のムラ・自然な陰影 ---
    for i in range(10):
        y = random.randint(40, H-40)
        draw.line([(0, y), (W, y)], fill=(210, 190, 150, 40), width=random.randint(1, 3))
    for i in range(6):
        x = random.randint(40, W-40)
        draw.line([(x, 0), (x, H)], fill=(210, 190, 150, 24), width=random.randint(1, 2))

    arr = np.array(img)
    noise = np.random.normal(0, 4, (H, W, 1))
    arr[:,:,:3] = np.clip(arr[:,:,:3] + noise, 0, 255)
    img = Image.fromarray(arr.astype(np.uint8), "RGBA")

    img = img.filter(ImageFilter.GaussianBlur(1.2))

    # --- 3. 外枠（破れ風・やや濃い茶色） ---
    border_draw = ImageDraw.Draw(img)
    border_draw.rectangle([11, 11, W-11, H-11], outline=border_color, width=3)

    img.save(output_path)
    return output_path
