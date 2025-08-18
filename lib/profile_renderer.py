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
    burn_width = 50                          # 焦げエリア幅

    img_arr = np.zeros((H, W, 4), dtype=np.uint8)
    img_arr[:, :, :3] = base_color           # 全体はまず中央色
    img_arr[:, :, 3] = 255

    # --- 紙のザラザラノイズ（全体） ---
    noise_strength = 16
    paper_noise = np.random.normal(0, 1, (H, W, 1))
    img_arr[:, :, :3] = np.clip(img_arr[:, :, :3] + paper_noise * noise_strength, 0, 255)

    # --- 端から50px以内に“まばら”な焦げムラ ---
    yy, xx = np.mgrid[0:H, 0:W]
    dist_left = xx
    dist_right = W - xx - 1
    dist_top = yy
    dist_bottom = H - yy - 1
    dist_edge = np.minimum.reduce([dist_left, dist_right, dist_top, dist_bottom])
    edge_mask = dist_edge < burn_width

    # ランダムな形状の焦げスポットを端中心にばら撒く（四角禁止！）
    num_spots = int(W*H*0.10 // 80)  # 端の15%の面積を見積もり
    for _ in range(num_spots):
        # 端50px内のランダム座標
        while True:
            cx = random.randint(0, W-1)
            cy = random.randint(0, H-1)
            if dist_edge[cy, cx] < burn_width and random.random() < 0.8:
                break
        spot_radius = random.randint(7, 40)
        spot_strength = random.uniform(0.3, 0.7)
        spot_shape = random.uniform(0.7, 1.2)
        for dx in range(-spot_radius, spot_radius):
            for dy in range(-spot_radius, spot_radius):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < W and 0 <= ny < H:
                    # 楕円でまばらに
                    d = ((dx/spot_shape)**2 + (dy*spot_shape)**2)**0.5
                    if d < spot_radius * (0.9 + 0.2*random.random()):
                        # 端から遠すぎるところは飛ばす
                        if dist_edge[ny, nx] > burn_width: continue
                        spot_ratio = spot_strength * (1 - d/spot_radius)
                        img_arr[ny, nx, :3] = (
                            img_arr[ny, nx, :3] * (1 - spot_ratio) +
                            edge_color * spot_ratio
                        ).astype(np.uint8)

    # --- 端の焦げグラデーション（ランダムな広がり） ---
    grad_mask = edge_mask & (np.random.rand(H, W) > 0.75)  # 端にグラデ部分もまばらに
    grad_ratio = dist_edge[grad_mask] / burn_width
    img_arr[grad_mask, :3] = (
        base_color[None, :] * (1 - grad_ratio)[:, None] +
        edge_color[None, :] * grad_ratio[:, None]
    ).astype(np.uint8)

    # --- ぼかしは控えめ ---
    img = Image.fromarray(img_arr, 'RGBA')
    img = img.filter(ImageFilter.GaussianBlur(0.5))

    img.save(output_path)
    return output_path
