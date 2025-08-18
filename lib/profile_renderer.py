from PIL import Image, ImageDraw, ImageFilter
import random
import math
import logging
import numpy as np

logger = logging.getLogger(__name__)

def generate_profile_card(player_data, output_path="profile_card.png", size=(800, 1100)):
    W, H = size
    base_color = np.array([203, 169, 110])   # 画像中央の平均色
    edge_color = np.array([174, 129, 68])    # 画像端の平均色
    burn_width = 50                          # 焦げエリア幅（画像と同じ）

    img_arr = np.zeros((H, W, 4), dtype=np.uint8)
    img_arr[:, :, :3] = base_color           # 全体はまず中央色
    img_arr[:, :, 3] = 255

    # --- 端50pxにグラデーション＋ノイズで焦げ色 ---
    yy, xx = np.mgrid[0:H, 0:W]
    dist_left = xx
    dist_right = W - xx - 1
    dist_top = yy
    dist_bottom = H - yy - 1
    dist_edge = np.minimum.reduce([dist_left, dist_right, dist_top, dist_bottom])

    # ノイズ生成
    H_blocks = (H + 7) // 8
    W_blocks = (W + 7) // 8
    noise = np.random.normal(0, 1, (H_blocks, W_blocks))
    noise = np.kron(noise, np.ones((8,8)))
    noise = noise[:H, :W]
    noise = np.clip(noise, -1.2, 1.2)  # ノイズ振幅調整

    # グラデーション＋ノイズ
    edge_mask = dist_edge < burn_width
    ratio = dist_edge[edge_mask] / burn_width
    ratio_noise = np.clip(ratio + noise[edge_mask] * 0.08, 0, 1)

    img_arr[edge_mask, :3] = (
        base_color * (1 - ratio_noise) + edge_color * ratio_noise
    ).astype(np.uint8)

    # 焦げスポット（端50pxだけ）
    for _ in range(40):
        angle = random.uniform(0, 2*math.pi)
        r = random.uniform(0, burn_width)
        # 端からランダムに配置
        for _ in range(2):
            # 左右上下4辺
            for edge in ['top', 'bottom', 'left', 'right']:
                if edge == 'top':
                    cx = int(random.uniform(0, W))
                    cy = int(r)
                elif edge == 'bottom':
                    cx = int(random.uniform(0, W))
                    cy = H-1-int(r)
                elif edge == 'left':
                    cx = int(r)
                    cy = int(random.uniform(0, H))
                elif edge == 'right':
                    cx = W-1-int(r)
                    cy = int(random.uniform(0, H))
                spot_radius = random.randint(5, 18)
                spot_strength = random.uniform(0.4, 0.7)
                for dx in range(-spot_radius, spot_radius):
                    for dy in range(-spot_radius, spot_radius):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < W and 0 <= ny < H:
                            d = math.hypot(dx, dy)
                            if d < spot_radius:
                                spot_ratio = spot_strength * (1 - d/spot_radius)
                                img_arr[ny, nx, :3] = (
                                    img_arr[ny, nx, :3] * (1 - spot_ratio) +
                                    edge_color * spot_ratio
                                ).astype(np.uint8)

    # ぼかしで馴染ませ
    img = Image.fromarray(img_arr, 'RGBA')
    img = img.filter(ImageFilter.GaussianBlur(0.9))

    img.save(output_path)
    return output_path
