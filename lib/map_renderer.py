from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import logging
import json
import discord
from datetime import datetime, timezone, timedelta
from math import sqrt
import collections

logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_PATH = os.path.join(project_root, "assets", "map")
FONT_PATH = os.path.join(project_root, "assets", "fonts", "NotoSansJP-Bold.ttf")

class MapRenderer:
    def __init__(self):
        try:
            self.map_img = Image.open(os.path.join(ASSETS_PATH, "main-map.png")).convert("RGBA")
            self.crown_img = Image.open(os.path.join(ASSETS_PATH, "crown.png")).convert("RGBA")
            with open(os.path.join(ASSETS_PATH, "territories.json"), "r", encoding='utf-8') as f:
                self.local_territories = json.load(f)
            self.font = ImageFont.truetype(FONT_PATH, 40)

            TARGET_WIDTH = 1600
            original_w, original_h = self.map_img.size
            scale_factor = TARGET_WIDTH / original_w
            new_h = int(original_h * scale_factor)
            self.resized_map = self.map_img.resize((TARGET_WIDTH, new_h), Image.Resampling.LANCZOS)
            self.scale_factor = scale_factor
            logger.info(f"--- [MapRenderer] ベースマップを初期リサイズしました: {TARGET_WIDTH}x{new_h}")
        
        except FileNotFoundError as e:
            logger.error(f"マップ生成に必要なアセットが見つかりません: {e}")
            raise

    def _coord_to_pixel(self, x, z):
        return x + 2383, z + 6572

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        hex_color = hex_color.lstrip('#')
        try:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        except (ValueError, IndexError):
            return (255, 255, 255)

    def _is_city_territory(self, territory_data):
        emeralds = int(territory_data.get("resources", {}).get("emeralds", "0"))
        return emeralds == 18000

    def _calc_conn_ext_hqbuff(self, owned_territories, territory_name):
        connections = set()
        externals = set()
        visited = set()
        queue = [(territory_name, 0)]
        while queue:
            current, dist = queue.pop(0)
            if current in visited or dist > 3:
                continue
            visited.add(current)
            if dist == 1 and current in owned_territories:
                connections.add(current)
            if dist > 0 and current in owned_territories and current != territory_name:
                externals.add(current)
            for conn in self.local_territories.get(current, {}).get("Trading Routes", []):
                if conn not in visited:
                    queue.append((conn, dist + 1))
        multiplier = (1.5 + (len(externals) * 0.25)) * (1.0 + (len(connections) * 0.30))
        hq_buff = int(multiplier * 100)
        return len(connections), len(externals), hq_buff

    def _sum_resources(self, owned_territories):
        total = {"emeralds": 0, "ore": 0, "crops": 0, "fish": 0, "wood": 0}
        for t in owned_territories:
            res = self.local_territories.get(t, {}).get("resources", {})
            for k in total:
                total[k] += int(res.get(k, "0"))
        return total

    def _pick_hq_candidate(self, owned_territories, territory_api_data):
        # Step1: HQ候補5つピックアップ (Conn含むExt多い順)
        hq_stats = []
        for t in owned_territories:
            conn, ext, hq_buff = self._calc_conn_ext_hqbuff(owned_territories, t)
            acquired = territory_api_data.get(t, {}).get("acquired", "")
            if not acquired:
                acquired = "9999-12-31T23:59:59.999999Z"
            is_city = self._is_city_territory(self.local_territories[t])
            hq_stats.append({
                "name": t,
                "conn": conn,
                "ext": ext,
                "hq_buff": hq_buff,
                "is_city": is_city,
                "acquired": acquired,
                "resources": self.local_territories[t].get("resources", {})
            })
        # Conn含むExt多い順→Conn多い順→HQバフ多い順→取得時刻古い順
        hq_stats.sort(key=lambda x: (-x["ext"], -x["conn"], -x["hq_buff"], x["acquired"]))
        top5 = hq_stats[:5]
        total_res = self._sum_resources(owned_territories)

        # Step2: Conn最大グループ
        max_conn = max(x["conn"] for x in top5)
        conn_group = [x for x in top5 if x["conn"] == max_conn]

        # Step3: その中でExt<20なもの
        conn_group_ext_lt20 = [x for x in conn_group if x["ext"] < 20]

        # Step4: その中に街があれば街
        city = next((x for x in conn_group_ext_lt20 if x["is_city"]), None)
        if city:
            return city["name"], hq_stats, top5, total_res

        # Step5: そうでなければExt最大グループ（同値ならHQバフ最大）
        if conn_group:
            max_ext = max(x["ext"] for x in conn_group)
            ext_group = [x for x in conn_group if x["ext"] == max_ext]
            hq_max = max(ext_group, key=lambda x: x["hq_buff"])
            return hq_max["name"], hq_stats, top5, total_res

        # ここまで来たら念のためtop5の最初を返しておく
        return top5[0]["name"], hq_stats, top5, total_res

    def _draw_trading_and_territories(self, map_to_draw_on, box, is_zoomed, territory_data, guild_color_map, hq_territories=None):
        overlay = Image.new("RGBA", map_to_draw_on.size, (0,0,0,0))
        overlay_draw = ImageDraw.Draw(overlay)
        draw = ImageDraw.Draw(map_to_draw_on)
        for name, data in self.local_territories.items():
            if "Trading Routes" not in data or "Location" not in data:
                continue
            try:
                x1 = (data["Location"]["start"][0] + data["Location"]["end"][0]) // 2
                z1 = (data["Location"]["start"][1] + data["Location"]["end"][1]) // 2
                l_px1, l_py1 = self._coord_to_pixel(x1, z1)
                l_scaled_px1, l_scaled_py1 = l_px1 * self.scale_factor, l_py1 * self.scale_factor
                for destination_name in data["Trading Routes"]:
                    dest_data = self.local_territories.get(destination_name)
                    if not dest_data or "Location" not in dest_data:
                        continue
                    x2 = (dest_data["Location"]["start"][0] + dest_data["Location"]["end"][0]) // 2
                    z2 = (dest_data["Location"]["start"][1] + dest_data["Location"]["end"][1]) // 2
                    l_px2, l_py2 = self._coord_to_pixel(x2, z2)
                    l_scaled_px2, l_scaled_py2 = l_px2 * self.scale_factor, l_py2 * self.scale_factor
                    if is_zoomed and box:
                        l_px1_rel, l_px2_rel = l_scaled_px1 - box[0], l_scaled_px2 - box[0]
                        l_py1_rel, l_py2_rel = l_scaled_py1 - box[1], l_scaled_py2 - box[1]
                        draw.line([(l_px1_rel, l_py1_rel), (l_px2_rel, l_py2_rel)], fill=(10, 10, 10, 128), width=1)
                    else:
                        draw.line([(l_scaled_px1, l_scaled_py1), (l_scaled_px2, l_scaled_py2)], fill=(10, 10, 10, 128), width=1)
            except KeyError:
                continue

        scaled_font_size = max(12, int(self.font.size * self.scale_factor))
        try:
            scaled_font = ImageFont.truetype(FONT_PATH, scaled_font_size)
        except IOError:
            scaled_font = ImageFont.load_default()

        for name, info in territory_data.items():
            if 'location' not in info or 'guild' not in info:
                continue
            t_px1, t_py1 = self._coord_to_pixel(*info["location"]["start"])
            t_px2, t_py2 = self._coord_to_pixel(*info["location"]["end"])
            t_scaled_px1, t_scaled_py1 = t_px1 * self.scale_factor, t_py1 * self.scale_factor
            t_scaled_px2, t_scaled_py2 = t_px2 * self.scale_factor, t_py2 * self.scale_factor
            if is_zoomed and box:
                t_px1_rel, t_px2_rel = t_scaled_px1 - box[0], t_scaled_px2 - box[0]
                t_py1_rel, t_py2_rel = t_scaled_py1 - box[1], t_scaled_py2 - box[1]
            else:
                t_px1_rel, t_py1_rel, t_px2_rel, t_py2_rel = t_scaled_px1, t_scaled_py1, t_scaled_px2, t_scaled_py2
            x_min, x_max = sorted([t_px1_rel, t_px2_rel])
            y_min, y_max = sorted([t_py1_rel, t_py2_rel])
            if x_max > 0 and y_max > 0 and x_min < map_to_draw_on.width and y_min < map_to_draw_on.height:
                prefix = info["guild"]["prefix"]
                color_hex = guild_color_map.get(prefix, "#FFFFFF")
                color_rgb = self._hex_to_rgb(color_hex)
                overlay_draw.rectangle([x_min, y_min, x_max, y_max], fill=(*color_rgb, 64))
                draw.rectangle([x_min, y_min, x_max, y_max], outline=color_rgb, width=2)
                if hq_territories and name in hq_territories:
                    continue
                draw.text(((x_min + x_max)/2, (y_min + y_max)/2), prefix, font=scaled_font, fill=color_rgb, anchor="mm", stroke_width=2, stroke_fill="black")
        return map_to_draw_on

    def draw_guild_hq_on_map(self, territory_data, guild_color_map, territory_api_data, box=None, is_zoomed=False, map_to_draw_on=None, owned_territories_map=None):
        if map_to_draw_on is None:
            map_img = self.resized_map.copy()
        else:
            map_img = map_to_draw_on
        prefix_to_territories = {}
        for name, info in territory_data.items():
            prefix = info.get("guild", {}).get("prefix", "")
            if not prefix:
                continue
            prefix_to_territories.setdefault(prefix, set()).add(name)
        hq_names = set()
        for prefix, owned in prefix_to_territories.items():
            candidate_territories = owned_territories_map[prefix] if owned_territories_map and prefix in owned_territories_map else owned
            hq_name, _, _, _ = self._pick_hq_candidate(candidate_territories, territory_api_data)
            hq_names.add(hq_name)
        self._draw_trading_and_territories(map_img, box, is_zoomed, territory_data, guild_color_map, hq_territories=hq_names)
        draw = ImageDraw.Draw(map_img)
        for prefix, owned in prefix_to_territories.items():
            candidate_territories = owned_territories_map[prefix] if owned_territories_map and prefix in owned_territories_map else owned
            hq_name, _, _, _ = self._pick_hq_candidate(candidate_territories, territory_api_data)
            loc = self.local_territories.get(hq_name, {}).get("Location")
            if not loc:
                continue
            x = (loc["start"][0] + loc["end"][0]) // 2
            z = (loc["start"][1] + loc["end"][1]) // 2
            px, py = self._coord_to_pixel(x, z)
            px, py = px * self.scale_factor, py * self.scale_factor
            if is_zoomed and box:
                px -= box[0]
                py -= box[1]
            color_hex = guild_color_map.get(prefix, "#FFFFFF")
            color_rgb = self._hex_to_rgb(color_hex)

            # --- 領地サイズに合わせて王冠サイズを決定 ---
            x1, y1 = self._coord_to_pixel(loc["start"][0], loc["start"][1])
            x2, y2 = self._coord_to_pixel(loc["end"][0], loc["end"][1])
            x1, x2 = x1 * self.scale_factor, x2 * self.scale_factor
            y1, y2 = y1 * self.scale_factor, y2 * self.scale_factor
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            # 前までのロジックで使っていた上限値
            scaled_font_size = max(12, int(self.font.size * self.scale_factor))
            crown_size_limit = int(scaled_font_size * 1.8)
            crown_size_limit = max(28, min(crown_size_limit, 120))
            # 領地の短辺の90%を王冠サイズ、ただし上限つき
            crown_size = int(min(width, height) * 0.9)
            crown_size = max(18, min(crown_size, crown_size_limit))

            crown_img_resized = self.crown_img.resize((crown_size, crown_size), Image.LANCZOS)
            crown_x = int(px - crown_size/2)
            crown_y = int(py - crown_size/2)
            map_img.alpha_composite(crown_img_resized, dest=(crown_x, crown_y))

            # --- プレフィクスのフォントサイズも王冠サイズに厳密フィット ---
            prefix_font_size = crown_size
            font_found = False
            for test_size in range(crown_size, 5, -1):
                try:
                    test_font = ImageFont.truetype(FONT_PATH, test_size)
                except IOError:
                    test_font = ImageFont.load_default()
                bbox = test_font.getbbox(prefix)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                if text_width <= crown_size and text_height <= crown_size:
                    prefix_font_size = test_size
                    font_found = True
                    break
            if font_found:
                prefix_font = ImageFont.truetype(FONT_PATH, prefix_font_size)
            else:
                prefix_font = ImageFont.load_default()
            bbox = prefix_font.getbbox(prefix)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = px
            text_y = crown_y - text_height // 2 - 2
            draw.text(
                (text_x, text_y),
                prefix,
                font=prefix_font,
                fill=color_rgb,
                anchor="mm",
                stroke_width=2,
                stroke_fill="black"
            )
        return map_img, [(0, 0, "", hq_name) for hq_name in hq_names]
    
    def create_territory_map(self, territory_data: dict, territories_to_render: dict, guild_color_map: dict, owned_territories_map=None) -> tuple[discord.File | None, discord.Embed | None]:
        if not territories_to_render:
            return None, None
        try:
            map_to_draw_on = self.resized_map.copy()
            box = None
            all_x, all_y = [], []
            is_zoomed = len(territories_to_render) < len(self.local_territories)
            if is_zoomed:
                for terri_data in territories_to_render.values():
                    loc = terri_data.get("location", {})
                    start_x, start_z = loc.get("start", [0,0])
                    end_x, end_z = loc.get("end", [0,0])
                    px1, py1 = self._coord_to_pixel(start_x, start_z)
                    px2, py2 = self._coord_to_pixel(end_x, end_z)
                    all_x.extend([px1 * self.scale_factor, px2 * self.scale_factor])
                    all_y.extend([py1 * self.scale_factor, py2 * self.scale_factor])

            if all_x and all_y:
                padding = 30
                box = (
                    max(0, min(all_x) - padding),
                    max(0, min(all_y) - padding),
                    min(self.resized_map.width, max(all_x) + padding),
                    min(self.resized_map.height, max(all_y) + padding)
                )
                map_to_draw_on = map_to_draw_on.crop(box)

            final_map, _ = self.draw_guild_hq_on_map(
                territory_data=territory_data,
                guild_color_map=guild_color_map,
                territory_api_data=territory_data,
                box=box,
                is_zoomed=is_zoomed,
                map_to_draw_on=map_to_draw_on,
                owned_territories_map=owned_territories_map
            )

            map_bytes = BytesIO()
            final_map.save(map_bytes, format='PNG')
            map_bytes.seek(0)

            jst_now = datetime.now(timezone(timedelta(hours=9)))
            formatted_time = jst_now.strftime("%Y/%m/%d %H:%M:%S")

            file = discord.File(map_bytes, filename="wynn_map.png")
            embed = discord.Embed(
                title="",
                color=discord.Color.green()
            )
            embed.set_image(url="attachment://wynn_map.png")
            embed.set_footer(text=f"Territory Map ({formatted_time}) | Minister Chikuwa")

            return file, embed

        except Exception as e:
            logger.error(f"マップ生成中にエラー: {e}", exc_info=True)
            return None, None

    def create_single_territory_image(self, territory: str, territory_data: dict, guild_color_map: dict) -> BytesIO | None:
        logger.info(f"--- [MapRenderer] 単一テリトリー画像生成開始: {territory}")
        try:
            terri_data = self.local_territories.get(territory)
            if not terri_data or 'Location' not in terri_data:
                logger.error(f"'{territory}'にLocationデータがありません。")
                return None
            
            map_to_draw_on = self.resized_map.copy()
            box = None
            all_x, all_y = [], []
            is_zoomed = None

            self.map_on_process, _ = self.draw_guild_hq_on_map(
                territory_data=territory_data,
                guild_color_map=guild_color_map,
                territory_api_data=territory_data,
                box=box,
                is_zoomed=is_zoomed,
                map_to_draw_on=map_to_draw_on
            )
            
            loc = terri_data.get("Location", {})
            
            px1, py1 = self._coord_to_pixel(*loc.get("start", [0, 0]))
            px2, py2 = self._coord_to_pixel(*loc.get("end", [0, 0]))

            px1, py1 = px1 * self.scale_factor, py1 * self.scale_factor
            px2, py2 = px2 * self.scale_factor, py2 * self.scale_factor

            left = min(px1, px2)
            right = max(px1, px2)
            top = min(py1, py2)
            bottom = max(py1, py2)

            padding = 50

            box = (
                max(0, left - padding),
                max(0, top - padding),
                min(self.map_on_process.width, right + padding),
                min(self.map_on_process.height, bottom + padding)
            )

            if not (box[0] < box[2] and box[1] < box[3]):
                logger.error(f"'{territory}'の計算後の切り抜き範囲が無効です。Box: {box}")
                return None

            center_x = (px1 + px2) / 2
            center_y = (py1 + py2) / 2
            territory_width = abs(px2 - px1)
            territory_height = abs(py2 - py1)
            highlight_radius = int(sqrt(territory_width ** 2 + territory_height ** 2) / 2)

            draw = ImageDraw.Draw(self.map_on_process)
            draw.ellipse(
                [(center_x - highlight_radius, center_y - highlight_radius),
                 (center_x + highlight_radius, center_y + highlight_radius)],
                outline="gold",
                width=3
            )
                
            cropped_image = self.map_on_process.crop(box)
            map_bytes = BytesIO()
            cropped_image.save(map_bytes, format='PNG')
            map_bytes.seek(0)
            logger.info(f"--- [MapRenderer] ✅ 画像生成成功。")
            
            return map_bytes
        except Exception as e:
            logger.error(f"単一テリトリー画像の生成中にエラー: {e}")
            return None
