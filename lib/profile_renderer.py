from PIL import Image, ImageDraw, ImageFilter
import random
import numpy as np

def generate_profile_card(player_data, output_path="profile_card.png", size=(800, 1100)):
    W, H = size
    base_color = np.array([203, 169, 110])   # 中央の平均色
    edge_color = np.array([174, 129, 68])    # 焦げ色
    burn_width = 50                          # 周囲の幅

    img_arr = np.zeros((H, W, 4), dtype=np.uint8)
    img_arr[:, :, :3] = base_color
    img_arr[:, :, 3] = 255

    # 紙のザラザラノイズ（全体）
    noise_strength = 16
    paper_noise = np.random.normal(0, 1, (H, W, 1))
    img_arr[:, :, :3] = np.clip(img_arr[:, :, :3] + paper_noise * noise_strength, 0, 255)

    # 端からburn_width以内だけでまばらに焦げスポット
    yy, xx = np.mgrid[0:H, 0:W]
    dist_left = xx
    dist_right = W - xx - 1
    dist_top = yy
    dist_bottom = H - yy - 1
    dist_edge = np.minimum.reduce([dist_left, dist_right, dist_top, dist_bottom])
    edge_mask = dist_edge < burn_width

    num_spots = int(W * H * 0.15 // 180)  # 端面積に合わせて
    for _ in range(num_spots):
        # 端burn_width以内のランダム座標
        candidates = np.argwhere(edge_mask)
        if len(candidates) == 0: break
        idx = random.randint(0, len(candidates)-1)
        cy, cx = candidates[idx]
        spot_radius = random.randint(10, 30)
        spot_strength = random.uniform(0.3, 0.7)
        for dx in range(-spot_radius, spot_radius):
            for dy in range(-spot_radius, spot_radius):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < W and 0 <= ny < H:
                    # spot範囲が端からはみ出てもOK
                    d = np.hypot(dx, dy)
                    if d < spot_radius * (0.8 + 0.3*random.random()):
                        spot_ratio = spot_strength * (1 - d / spot_radius)
                        img_arr[ny, nx, :3] = (
                            img_arr[ny, nx, :3] * (1 - spot_ratio) +
                            edge_color * spot_ratio
                        ).astype(np.uint8)

    # ぼかし控えめ
    img = Image.fromarray(img_arr, 'RGBA')
    img = img.filter(ImageFilter.GaussianBlur(0.5))

    img.save(output_path)
    return output_path
