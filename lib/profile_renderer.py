from PIL import Image, ImageDraw, ImageFilter

def generate_profile_card(player_data, output_path="profile_card.png", size=(800, 1100)):
    # 濃いカーキ色＋黒みがかった周囲
    base_color = (198, 168, 107)      # 濃いカーキ
    edge_color = (91, 71, 48)         # 黒みの焦げ茶
    W, H = size

    img = Image.new("RGBA", (W, H), base_color)
    draw = ImageDraw.Draw(img)

    # --- 1. 周囲グラデーション（円ではなく矩形に沿って） ---
    edge_width = 70
    for i in range(edge_width):
        # iが小さいほど外側、iが大きいほど内側
        ratio = i / edge_width
        color = (
            int(base_color[0] * (1 - ratio) + edge_color[0] * ratio),
            int(base_color[1] * (1 - ratio) + edge_color[1] * ratio),
            int(base_color[2] * (1 - ratio) + edge_color[2] * ratio),
            255
        )
        # 外枠に近いほどedge_color
        draw.rectangle([i, i, W - i, H - i], outline=color)

    # --- 2. 軽いぼかしでなじませる（任意・好みで） ---
    img = img.filter(ImageFilter.GaussianBlur(1.3))

    img.save(output_path)
    return output_path
