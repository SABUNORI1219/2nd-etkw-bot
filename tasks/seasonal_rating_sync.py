import asyncio
import logging
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from lib.api_stocker import WynncraftAPI
from lib.db import (
    upsert_guild_seasonal_rating, get_conn, update_current_season, 
    get_current_season, is_season_completed
)
import psycopg2

logger = logging.getLogger(__name__)

class SeasonalRatingSync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api = None
        self.request_delay = 0.55  # 120req/min = 2req/sec、安全マージン含む（0.55秒間隔）
        self.max_requests_per_hour = 7000  # 120req/min * 60min - 安全マージン
        self.current_season = None  # キャッシュ用
        self.sync_seasonal_ratings_task.start()  # タスクを開始
        
    def cog_unload(self):
        """Cogがアンロードされる時の処理"""
        self.sync_seasonal_ratings_task.cancel()
        if self.api:
            asyncio.create_task(self.api.close())

    async def get_current_season_from_seq(self):
        """SEQギルドから最新シーズンを取得"""
        try:
            logger.info("[SeasonalRatingSync] SEQギルドから最新シーズンを取得中...")
            guild_data = await self.api.get_guild_by_prefix("SEQ")
            
            if not guild_data:
                logger.error("[SeasonalRatingSync] SEQギルドの取得に失敗")
                return None
            
            season_ranks = guild_data.get("seasonRanks", {})
            if not season_ranks:
                logger.error("[SeasonalRatingSync] SEQギルドにseasonRanksがありません")
                return None
            
            # 最新のシーズン番号を取得
            season_numbers = [int(k) for k in season_ranks.keys() if k.isdigit()]
            if not season_numbers:
                logger.error("[SeasonalRatingSync] SEQギルドに有効なシーズンデータがありません")
                return None
            
            latest_season = max(season_numbers)
            logger.info(f"[SeasonalRatingSync] 最新シーズン: Season {latest_season}")
            
            # DBに保存
            update_current_season(latest_season)
            self.current_season = latest_season  # キャッシュ更新
            
            return latest_season
            
        except Exception as e:
            logger.error(f"SEQギルドから最新シーズン取得エラー: {e}", exc_info=True)
            return None

    async def get_season_ratings_by_season(self, guild_data, target_seasons=None):
        """指定シーズンのみのSeasonal Ratingを取得"""
        try:
            season_ranks = guild_data.get("seasonRanks", {})
            if not season_ranks:
                return []
            
            ratings = []
            for season_str, season_data in season_ranks.items():
                if season_str.isdigit():
                    season_number = int(season_str)
                    
                    # 対象シーズンが指定されている場合、それ以外はスキップ
                    if target_seasons and season_number not in target_seasons:
                        continue
                    
                    rating = season_data.get("rating", 0)
                    if rating > 0:  # 0より大きいレートのみ保存
                        ratings.append((season_number, rating))
            
            return ratings
        except Exception as e:
            logger.warning(f"指定シーズンRating取得エラー: {e}")
            return []
    
    async def process_guild_batch(self, guild_names, batch_num, total_batches, target_seasons):
        """ギルドバッチを処理（効率化版：対象シーズンのみ）"""
        processed = 0
        errors = 0
        saved_records = 0
        
        logger.debug(f"[SeasonalRatingSync] バッチ {batch_num}/{total_batches} 開始 ({len(guild_names)}ギルド)")
        
        for i, guild_name in enumerate(guild_names):
            try:
                # レート制限遵守
                if i > 0:
                    await asyncio.sleep(self.request_delay)
                
                # ギルド詳細データを取得
                guild_data = await self.api.get_guild_by_name(guild_name)
                if not guild_data:
                    errors += 1
                    continue
                
                # データ抽出
                guild_prefix = guild_data.get("prefix", "")
                if not guild_prefix:
                    errors += 1
                    continue
                
                # 対象シーズンのみのレーティングを取得
                season_ratings = await self.get_season_ratings_by_season(guild_data, target_seasons)
                
                if season_ratings:
                    # 対象シーズンのデータを保存
                    for season_number, rating in season_ratings:
                        try:
                            upsert_guild_seasonal_rating(guild_name, guild_prefix, season_number, rating)
                            saved_records += 1
                        except Exception as db_e:
                            logger.error(f"ギルド {guild_name} S{season_number} データ保存エラー: {db_e}")
                    
                    processed += 1
                
            except Exception as e:
                logger.error(f"ギルド {guild_name} 処理中エラー: {e}")
                errors += 1
                continue
        
        if batch_num % 5 == 0:  # 5バッチおきにログ
            logger.info(f"[SeasonalRatingSync] バッチ {batch_num} 完了: {processed}ギルド成功, {saved_records}レコード保存, {errors}エラー")
        
        return processed, errors

    async def get_unprocessed_guilds(self, all_guilds, limit=None, target_seasons=None):
        """未処理ギルドを取得（効率化版：対象シーズンベース）"""
        try:
            if not target_seasons:
                target_seasons = [self.current_season] if self.current_season else []
            
            conn = get_conn()
            with conn.cursor() as cur:
                # 対象シーズンで24時間以内に更新されたギルドを取得
                season_placeholders = ','.join(['%s'] * len(target_seasons))
                query = f"""
                    SELECT DISTINCT guild_name FROM guild_seasonal_ratings 
                    WHERE season_number IN ({season_placeholders}) 
                    AND updated_at > %s
                """
                params = target_seasons + [datetime.now() - timedelta(hours=24)]
                cur.execute(query, params)
                
                recent_updates = set(row[0] for row in cur.fetchall())
            conn.close()
            
            # 未処理のギルドを抽出
            unprocessed = [guild for guild in all_guilds if guild not in recent_updates]
            
            # 制限を適用
            if limit is not None:
                unprocessed = unprocessed[:limit]
            
            processed_count = len(all_guilds) - len(unprocessed)
            completion_rate = (processed_count / len(all_guilds) * 100) if all_guilds else 0
            
            logger.info(f"[SeasonalRatingSync] 📋 対象シーズン{target_seasons}の状況:")
            logger.info(f"  • 全ギルド: {len(all_guilds):,}個")
            logger.info(f"  • 処理済み: {processed_count:,}個 ({completion_rate:.1f}%)")
            logger.info(f"  • 未処理: {len(unprocessed):,}個")
            
            return unprocessed
            
        except Exception as e:
            logger.error(f"未処理ギルド取得エラー: {e}")
            return all_guilds[:limit] if limit else all_guilds

    @tasks.loop(hours=1)  # 1時間ごとに実行（効率化）
    async def sync_seasonal_ratings_task(self):
        """定期実行されるSeasonal Rating同期タスク（効率化版）"""
        try:
            logger.info("[SeasonalRatingSync] 効率化同期開始")
            start_time = datetime.now()
            
            # APIクライアントを初期化
            if not self.api:
                self.api = WynncraftAPI()
            
            # 最新シーズンを取得
            current_season = await self.get_current_season_from_seq()
            if not current_season:
                logger.error("[SeasonalRatingSync] 最新シーズンの取得に失敗")
                return
            
            # 全ギルドリストを取得
            logger.info("[SeasonalRatingSync] 全ギルドリスト取得中...")
            all_guilds_data = await self.api.get_all_guilds()
            if not all_guilds_data:
                logger.error("[SeasonalRatingSync] 全ギルドリスト取得失敗")
                return
            
            all_guild_names = list(all_guilds_data.keys())
            total_guilds = len(all_guild_names)
            logger.info(f"[SeasonalRatingSync] 総ギルド数: {total_guilds:,}個")
            
            # 収集対象シーズンを決定
            target_seasons = []
            
            # 最新シーズンは常に対象
            target_seasons.append(current_season)
            
            # 過去シーズンで未完了のものも対象に追加
            for season in range(max(1, current_season - 3), current_season):
                if not is_season_completed(season):
                    target_seasons.append(season)
                    logger.info(f"[SeasonalRatingSync] Season {season} は未完了のため収集対象に追加")
            
            logger.info(f"[SeasonalRatingSync] 収集対象シーズン: {target_seasons}")
            
            # 未処理ギルドを特定（1時間に処理可能な分）
            max_guilds_this_run = min(total_guilds, 6000)  # 1時間で6000ギルド
            unprocessed_guilds = await self.get_unprocessed_guilds(
                all_guild_names, 
                limit=max_guilds_this_run,
                target_seasons=target_seasons
            )
            
            if not unprocessed_guilds:
                logger.info("[SeasonalRatingSync] 処理対象ギルドがありません")
                return
            
            logger.info(f"[SeasonalRatingSync] 今回処理: {len(unprocessed_guilds):,}ギルド")
            
            # バッチ処理
            total_processed = 0
            total_errors = 0
            batch_size = 100
            batches = [unprocessed_guilds[i:i + batch_size] 
                      for i in range(0, len(unprocessed_guilds), batch_size)]
            
            for batch_num, batch in enumerate(batches, 1):
                processed, errors = await self.process_guild_batch(
                    batch, batch_num, len(batches), target_seasons
                )
                total_processed += processed
                total_errors += errors
                
                # 進捗報告
                if batch_num % 10 == 0:
                    progress = (batch_num / len(batches)) * 100
                    logger.info(f"[SeasonalRatingSync] 進捗: {progress:.1f}% ({total_processed:,}ギルド完了)")
                
                # バッチ間のクールダウン
                if batch_num < len(batches):
                    await asyncio.sleep(1)
            
            elapsed = datetime.now() - start_time
            
            logger.info(f"[SeasonalRatingSync] ✅ 効率化同期完了")
            logger.info(f"  📊 結果: {total_processed:,}成功, {total_errors:,}エラー")
            logger.info(f"  ⏱️ 実行時間: {elapsed}")
            logger.info(f"  🎯 対象シーズン: {target_seasons}")
            
        except Exception as e:
            logger.error(f"SeasonalRatingSync効率化実行エラー: {e}", exc_info=True)

    @sync_seasonal_ratings_task.before_loop
    async def before_sync_seasonal_ratings_task(self):
        """タスク開始前の待機（Botの準備が整うまで待つ）"""
        await self.bot.wait_until_ready()
        logger.info("[SeasonalRatingSync] タスクを開始します")

    @commands.command(name="sync_ratings", help="Seasonal Ratingの手動同期を実行（効率化版）")
    @commands.is_owner()
    async def manual_sync_ratings(self, ctx, limit: int = 1000):
        """管理者用の手動同期コマンド（効率化版）"""
        try:
            await ctx.send("🚀 効率化版Seasonal Rating同期を開始...")
            
            if not self.api:
                self.api = WynncraftAPI()
            
            # 最新シーズンを取得
            status_msg = await ctx.send("🔍 SEQギルドから最新シーズンを取得中...")
            current_season = await self.get_current_season_from_seq()
            if not current_season:
                await status_msg.edit(content="❌ 最新シーズンの取得に失敗しました")
                return
            
            # 全ギルドリスト取得
            await status_msg.edit(content=f"📡 全ギルドリスト取得中... (最新シーズン: S{current_season})")
            all_guilds_data = await self.api.get_all_guilds()
            if not all_guilds_data:
                await status_msg.edit(content="❌ 全ギルドリスト取得に失敗しました")
                return
            
            all_guild_names = list(all_guilds_data.keys())
            total_guilds = len(all_guild_names)
            
            # 対象シーズンを決定
            target_seasons = [current_season]
            
            # 過去の未完了シーズンも追加
            for season in range(max(1, current_season - 2), current_season):
                if not is_season_completed(season):
                    target_seasons.append(season)
            
            # 未処理ギルドを取得
            unprocessed_guilds = await self.get_unprocessed_guilds(
                all_guild_names, 
                limit=limit, 
                target_seasons=target_seasons
            )
            
            await status_msg.edit(content=f"📊 **効率化同期情報:**\n"
                                         f"• 総ギルド数: **{total_guilds:,}**\n"
                                         f"• 対象シーズン: **{target_seasons}**\n"
                                         f"• 処理予定: **{len(unprocessed_guilds):,}**ギルド")
            
            if len(unprocessed_guilds) == 0:
                await ctx.send("✅ 対象シーズンは全ギルド処理済みです！")
                return
            
            # 推定時間計算
            estimated_minutes = len(unprocessed_guilds) / 120
            time_str = f"{estimated_minutes:.1f}分" if estimated_minutes < 60 else f"{estimated_minutes/60:.1f}時間"
            
            await ctx.send(f"🔄 **{len(unprocessed_guilds):,}ギルド**を処理開始\n"
                          f"⏱️ 推定時間: {time_str}\n"
                          f"🎯 対象: {target_seasons}")
            
            # 処理実行
            processed, errors = await self.process_guild_batch(
                unprocessed_guilds, 1, 1, target_seasons
            )
            
            # 結果表示
            success_rate = (processed / len(unprocessed_guilds) * 100) if unprocessed_guilds else 0
            
            await ctx.send(f"✅ **効率化同期完了**\n"
                          f"📈 成功: **{processed:,}**ギルド ({success_rate:.1f}%)\n"
                          f"❌ エラー: **{errors:,}**\n"
                          f"🎯 対象シーズン: **{target_seasons}**")
            
        except Exception as e:
            logger.error(f"効率化手動同期エラー: {e}", exc_info=True)
            await ctx.send(f"❌ 効率化同期中にエラーが発生しました: {e}")

    @commands.command(name="check_db", help="データベースの状況を確認（効率化版）")
    @commands.is_owner()
    async def check_database(self, ctx):
        """データベースの状況確認（効率化版）"""
        try:
            from lib.db import get_available_seasons, get_guild_count_by_season, get_current_season
            
            status_msg = await ctx.send("📊 効率化版データベース状況を確認中...")
            
            if not self.api:
                self.api = WynncraftAPI()
            
            # 最新シーズンを確認
            api_current_season = await self.get_current_season_from_seq()
            db_current_season = get_current_season()
            
            # 全ギルドリスト取得
            all_guilds_data = await self.api.get_all_guilds()
            total_guilds_api = len(all_guilds_data.keys()) if all_guilds_data else 0
            
            # 利用可能シーズンを取得
            seasons = get_available_seasons()
            
            info_text = f"📊 **効率化版データベース状況:**\n\n"
            info_text += f"🌍 **Wynncraft総ギルド数:** {total_guilds_api:,}個\n"
            info_text += f"🆕 **API最新シーズン:** Season {api_current_season}\n"
            info_text += f"💾 **DB記録シーズン:** Season {db_current_season}\n"
            
            if not seasons:
                info_text += "\n❌ **データベース:** データなし"
                await status_msg.edit(content=info_text)
                return
            
            info_text += f"📈 **利用可能シーズン数:** {len(seasons)}個\n\n"
            
            # 最新5シーズンの詳細
            total_records = 0
            for season in seasons[:5]:
                count = get_guild_count_by_season(season)
                completion = (count / total_guilds_api * 100) if total_guilds_api > 0 else 0
                status_icon = "🟢" if completion > 95 else "🟡" if completion > 50 else "🔴"
                info_text += f"{status_icon} **Season {season}:** {count:,}ギルド ({completion:.1f}%)\n"
                total_records += count
            
            if len(seasons) > 5:
                info_text += f"... 他{len(seasons)-5}シーズン\n"
            
            # 現在の効率化状況
            if api_current_season and all_guilds_data:
                target_seasons = [api_current_season]
                unprocessed_guilds = await self.get_unprocessed_guilds(
                    list(all_guilds_data.keys()),
                    limit=None,
                    target_seasons=target_seasons
                )
                current_season_completion = ((total_guilds_api - len(unprocessed_guilds)) / total_guilds_api * 100) if total_guilds_api > 0 else 0
                
                info_text += f"\n🎯 **効率化戦略状況:**\n"
                info_text += f"• 最新シーズン完了率: **{current_season_completion:.1f}%**\n"
                info_text += f"• 未処理ギルド: **{len(unprocessed_guilds):,}**個\n"
                
                if len(unprocessed_guilds) > 0:
                    estimated_minutes = len(unprocessed_guilds) / 120
                    time_str = f"{estimated_minutes:.1f}分" if estimated_minutes < 60 else f"{estimated_minutes/60:.1f}時間"
                    info_text += f"• 推定完了時間: **{time_str}**\n"
            
            info_text += f"\n📊 **総レコード数:** {total_records:,}個"
            
            await status_msg.edit(content=info_text)
            
        except Exception as e:
            logger.error(f"効率化DB確認エラー: {e}", exc_info=True)
            await ctx.send(f"❌ データベース確認中にエラーが発生しました: {e}")

async def setup(bot):
    await bot.add_cog(SeasonalRatingSync(bot))