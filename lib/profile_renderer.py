from PIL import Image, ImageDraw, ImageFilter
import random
import numpy as np

def generate_profile_card(player_data, output_path="profile_card.png", size=(800, 1100)):
    # 色設定
    base_color = (233, 223, 197)
    edge_color = (60, 40, 20)
    W, H = size

    # RGBAで作成（端の破れ・透明も表現）
    img = Image.new("RGBA", (W, H), base_color)
    draw = ImageDraw.Draw(img)

    # --- 1. 端の焦げ＋破れ表現 ---
    for side in range(4):
        if side == 0:  # 上側
            for x in range(W):
                burn = random.randint(20, 48)
                for y in range(burn):
                    alpha = random.randint(120, 255)
                    color = (
                        int(base_color[0] * 0.5 + edge_color[0] * 0.5),
                        int(base_color[1] * 0.5 + edge_color[1] * 0.5),
                        int(base_color[2] * 0.5 + edge_color[2] * 0.5),
                        alpha
                    )
                    img.putpixel((x, y), color)
                # 破れ
                if burn > 40 and random.random() < 0.11:
                    img.putpixel((x, random.randint(0, 8)), (0, 0, 0, 0))
        if side == 1:  # 下側
            for x in range(W):
                burn = random.randint(20, 48)
                for y in range(H-1, H-burn, -1):
                    alpha = random.randint(120, 255)
                    color = (
                        int(base_color[0] * 0.5 + edge_color[0] * 0.5),
                        int(base_color[1] * 0.5 + edge_color[1] * 0.5),
                        int(base_color[2] * 0.5 + edge_color[2] * 0.5),
                        alpha
                    )
                    img.putpixel((x, y), color)
                if burn > 40 and random.random() < 0.11:
                    img.putpixel((x, H-1-random.randint(0,8)), (0, 0, 0, 0))
        if side == 2:  # 左側
            for y in range(H):
                burn = random.randint(20, 48)
                for x in range(burn):
                    alpha = random.randint(120, 255)
                    color = (
                        int(base_color[0] * 0.5 + edge_color[0] * 0.5),
                        int(base_color[1] * 0.5 + edge_color[1] * 0.5),
                        int(base_color[2] * 0.5 + edge_color[2] * 0.5),
                        alpha
                    )
                    img.putpixel((x, y), color)
                if burn > 40 and random.random() < 0.11:
                    img.putpixel((random.randint(0,8), y), (0, 0, 0, 0))
        if side == 3:  # 右側
            for y in range(H):
                burn = random.randint(20, 48)
                for x in range(W-1, W-burn, -1):
                    alpha = random.randint(120, 255)
                    color = (
                        int(base_color[0] * 0.5 + edge_color[0] * 0.5),
                        int(base_color[1] * 0.5 + edge_color[1] * 0.5),
                        int(base_color[2] * 0.5 + edge_color[2] * 0.5),
                        alpha
                    )
                    img.putpixel((x, y), color)
                if burn > 40 and random.random() < 0.11:
                    img.putpixel((W-1-random.randint(0,8), y), (0, 0, 0, 0))

    # --- 2. 紙のシワ・ムラ感 ---
    # 横線（シワ）
    for i in range(12):
        y = random.randint(30, H-30)
        draw.line([(0, y), (W, y)], fill=(180,180,180,60), width=random.randint(1,3))
    # 縦線（シワ）
    for i in range(8):
        x = random.randint(30, W-30)
        draw.line([(x, 0), (x, H)], fill=(180,180,180,40), width=random.randint(1,2))

    # --- 3. ムラノイズ（点描よりムラ感重視） ---
    arr = np.array(img)
    noise = np.random.normal(0, 8, (H, W, 1))
    arr[:,:,:3] = np.clip(arr[:,:,:3] + noise, 0, 255)
    img = Image.fromarray(arr.astype(np.uint8), "RGBA")

    # --- 4. 軽いぼかしで馴染ませる ---
    img = img.filter(ImageFilter.GaussianBlur(1.5))

    # --- 5. 外枠（Wanted感UP） ---
    border_draw = ImageDraw.Draw(img)
    border_draw.rectangle([13, 13, W-13, H-13], outline=edge_color, width=3)

    img.save(output_path)
    return output_path
