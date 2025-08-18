from PIL import Image, ImageDraw, ImageFilter
import random
import math

def generate_profile_card(player_data, output_path="profile_card.png", size=(800, 1100)):
    # カーキ色（中央紙色）
    base_color = (198, 168, 107)
    # 焦げ色（黒みの強い焦げ茶）
    burn_color = (65, 53, 38)
    W, H = size

    img = Image.new("RGBA", (W, H), base_color)
    draw = ImageDraw.Draw(img)

    # --- 端を「焦げムラ」風にする ---
    max_burn = 65      # 最大焦げ幅
    min_burn = 28      # 最小焦げ幅
    burn_variance = 20 # 焦げのムラ強度

    # 各ピクセルごとに端からの距離で色を変化させる
    for y in range(H):
        for x in range(W):
            # 距離（端からどれくらいか）
            dist_left = x
            dist_right = W - x - 1
            dist_top = y
            dist_bottom = H - y - 1
            dist_min = min(dist_left, dist_right, dist_top, dist_bottom)
            # ムラ（ノイズで焦げ幅を不規則に）
            burn_edge = random.randint(min_burn, max_burn) + int(random.gauss(0, burn_variance))
            burn_edge = max(min_burn, min(max_burn, burn_edge))
            if dist_min < burn_edge:
                # ratio: 端(0)〜内側(burn_edge)までグラデ
                ratio = dist_min / burn_edge
                # 端ほど焦げ、内側ほどカーキ
                r = int(base_color[0] * ratio + burn_color[0] * (1-ratio))
                g = int(base_color[1] * ratio + burn_color[1] * (1-ratio))
                b = int(base_color[2] * ratio + burn_color[2] * (1-ratio))
                img.putpixel((x, y), (r, g, b, 255))

    # 軽くぼかして自然になじませる
    img = img.filter(ImageFilter.GaussianBlur(1.1))

    img.save(output_path)
    return output_path
