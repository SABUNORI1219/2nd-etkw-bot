from PIL import Image, ImageDraw, ImageFilter
import random
import math

def generate_profile_card(player_data, output_path="profile_card.png", size=(800, 1100)):
    base_color = (198, 168, 107)   # 濃いカーキ
    burn_color = (65, 53, 38)      # 黒みの焦げ茶
    W, H = size

    img = Image.new("RGBA", (W, H), base_color)

    # --- ムラ感を広げてカーキに馴染ませる ---
    max_burn = 120      # 焦げの最大幅を広げる
    min_burn = 40       # 焦げの最小幅
    burn_variance = 40  # ムラの強度（大きめ）

    for y in range(H):
        for x in range(W):
            # 端からの距離（最小）
            dist_left = x
            dist_right = W - x - 1
            dist_top = y
            dist_bottom = H - y - 1
            dist_min = min(dist_left, dist_right, dist_top, dist_bottom)

            # ランダムノイズで焦げエリアを不規則に
            burn_edge = random.randint(min_burn, max_burn) + int(random.gauss(0, burn_variance))
            burn_edge = max(min_burn, min(max_burn, burn_edge))

            # ムラ感広く、端からmax_burnピクセルまで焦げ
            if dist_min < burn_edge:
                # ratio: 端(0)〜内側(burn_edge)まで
                ratio = dist_min / burn_edge

                # なじませるためにグラデーションを滑らかに
                # ratioを指数的に緩やかに（端が強く、内側はカーキに寄せる）
                smooth_ratio = ratio ** 1.8

                # 端にはたまに濃いスポットを作る
                if random.random() < 0.13 * (1-smooth_ratio):
                    r = int(burn_color[0] * (1-smooth_ratio) + base_color[0] * smooth_ratio)
                    g = int(burn_color[1] * (1-smooth_ratio) + base_color[1] * smooth_ratio)
                    b = int(burn_color[2] * (1-smooth_ratio) + base_color[2] * smooth_ratio)
                else:
                    r = int(base_color[0] * smooth_ratio + burn_color[0] * (1-smooth_ratio))
                    g = int(base_color[1] * smooth_ratio + burn_color[1] * (1-smooth_ratio))
                    b = int(base_color[2] * smooth_ratio + burn_color[2] * (1-smooth_ratio))

                img.putpixel((x, y), (r, g, b, 255))

    # 端を軽くぼかしてさらに馴染ませる
    img = img.filter(ImageFilter.GaussianBlur(1.8))

    img.save(output_path)
    return output_path
