from PIL import Image, ImageDraw, ImageFilter
import random

def generate_profile_card(player_data, output_path="profile_card.png", size=(800, 1100)):
    # 中央カーキ色
    base_color = (198, 168, 107)      # 濃いカーキ
    # 端の焦げ色（カーキ＋焦げ茶＋黒）
    burn_dark = (65, 53, 38)          # 黒みの焦げ茶
    burn_mid = (91, 71, 48)           # 焦げ茶
    W, H = size

    img = Image.new("RGBA", (W, H), base_color)
    draw = ImageDraw.Draw(img)

    # --- 周囲を「自然な焦げ」風にする ---
    max_burn = 60  # 焦げの最大幅
    for side in ("top", "bottom", "left", "right"):
        for idx in range(W if side in ("top", "bottom") else H):
            # 焦げエリアの幅をランダムに
            burn_width = random.randint(24, max_burn)
            for b in range(burn_width):
                # 焦げ色グラデーション（黒み強め→カーキ）
                ratio = b / burn_width
                color = (
                    int(base_color[0] * (1 - ratio) + burn_dark[0] * ratio),
                    int(base_color[1] * (1 - ratio) + burn_dark[1] * ratio),
                    int(base_color[2] * (1 - ratio) + burn_dark[2] * ratio),
                    255
                )
                if side == "top":
                    x, y = idx, b
                elif side == "bottom":
                    x, y = idx, H - 1 - b
                elif side == "left":
                    x, y = b, idx
                elif side == "right":
                    x, y = W - 1 - b, idx
                # 端っこは一部だけ焦げを強調する（ランダムに濃い点を増やす）
                if random.random() < 0.18 * (1 - ratio):
                    color = (
                        int(burn_mid[0] * (1 - ratio) + burn_dark[0] * ratio),
                        int(burn_mid[1] * (1 - ratio) + burn_dark[1] * ratio),
                        int(burn_mid[2] * (1 - ratio) + burn_dark[2] * ratio),
                        255
                    )
                img.putpixel((x, y), color)

    # --- 端を軽くぼかしてなじませる（任意） ---
    img = img.filter(ImageFilter.GaussianBlur(1.2))

    img.save(output_path)
    return output_path
