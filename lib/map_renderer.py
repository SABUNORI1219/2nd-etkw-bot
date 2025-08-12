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

# DBとキャッシュから履歴情報を取得
from lib.db import get_guild_territory_state
from tasks.guild_territory_tracker import get_effective_owned_territories, sync_history_from_db

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

    def _get_owned_territories_map_from_db(self):
        """
        DBから「ギルドごとに '現所有+直近1時間以内に失領' を含む領地名セット」を返す
        """
        sync_history_from_db()  # 必ず最新化
        db_state = get_guild_territory_state()
        # {prefix: set(territory_name)}
        return {prefix: set(get_effective_owned_territories(prefix)) for prefix in db_state}

    def _pick_hq_candidate(self, owned_territories, territory_api_data, exclude_lost=None):
        # exclude_lost: HQ候補から除外したい領地名(set)
        hq_stats = []
        for t in owned_territories:
            if exclude_lost and t in exclude_lost:
                continue
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
        if not hq_stats:
            return None, [], [], {}
        # Conn含むExt多い順→Conn多い順→HQバフ多い順→取得時刻古い順
        hq_stats.sort(key=lambda x: (-(x["conn"] + x["ext"]), -x["conn"], -x["ext"], -x["hq_buff"], x["acquired"]))
        top5 = hq_stats[:5]
        total_res = self._sum_resources(owned_territories)

        # 1. Conn > Ext最大グループのConn + 2 なら優先
        max_ext = max(x["ext"] for x in top5)
        ext_max_group = [x for x in top5 if x["ext"] == max_ext]
        ext_max_conn = max(x["conn"] for x in ext_max_group)
        conn2plus_candidates = [x for x in top5 if x["conn"] >= ext_max_conn + 2]
        if conn2plus_candidates:
            conn2plus_candidates.sort(key=lambda x: (-x["conn"], -x["ext"], -x["hq_buff"], x["acquired"]))
            return conn2plus_candidates[0]["name"], hq_stats, top5, total_res

        # 2. Conn含むExtの数が同数の領地が2つ以上ピックされた場合、Connが多いほうを優先
        max_conn_ext = max(x["conn"] + x["ext"] for x in top5)
        conn_ext_tops = [x for x in top5 if x["conn"] + x["ext"] == max_conn_ext]
        if len(conn_ext_tops) > 1:
            conn_max_val = max(x["conn"] for x in conn_ext_tops)
            conn_maxs = [x for x in conn_ext_tops if x["conn"] == conn_max_val]
            if len(conn_maxs) == 1:
                return conn_maxs[0]["name"], hq_stats, top5, total_res
        else:
            conn_maxs = conn_ext_tops
    
        # 3. 所持領地が6個以下の場合、Time Heldが一番長い箇所
        if len(owned_territories) <= 6:
            oldest = min(top5, key=lambda x: x["acquired"] or "9999")
            return oldest["name"], hq_stats, top5, total_res
        
        # 4. Conn同数かつExt<20で街領地があればそれを優先
        ext_max_group_conns = [x["conn"] for x in ext_max_group]
        conn_max_in_ext = max(ext_max_group_conns)
        conn_maxs = [x for x in ext_max_group if x["conn"] == conn_max_in_ext]
        if len(conn_maxs) > 1:
            if conn_maxs[0]["ext"] < 20:
                city = next((x for x in conn_maxs if x["is_city"]), None)
                if city:
                    return city["name"], hq_stats, top5, total_res
            return conn_maxs[0]["name"], hq_stats, top5, total_res
        else:
            return conn_maxs[0]["name"], hq_stats, top5, total_res

        # 5. Conn,Ext同値なら資源バランス優先
        if len(conn_maxs) > 1 and all(x["conn"] == conn_maxs[0]["conn"] and x["ext"] == conn_maxs[0]["ext"] for x in conn_maxs):
            res_priority = ["crops", "ore", "wood", "fish"]
            min_val = float("inf")
            min_type = None
            for rtype in res_priority:
                val = total_res.get(rtype, 0)
                if val > 0 and val < min_val:
                    min_val = val
                    min_type = rtype
            if min_type:
                def trading_route_distance(start, goals):
                    queue = collections.deque()
                    visited = set()
                    queue.append((start, 0))
                    while queue:
                        current, dist = queue.popleft()
                        if current in visited:
                            continue
                        visited.add(current)
                        if current in goals:
                            return dist
                        neighbors = self.local_territories.get(current, {}).get("Trading Routes", [])
                        neighbors = [n for n in neighbors if n in owned_territories]
                        queue.extend((n, dist+1) for n in neighbors)
                    return float("inf")
                res_territories = [x for x in hq_stats if int(x["resources"].get(min_type, "0")) > 0]
                res_names = [x["name"] for x in res_territories]
                min_dist = float("inf")
                best_cand = conn_maxs[0]
                for cand in conn_maxs:
                    d = trading_route_distance(cand["name"], set(res_names))
                    if d < min_dist:
                        min_dist = d
                        best_cand = cand
                    elif d == min_dist:
                        cand_res = int(self.local_territories[cand["name"]].get("resources", {}).get(min_type, "0"))
                        best_res = int(self.local_territories[best_cand["name"]].get("resources", {}).get(min_type, "0"))
                        if cand_res > best_res:
                            best_cand = cand
                return best_cand["name"], hq_stats, top5, total_res

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
                        points = [(l_px1_rel, l_py1_rel), (l_px2_rel, l_py2_rel)]
                    else:
                        points = [(l_scaled_px1, l_scaled_py1), (l_scaled_px2, l_scaled_py2)]
                    color_rgb = (10, 10, 10)
                    # 1pxメイン
                    draw.line(points, fill=(*color_rgb, 200), width=1)
                    # 2px薄く
                    draw.line(points, fill=(*color_rgb, 80), width=2)
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

        # ここでprefix_to_territoriesはAPIからでなくowned_territories_mapから構成する
        prefix_to_territories = {}
        if owned_territories_map:
            for prefix, terrset in owned_territories_map.items():
                prefix_to_territories[prefix] = set(terrset)
        else:
            # fallback: APIの直所有
            for name, info in territory_data.items():
                prefix = info.get("guild", {}).get("prefix", "")
                if not prefix:
                    continue
                prefix_to_territories.setdefault(prefix, set()).add(name)

        # HQ候補地から「1時間以内に失領した領地」を除外
        db_state = get_guild_territory_state()
        hq_names = set()
        for prefix, owned in prefix_to_territories.items():
            # 直近1時間以内に奪われた領地
            lost_only = set()
            for t in db_state.get(prefix, {}):
                lost_time = db_state[prefix][t].get("lost")
                if lost_time is not None:
                    # HQ候補地から除外
                    lost_only.add(t)
            # 有効なHQ候補のみで選定
            candidate_territories = owned - lost_only
            hq_name, _, _, _ = self._pick_hq_candidate(candidate_territories, territory_api_data)
            if hq_name:
                hq_names.add(hq_name)
        self._draw_trading_and_territories(map_img, box, is_zoomed, territory_data, guild_color_map, hq_territories=hq_names)
        draw = ImageDraw.Draw(map_img)
        for prefix, owned in prefix_to_territories.items():
            lost_only = set()
            for t in db_state.get(prefix, {}):
                lost_time = db_state[prefix][t].get("lost")
                if lost_time is not None:
                    lost_only.add(t)
            candidate_territories = owned - lost_only
            hq_name, _, _, _ = self._pick_hq_candidate(candidate_territories, territory_api_data)
            if not hq_name:
                continue
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

            x1, y1 = self._coord_to_pixel(loc["start"][0], loc["start"][1])
            x2, y2 = self._coord_to_pixel(loc["end"][0], loc["end"][1])
            x1, x2 = x1 * self.scale_factor, x2 * self.scale_factor
            y1, y2 = y1 * self.scale_factor, y2 * self.scale_factor
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            scaled_font_size = max(12, int(self.font.size * self.scale_factor))
            crown_size_limit = int(scaled_font_size * 1.8)
            crown_size_limit = max(28, min(crown_size_limit, 120))
            crown_size = int(min(width, height) * 0.9)
            crown_size = max(18, min(crown_size, crown_size_limit))

            crown_img_resized = self.crown_img.resize((crown_size, crown_size), Image.LANCZOS)
            crown_x = int(px - crown_size/2)
            crown_y = int(py - crown_size/2)
            map_img.alpha_composite(crown_img_resized, dest=(crown_x, crown_y))

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
        if owned_territories_map is None:
            owned_territories_map = self._get_owned_territories_map_from_db()
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

    def create_single_territory_image(self, territory: str, guild_color_map: dict) -> BytesIO | None:
        logger.info(f"--- [MapRenderer] 単一テリトリー画像生成開始: {territory}")
        try:
            terri_data = self.local_territories.get(territory)
            if not terri_data or 'Location' not in terri_data:
                logger.error(f"'{territory}'にLocationデータがありません。")
                return None
    
            # --- ここでDB履歴を参照し、所有ギルドを判定 ---
            sync_history_from_db()
            db_state = get_guild_territory_state()
            owner_prefix = None
            for prefix, terrs in db_state.items():
                if territory in get_effective_owned_territories(prefix):
                    owner_prefix = prefix
                    break
    
            if not owner_prefix:
                logger.error(f"領地 {territory} の所有ギルドが1時間ルール下にも見つかりません")
                return None
    
            map_to_draw_on = self.resized_map.copy()
            box = None
    
            # 領地名→所有ギルドの色を取得
            color_hex = guild_color_map.get(owner_prefix, "#FFFFFF")
            color_rgb = self._hex_to_rgb(color_hex)
    
            # 領地の位置
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
                min(self.resized_map.width, right + padding),
                min(self.resized_map.height, bottom + padding)
            )
    
            if not (box[0] < box[2] and box[1] < box[3]):
                logger.error(f"'{territory}'の計算後の切り抜き範囲が無効です。Box: {box}")
                return None
    
            center_x = (px1 + px2) / 2
            center_y = (py1 + py2) / 2
            territory_width = abs(px2 - px1)
            territory_height = abs(py2 - py1)
            highlight_radius = int(sqrt(territory_width ** 2 + territory_height ** 2) / 2)
    
            draw = ImageDraw.Draw(map_to_draw_on)
            draw.ellipse(
                [(center_x - highlight_radius, center_y - highlight_radius),
                 (center_x + highlight_radius, center_y + highlight_radius)],
                outline="gold",
                width=3
            )
            # 領地全体を色で塗る
            draw.rectangle([left, top, right, bottom], outline=color_rgb, width=5)
    
            cropped_image = map_to_draw_on.crop(box)
            map_bytes = BytesIO()
            cropped_image.save(map_bytes, format='PNG')
            map_bytes.seek(0)
            logger.info(f"--- [MapRenderer] ✅ 画像生成成功。")
            return map_bytes
        except Exception as e:
            logger.error(f"単一テリトリー画像の生成中にエラー: {e}")
            return None
