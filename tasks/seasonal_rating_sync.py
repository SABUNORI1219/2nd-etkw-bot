import asyncio
import logging
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from lib.api_stocker import WynncraftAPI
from lib.db import upsert_guild_seasonal_rating, get_conn
import psycopg2

logger = logging.getLogger(__name__)

class SeasonalRatingSync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api = None
        self.request_delay = 0.6  # 1分間100リクエスト制限（安全マージン含む）
        self.batch_size = 500  # 1回の実行で処理するギルド数
        self.sync_seasonal_ratings_task.start()  # タスクを開始
        
    def cog_unload(self):
        """Cogがアンロードされる時の処理"""
        self.sync_seasonal_ratings_task.cancel()
        if self.api:
            asyncio.create_task(self.api.close())
            
    async def get_all_season_ratings(self, guild_data):
        """ギルドデータから全シーズンのSeasonal Ratingを取得"""
        try:
            season_ranks = guild_data.get("seasonRanks", {})
            if not season_ranks:
                return []
            
            # 全シーズンデータを取得
            ratings = []
            for season_str, season_data in season_ranks.items():
                if season_str.isdigit():
                    season_number = int(season_str)
                    rating = season_data.get("rating", 0)
                    if rating > 0:  # 0より大きいレートのみ保存
                        ratings.append((season_number, rating))
            
            return ratings
        except Exception as e:
            logger.warning(f"Seasonal Ratings取得エラー: {e}")
            return []
    
    async def process_guild_batch(self, guild_names, batch_num, total_batches):
        """ギルドバッチを処理"""
        processed = 0
        errors = 0
        saved_records = 0
        
        logger.info(f"[SeasonalRatingSync] バッチ {batch_num}/{total_batches} 開始 ({len(guild_names)}ギルド)")
        
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
                season_ratings = await self.get_all_season_ratings(guild_data)
                
                if season_ratings and guild_prefix:
                    # 全シーズンのデータを保存
                    for season_number, rating in season_ratings:
                        upsert_guild_seasonal_rating(guild_name, guild_prefix, season_number, rating)
                        saved_records += 1
                    
                    processed += 1
                    
                    if processed % 50 == 0:
                        logger.info(f"[SeasonalRatingSync] 進捗: {processed}/{len(guild_names)} 処理完了 ({saved_records}レコード保存)")
                        
            except Exception as e:
                logger.error(f"ギルド {guild_name} 処理中エラー: {e}")
                errors += 1
                continue
        
        logger.info(f"[SeasonalRatingSync] バッチ {batch_num} 完了: {processed}ギルド成功, {saved_records}レコード保存, {errors}エラー")
        return processed, errors
    
    async def get_unprocessed_guilds(self, all_guilds, limit=None):
        """未処理または更新が必要なギルドを取得"""
        try:
            conn = get_conn()
            with conn.cursor() as cur:
                # 過去24時間以内に更新されたギルドを除外
                cur.execute("""
                    SELECT DISTINCT guild_name FROM guild_seasonal_ratings 
                    WHERE updated_at > %s
                """, (datetime.now() - timedelta(hours=24),))
                
                recent_updates = set(row[0] for row in cur.fetchall())
            conn.close()
            
            # 未処理のギルドを抽出
            unprocessed = [guild for guild in all_guilds if guild not in recent_updates]
            
            if limit:
                unprocessed = unprocessed[:limit]
                
            logger.info(f"[SeasonalRatingSync] 未処理ギルド: {len(unprocessed)}個 (全体: {len(all_guilds)})")
            return unprocessed
            
        except Exception as e:
            logger.error(f"未処理ギルド取得エラー: {e}")
            return all_guilds[:limit] if limit else all_guilds

    @tasks.loop(hours=6)  # 6時間ごとに実行
    async def sync_seasonal_ratings_task(self):
        """定期実行されるSeasonal Rating同期タスク"""
        try:
            logger.info("[SeasonalRatingSync] 定期同期開始")
            start_time = datetime.now()
            
            # APIクライアントを初期化
            if not self.api:
                self.api = WynncraftAPI()
            
            # 全ギルドリストを取得
            all_guilds_data = await self.api.get_all_guilds()
            if not all_guilds_data:
                logger.error("[SeasonalRatingSync] 全ギルドリスト取得失敗")
                return
            
            # ギルド名リストを抽出
            all_guild_names = list(all_guilds_data.keys())
            logger.info(f"[SeasonalRatingSync] 総ギルド数: {len(all_guild_names)}")
            
            # 未処理ギルドを特定（バッチサイズで制限）
            unprocessed_guilds = await self.get_unprocessed_guilds(
                all_guild_names, 
                limit=self.batch_size
            )
            
            if not unprocessed_guilds:
                logger.info("[SeasonalRatingSync] 処理対象ギルドがありません")
                return
            
            # バッチ処理
            total_processed = 0
            total_errors = 0
            batches = [unprocessed_guilds[i:i + 100]  # 小さなバッチで分割
                      for i in range(0, len(unprocessed_guilds), 100)]
            
            for batch_num, batch in enumerate(batches, 1):
                processed, errors = await self.process_guild_batch(
                    batch, batch_num, len(batches)
                )
                total_processed += processed
                total_errors += errors
                
                # バッチ間のクールダウン（レート制限緩和）
                if batch_num < len(batches):
                    await asyncio.sleep(10)
            
            elapsed = datetime.now() - start_time
            logger.info(f"[SeasonalRatingSync] 定期同期完了: {total_processed}成功, {total_errors}エラー, 実行時間: {elapsed}")
            
        except Exception as e:
            logger.error(f"SeasonalRatingSync定期実行エラー: {e}", exc_info=True)

    @sync_seasonal_ratings_task.before_loop
    async def before_sync_seasonal_ratings_task(self):
        """タスク開始前の待機（Botの準備が整うまで待つ）"""
        await self.bot.wait_until_ready()
        logger.info("[SeasonalRatingSync] タスクを開始します")

    @commands.command(name="sync_ratings", help="Seasonal Ratingの手動同期を実行")
    @commands.is_owner()
    async def manual_sync_ratings(self, ctx, limit: int = 50):
        """管理者用の手動同期コマンド"""
        try:
            await ctx.send(f"Seasonal Ratingの手動同期を開始します（最大{limit}ギルド）...")
            
            if not self.api:
                self.api = WynncraftAPI()
            
            # 全ギルドリスト取得
            all_guilds_data = await self.api.get_all_guilds()
            if not all_guilds_data:
                await ctx.send("❌ 全ギルドリスト取得に失敗しました")
                return
            
            all_guild_names = list(all_guilds_data.keys())
            unprocessed_guilds = await self.get_unprocessed_guilds(all_guild_names, limit=limit)
            
            if not unprocessed_guilds:
                await ctx.send("✅ 処理対象ギルドがありません")
                return
            
            # 処理実行
            processed, errors = await self.process_guild_batch(unprocessed_guilds, 1, 1)
            await ctx.send(f"✅ 手動同期完了: {processed}成功, {errors}エラー")
            
        except Exception as e:
            logger.error(f"手動同期エラー: {e}", exc_info=True)
            await ctx.send(f"❌ 手動同期中にエラーが発生しました: {e}")

async def setup(bot):
    await bot.add_cog(SeasonalRatingSync(bot))