from PIL import Image, ImageDraw, ImageFilter
import random
import math
import numpy as np

def generate_profile_card(player_data, output_path="profile_card.png", size=(800, 1100)):
    W, H = size
    base_color = np.array([198, 168, 107])  # 濃いカーキ
    burn_color = np.array([65, 53, 38])     # 焦げ茶

    img_arr = np.zeros((H, W, 4), dtype=np.uint8)
    img_arr[:, :, :3] = base_color
    img_arr[:, :, 3] = 255

    # --- ノイズ生成（ムラ感・焦げ感を出す） ---
    # Perlinノイズ風：今回はシンプルなランダムノイズを拡大して近似
    noise = np.random.normal(0, 1, (H//8, W//8))
    noise = np.kron(noise, np.ones((8,8)))  # 拡大して滑らかさ
    noise = noise[:H, :W]

    # --- 端からの距離計算 ---
    yy, xx = np.mgrid[0:H, 0:W]
    dist_left = xx
    dist_right = W - xx - 1
    dist_top = yy
    dist_bottom = H - yy - 1
    dist_edge = np.minimum.reduce([dist_left, dist_right, dist_top, dist_bottom])

    # --- 焦げエリア判定・色生成 ---
    max_burn = 120
    min_burn = 30
    burn_map = dist_edge + noise * 40  # ノイズで焦げ幅を揺らす
    burn_map = np.clip(burn_map, 0, max_burn)

    # ratio: 端(0)〜内側(max_burn)まで
    ratio = burn_map / max_burn
    ratio = np.clip(ratio, 0, 1)

    # カーキと焦げ茶をブレンド
    burn_mask = ratio < 1
    img_arr[burn_mask, :3] = (
        base_color * ratio[burn_mask, None] +
        burn_color * (1 - ratio[burn_mask, None])
    ).astype(np.uint8)

    # さらに端に「濃い焦げスポット」を追加
    for _ in range(70):
        cx = random.randint(0, W-1)
        cy = random.randint(0, H-1)
        spot_radius = random.randint(6, 22)
        spot_strength = random.uniform(0.3, 0.7)
        for dx in range(-spot_radius, spot_radius):
            for dy in range(-spot_radius, spot_radius):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < W and 0 <= ny < H:
                    if math.hypot(dx, dy) < spot_radius:
                        spot_ratio = spot_strength * (1 - math.hypot(dx, dy)/spot_radius)
                        img_arr[ny, nx, :3] = (
                            img_arr[ny, nx, :3] * (1 - spot_ratio) +
                            burn_color * spot_ratio
                        ).astype(np.uint8)

    # PIL画像化 & ぼかしでなじませ
    img = Image.fromarray(img_arr, 'RGBA')
    img = img.filter(ImageFilter.GaussianBlur(1.0))

    img.save(output_path)
    return output_path
