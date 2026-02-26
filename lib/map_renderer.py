from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import logging
import json
import discord
from datetime import datetime, timezone, timedelta
from math import sqrt

logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_PATH = os.path.join(project_root, "assets", "map")
FONT_PATH = os.path.join(project_root, "assets", "fonts", "Minecraftia-Regular.ttf")

class MapRenderer:
    def __init__(self):
        try:
            with open(os.path.join(ASSETS_PATH, "territories.json"), "r", encoding='utf-8') as f:
                self.local_territories = json.load(f)
            self.font_path = FONT_PATH
        except FileNotFoundError as e:
            logger.error(f"マップ生成に必要なアセットが見つかりません: {e}")
            raise

    def _coord_to_pixel(self, x, z):
        return x + 2400, z + 6600

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        hex_color = hex_color.lstrip('#')
        try:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        except (ValueError, IndexError):
            return (255, 255, 255)

    def _get_guild_territory_stats(self, territory_data):
        """ギルドごとの領地保持統計を計算"""
        guild_stats = {}
        for name, info in territory_data.items():
            if "guild" not in info or not info["guild"].get("prefix"):
                continue
            prefix = info["guild"]["prefix"]
            guild_name = info["guild"]["name"]
            if prefix not in guild_stats:
                guild_stats[prefix] = {
                    "name": guild_name,
                    "prefix": prefix,
                    "count": 0
                }
            guild_stats[prefix]["count"] += 1
        
        # 領地数で降順ソート
        return sorted(guild_stats.values(), key=lambda x: x["count"], reverse=True)
    
    def create_territory_stats_embed(self, territory_data: dict) -> discord.Embed:
        """領地統計Embedを作成"""
        guild_stats = self._get_guild_territory_stats(territory_data)
        
        embed = discord.Embed(
            title="🏰 Territory Holdings",
            color=discord.Color.blue()
        )
        
        if guild_stats:
            # 全ギルドを表示
            stats_text = []
            
            for i, guild in enumerate(guild_stats, 1):
                prefix = guild["prefix"]
                name = guild["name"]
                count = guild["count"]
                
                # 順位に応じて絵文字を追加
                if i == 1:
                    rank_emoji = "🥇"
                elif i == 2:
                    rank_emoji = "🥈"
                elif i == 3:
                    rank_emoji = "🥉"
                else:
                    rank_emoji = f"`{i:2d}.`"
                
                stats_text.append(f"{rank_emoji} **{prefix}** - {count} territories")
            
            embed.description = "\n".join(stats_text)
        else:
            embed.description = "No territory data available"
        
        embed.set_footer(text="Territory Statistics | Minister Chikuwa")
        return embed

    def _get_map_and_scale(self):
        map_img = Image.open(os.path.join(ASSETS_PATH, "main-map.png")).convert("RGBA")
        TARGET_WIDTH = 1600
        original_w, original_h = map_img.size
        scale_factor = TARGET_WIDTH / original_w
        new_h = int(original_h * scale_factor)
        resized_map = map_img.resize((TARGET_WIDTH, new_h), Image.Resampling.LANCZOS)
        map_img.close()
        return resized_map, scale_factor

    def _get_font(self, size):
        try:
            return ImageFont.truetype(self.font_path, size)
        except Exception:
            return ImageFont.load_default()

    def _draw_trading_and_territories(self, map_to_draw_on, box, is_zoomed, territory_data, guild_color_map, show_held_time=False, upscale_factor=1.5):
        upscaled_lines = None
        overlay = None

        try:
            # コネクション線の描画
            up_w, up_h = int(map_to_draw_on.width * upscale_factor), int(map_to_draw_on.height * upscale_factor)
            upscaled_lines = Image.new("RGBA", (up_w, up_h), (0, 0, 0, 0))
            draw_lines = ImageDraw.Draw(upscaled_lines)
            for name, data in self.local_territories.items():
                if "Trading Routes" not in data or "Location" not in data:
                    continue
                try:
                    x1 = (data["Location"]["start"][0] + data["Location"]["end"][0]) // 2
                    z1 = (data["Location"]["start"][1] + data["Location"]["end"][1]) // 2
                    l_px1, l_py1 = self._coord_to_pixel(x1, z1)
                    l_scaled_px1, l_scaled_py1 = l_px1 * self.scale_factor * upscale_factor, l_py1 * self.scale_factor * upscale_factor
                    for destination_name in data["Trading Routes"]:
                        dest_data = self.local_territories.get(destination_name)
                        if not dest_data or "Location" not in dest_data:
                            continue
                        x2 = (dest_data["Location"]["start"][0] + dest_data["Location"]["end"][0]) // 2
                        z2 = (dest_data["Location"]["start"][1] + dest_data["Location"]["end"][1]) // 2
                        l_px2, l_py2 = self._coord_to_pixel(x2, z2)
                        l_scaled_px2, l_scaled_py2 = l_px2 * self.scale_factor * upscale_factor, l_py2 * self.scale_factor * upscale_factor
                        if is_zoomed and box:
                            l_px1_rel = l_scaled_px1 - box[0] * upscale_factor
                            l_py1_rel = l_scaled_py1 - box[1] * upscale_factor
                            l_px2_rel = l_scaled_px2 - box[0] * upscale_factor
                            l_py2_rel = l_scaled_py2 - box[1] * upscale_factor
                            points = [(l_px1_rel, l_py1_rel), (l_px2_rel, l_py2_rel)]
                        else:
                            points = [(l_scaled_px1, l_scaled_py1), (l_scaled_px2, l_scaled_py2)]
                        color_rgb = (30, 30, 30)
                        draw_lines.line(points, fill=(*color_rgb, 180), width=3)
                except KeyError:
                    continue
            lines_down = upscaled_lines.resize((map_to_draw_on.width, map_to_draw_on.height), resample=Image.Resampling.LANCZOS)
            map_to_draw_on.alpha_composite(lines_down)
            del draw_lines, lines_down

            # 領地描画
            overlay = Image.new("RGBA", map_to_draw_on.size, (0,0,0,0))
            overlay_draw = ImageDraw.Draw(overlay)
            draw = ImageDraw.Draw(map_to_draw_on)
            scaled_font_size = max(12, int(self._get_font(40).size * self.scale_factor))
            scaled_font = self._get_font(scaled_font_size)
            time_font_size = max(8, int(scaled_font_size * 0.6))
            time_font = self._get_font(time_font_size)
            
            for name, info in territory_data.items():
                static = self.local_territories.get(name)
                if not static or "Location" not in static:
                    continue
                if "guild" not in info or not info["guild"].get("prefix"):
                    continue
                t_px1, t_py1 = self._coord_to_pixel(*static["Location"]["start"])
                t_px2, t_py2 = self._coord_to_pixel(*static["Location"]["end"])
                t_scaled_px1, t_scaled_py1 = t_px1 * self.scale_factor, t_py1 * self.scale_factor
                t_scaled_px2, t_scaled_py2 = t_px2 * self.scale_factor, t_py2 * self.scale_factor
                if is_zoomed and box:
                    t_px1_rel, t_px2_rel = t_scaled_px1 - box[0], t_scaled_px2 - box[0]
                    t_py1_rel, t_py2_rel = t_scaled_py1 - box[1], t_scaled_py2 - box[1]
                else:
                    t_px1_rel, t_py1_rel, t_px2_rel, t_py2_rel = t_scaled_px1, t_scaled_py1, t_scaled_px2, t_scaled_py2
                x_min, x_max = sorted([t_px1_rel, t_px2_rel])
                y_min, y_max = sorted([t_py1_rel, t_py2_rel])
                prefix = info["guild"]["prefix"]
                color_hex = guild_color_map.get(prefix, "#FFFFFF")
                color_rgb = self._hex_to_rgb(color_hex)
                overlay_draw.rectangle([x_min, y_min, x_max, y_max], fill=(*color_rgb, 64))
                draw.rectangle([x_min, y_min, x_max, y_max], outline=color_rgb, width=2)
                
                center_x = (x_min + x_max) / 2
                center_y = (y_min + y_max) / 2
                
                # ギルド名描画
                draw.text(
                    (center_x, center_y),
                    prefix,
                    font=scaled_font,
                    fill=color_rgb,
                    anchor="mm",
                    stroke_width=2,
                    stroke_fill="black"
                )
                
                # 保持時間描画（show_held_timeがTrueの場合のみ）
                if show_held_time and "acquired" in info:
                    try:
                        acquired_dt = datetime.fromisoformat(info['acquired'].replace("Z", "+00:00"))
                        duration = datetime.now(timezone.utc) - acquired_dt
                        
                        days = duration.days
                        hours, remainder = divmod(duration.seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        
                        time_parts = []
                        if days > 0:
                            time_parts.append(f"{days}d")
                        if hours > 0:
                            time_parts.append(f"{hours}h")
                        if minutes > 0:
                            time_parts.append(f"{minutes}m")
                        if seconds > 0 or not time_parts:
                            time_parts.append(f"{seconds}s")
                        
                        time_text = " ".join(time_parts[:2])  # 最大2つのパートまで表示
                        
                        # ギルド名の下に時間を表示
                        time_y = center_y + scaled_font_size // 2 + 2
                        draw.text(
                            (center_x, time_y + 3),
                            time_text,
                            font=time_font,
                            fill=(200, 200, 200),
                            anchor="mm",
                            stroke_width=1,
                            stroke_fill="black"
                        )
                    except (ValueError, KeyError):
                        pass
                        
            map_to_draw_on.alpha_composite(overlay)
            del overlay_draw, draw
        finally:
            if upscaled_lines is not None:
                upscaled_lines.close()
            if overlay is not None:
                overlay.close()

    def draw_territories_on_map(self, territory_data, guild_color_map, box=None, is_zoomed=False, map_to_draw_on=None, show_held_time=False):
        """領地をマップ上に描画する（HQ機能なし）"""
        try:
            self._draw_trading_and_territories(map_to_draw_on, box, is_zoomed, territory_data, guild_color_map, show_held_time=show_held_time)
            return map_to_draw_on
        except Exception as e:
            logger.error(f"領地描画中にエラー: {e}")
            return map_to_draw_on

    # デフォルトマップ生成するやつ
    def create_territory_map(self, territory_data: dict, territories_to_render: dict, guild_color_map: dict, show_held_time: bool = False) -> tuple[discord.File | None, discord.Embed | None]:
        if not territories_to_render:
            return None, None
        resized_map, scale_factor = self._get_map_and_scale()
        self.scale_factor = scale_factor
        map_to_draw_on = None
        file = None
        embed = None
        box = None
        all_x, all_y = [], []
        is_zoomed = len(territories_to_render) < len(self.local_territories)
        try:
            if is_zoomed:
                for terri_data in territories_to_render.values():
                    loc = terri_data.get("location", {})
                    start_x, start_z = loc.get("start", [0,0])
                    end_x, end_z = loc.get("end", [0,0])
                    px1, py1 = self._coord_to_pixel(start_x, start_z)
                    px2, py2 = self._coord_to_pixel(end_x, end_z)
                    all_x.extend([px1 * scale_factor, px2 * scale_factor])
                    all_y.extend([py1 * scale_factor, py2 * scale_factor])
            if all_x and all_y:
                padding = 30
                box = (
                    max(0, min(all_x) - padding),
                    max(0, min(all_y) - padding),
                    min(resized_map.width, max(all_x) + padding),
                    min(resized_map.height, max(all_y) + padding)
                )
                cropped = resized_map.crop(box)
                resized_map.close()
                map_to_draw_on = cropped
            else:
                map_to_draw_on = resized_map
            final_map = self.draw_territories_on_map(
                territory_data=territory_data,
                guild_color_map=guild_color_map,
                box=box,
                is_zoomed=is_zoomed,
                map_to_draw_on=map_to_draw_on,
                show_held_time=show_held_time
            )
            map_bytes = BytesIO()
            try:
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
            finally:
                map_bytes.close()
                final_map.close()
                map_to_draw_on.close()
        except Exception as e:
            logger.error(f"マップ生成中にエラー: {e}", exc_info=True)
            return None, None

    # 単一テリトリー生成
    def create_single_territory_image(self, territory: str, territory_data: dict, guild_color_map: dict) -> BytesIO | None:
        terri_static = self.local_territories.get(territory)
        if not terri_static or 'Location' not in terri_static:
            logger.error(f"'{territory}'にLocationデータがありません。")
            return None
        terri_live = territory_data.get(territory)
        if not terri_live or "guild" not in terri_live:
            logger.error(f"領地 {territory} にAPIライブデータがありません。")
            return None
        owner_prefix = terri_live["guild"].get("prefix")
        if not owner_prefix:
            logger.error(f"領地 {territory} の所有ギルドprefixがAPIデータにありません")
            return None
        resized_map, scale_factor = self._get_map_and_scale()
        self.scale_factor = scale_factor
        map_to_draw_on = resized_map
        final_map = self.draw_territories_on_map(
            territory_data=territory_data,
            guild_color_map=guild_color_map,
            box=None,
            is_zoomed=False,
            map_to_draw_on=map_to_draw_on,
            show_held_time=True  # 単一領地表示では保持時間を表示
        )
        static = terri_static
        loc = static.get("Location", {})
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
            min(resized_map.width, right + padding),
            min(resized_map.height, bottom + padding)
        )
        if not (box[0] < box[2] and box[1] < box[3]):
            logger.error(f"'{territory}'の計算後の切り抜き範囲が無効です。Box: {box}")
            final_map.close()
            map_to_draw_on.close()
            return None
        center_x = (px1 + px2) / 2
        center_y = (py1 + py2) / 2
        territory_width = abs(px2 - px1)
        territory_height = abs(py2 - py1)
        highlight_radius = int(sqrt(territory_width ** 2 + territory_height ** 2) / 2)
        draw = ImageDraw.Draw(final_map)
        draw.ellipse(
            [(center_x - highlight_radius, center_y - highlight_radius),
             (center_x + highlight_radius, center_y + highlight_radius)],
            outline="gold",
            width=3
        )
        del draw
        cropped_image = final_map.crop(box)
        map_bytes = BytesIO()
        try:
            cropped_image.save(map_bytes, format='PNG')
            map_bytes.seek(0)
            result = BytesIO(map_bytes.getvalue())
            return result
        finally:
            map_bytes.close()
            cropped_image.close()
            final_map.close()
            map_to_draw_on.close()
