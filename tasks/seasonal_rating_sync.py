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
        self.request_delay = 0.55  # 120req/min = 2req/sec、安全マージン含む（0.55秒間隔）
        self.max_requests_per_hour = 7000  # 120req/min * 60min - 安全マージン
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
            
            logger.debug(f"seasonRanksキーの内容: {list(season_ranks.keys())}")
            
            # 全シーズンデータを取得
            ratings = []
            for season_str, season_data in season_ranks.items():
                if season_str.isdigit():
                    season_number = int(season_str)
                    rating = season_data.get("rating", 0)
                    logger.debug(f"Season {season_number}: rating={rating}")
                    if rating > 0:  # 0より大きいレートのみ保存
                        ratings.append((season_number, rating))
                else:
                    logger.debug(f"数字以外のキー発見: {season_str}")
            
            logger.debug(f"最終的に取得したレーティング: {ratings}")
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
                    logger.warning(f"ギルド {guild_name} のデータ取得失敗")
                    errors += 1
                    continue
                
                # データ抽出
                guild_prefix = guild_data.get("prefix", "")
                if not guild_prefix:
                    logger.warning(f"ギルド {guild_name} にプレフィックスが設定されていません")
                    errors += 1
                    continue
                
                season_ratings = await self.get_all_season_ratings(guild_data)
                
                if not season_ratings:
                    logger.debug(f"ギルド {guild_name}({guild_prefix}) にSeasonal Ratingデータがありません")
                    # エラー数には含めない（データがないのは正常な場合もある）
                else:
                    logger.debug(f"ギルド {guild_name}({guild_prefix}) から{len(season_ratings)}個のシーズンデータを取得")
                    
                    # 全シーズンのデータを保存
                    for season_number, rating in season_ratings:
                        try:
                            upsert_guild_seasonal_rating(guild_name, guild_prefix, season_number, rating)
                            saved_records += 1
                        except Exception as db_e:
                            logger.error(f"ギルド {guild_name} S{season_number} データ保存エラー: {db_e}")
                    
                    processed += 1
                    
                if (i + 1) % 25 == 0:  # 25個おきにログ
                    logger.info(f"[SeasonalRatingSync] 進捗: {i+1}/{len(guild_names)} 処理中... ({processed}成功, {saved_records}レコード保存)")
                        
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
            
            # 制限を適用（Noneの場合は制限しない）
            if limit is not None:
                unprocessed = unprocessed[:limit]
                
            processed_count = len(all_guilds) - len(unprocessed)
            completion_rate = (processed_count / len(all_guilds) * 100) if all_guilds else 0
            
            logger.info(f"[SeasonalRatingSync] 📋 ギルド状況:")
            logger.info(f"  • 全ギルド: {len(all_guilds):,}個")
            logger.info(f"  • 処理済み: {processed_count:,}個 ({completion_rate:.1f}%)")
            logger.info(f"  • 未処理: {len(unprocessed):,}個")
            
            return unprocessed
            
        except Exception as e:
            logger.error(f"未処理ギルド取得エラー: {e}")
            # エラーの場合は全ギルドを返す（安全側に倒す）
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
            
            # 全ギルドリストを取得して総数を把握
            logger.info("[SeasonalRatingSync] 全ギルドリスト取得開始...")
            all_guilds_data = await self.api.get_all_guilds()
            if not all_guilds_data:
                logger.error("[SeasonalRatingSync] 全ギルドリスト取得失敗")
                return
            
            all_guild_names = list(all_guilds_data.keys())
            total_guilds = len(all_guild_names)
            logger.info(f"[SeasonalRatingSync] 🎯 取得したWynncraftの総ギルド数: {total_guilds:,}個")
            
            # 未処理ギルドを特定（制限なし、全て取得）
            unprocessed_guilds = await self.get_unprocessed_guilds(all_guild_names, limit=None)
            unprocessed_count = len(unprocessed_guilds)
            
            logger.info(f"[SeasonalRatingSync] 📊 処理が必要なギルド: {unprocessed_count:,}個（全体の{unprocessed_count/total_guilds*100:.1f}%）")
            
            if unprocessed_count == 0:
                logger.info("[SeasonalRatingSync] 処理対象ギルドがありません")
                return
            
            # 今回の実行で処理するギルド数を計算（6時間でmax 42000リクエスト）
            max_guilds_this_run = min(unprocessed_count, self.max_requests_per_hour * 6)
            guilds_to_process = unprocessed_guilds[:max_guilds_this_run]
            
            logger.info(f"[SeasonalRatingSync] 🚀 今回処理するギルド数: {len(guilds_to_process):,}個")
            
            # バッチ処理（100ギルドずつ）
            total_processed = 0
            total_errors = 0
            batch_size = 100
            batches = [guilds_to_process[i:i + batch_size] 
                      for i in range(0, len(guilds_to_process), batch_size)]
            
            logger.info(f"[SeasonalRatingSync] 📦 {len(batches)}個のバッチに分割して処理開始")
            
            for batch_num, batch in enumerate(batches, 1):
                logger.info(f"[SeasonalRatingSync] バッチ {batch_num}/{len(batches)} 開始...")
                processed, errors = await self.process_guild_batch(
                    batch, batch_num, len(batches)
                )
                total_processed += processed
                total_errors += errors
                
                # 進捗報告
                progress_percent = (batch_num / len(batches)) * 100
                logger.info(f"[SeasonalRatingSync] 📈 進捗: {progress_percent:.1f}% ({total_processed:,}ギルド処理完了)")
                
                # バッチ間のクールダウン（APIレート制限緩和）
                if batch_num < len(batches):
                    await asyncio.sleep(2)
            
            elapsed = datetime.now() - start_time
            remaining_guilds = total_guilds - total_processed
            
            logger.info(f"[SeasonalRatingSync] ✅ 定期同期完了")
            logger.info(f"  📊 処理結果: {total_processed:,}ギルド成功, {total_errors:,}エラー")
            logger.info(f"  ⏱️ 実行時間: {elapsed}")
            logger.info(f"  🎯 進捗: {total_processed}/{total_guilds} ({total_processed/total_guilds*100:.1f}%)")
            if remaining_guilds > 0:
                estimated_hours = (remaining_guilds / self.max_requests_per_hour) if self.max_requests_per_hour > 0 else 0
                logger.info(f"  📅 残り{remaining_guilds:,}ギルド（推定完了まで{estimated_hours:.1f}時間）")
            
        except Exception as e:
            logger.error(f"SeasonalRatingSync定期実行エラー: {e}", exc_info=True)

    @sync_seasonal_ratings_task.before_loop
    async def before_sync_seasonal_ratings_task(self):
        """タスク開始前の待機（Botの準備が整うまで待つ）"""
        await self.bot.wait_until_ready()
        logger.info("[SeasonalRatingSync] タスクを開始します")

    @commands.command(name="sync_ratings", help="Seasonal Ratingの手動同期を実行")
    @commands.is_owner()
    async def manual_sync_ratings(self, ctx, limit: int = 500):
        """管理者用の手動同期コマンド"""
        try:
            await ctx.send(f"🚀 Seasonal Ratingの手動同期を開始します...")
            
            if not self.api:
                self.api = WynncraftAPI()
            
            # 全ギルドリスト取得
            status_msg = await ctx.send("📡 全ギルドリストを取得中...")
            all_guilds_data = await self.api.get_all_guilds()
            if not all_guilds_data:
                await status_msg.edit(content="❌ 全ギルドリスト取得に失敗しました")
                return
            
            all_guild_names = list(all_guilds_data.keys())
            total_guilds = len(all_guild_names)
            
            # 未処理ギルドを取得
            unprocessed_guilds = await self.get_unprocessed_guilds(all_guild_names, limit=None)
            unprocessed_count = len(unprocessed_guilds)
            
            await status_msg.edit(content=f"📊 **ギルド状況:**\n"
                                         f"• 総ギルド数: **{total_guilds:,}**\n"
                                         f"• 未処理ギルド: **{unprocessed_count:,}**\n"
                                         f"• 処理済み率: **{((total_guilds-unprocessed_count)/total_guilds*100):.1f}%**")
            
            if unprocessed_count == 0:
                await ctx.send("✅ 全ギルドが処理済みです！")
                return
            
            # 実際に処理するギルド数を決定
            guilds_to_process = unprocessed_guilds[:limit]
            processing_count = len(guilds_to_process)
            
            # 推定時間計算（120req/min）
            estimated_minutes = processing_count / 120
            estimated_time_str = f"{estimated_minutes:.1f}分" if estimated_minutes < 60 else f"{estimated_minutes/60:.1f}時間"
            
            await ctx.send(f"🔄 **{processing_count:,}ギルド**を処理します\n"
                          f"⏱️ 推定時間: {estimated_time_str}\n"
                          f"🎯 レート制限: 120req/min遵守")
            
            # 処理実行
            processed, errors = await self.process_guild_batch(guilds_to_process, 1, 1)
            
            # 結果表示
            success_rate = (processed / processing_count * 100) if processing_count > 0 else 0
            remaining_after = unprocessed_count - processed
            
            await ctx.send(f"✅ **手動同期完了**\n"
                          f"📈 成功: **{processed:,}**ギルド ({success_rate:.1f}%)\n"
                          f"❌ エラー: **{errors:,}**\n"
                          f"📊 残り未処理: **{remaining_after:,}**ギルド")
            
        except Exception as e:
            logger.error(f"手動同期エラー: {e}", exc_info=True)
            await ctx.send(f"❌ 手動同期中にエラーが発生しました: {e}")

    @commands.command(name="check_db", help="データベースの状況を確認")
    @commands.is_owner()
    async def check_database(self, ctx):
        """データベースの状況確認"""
        try:
            from lib.db import get_available_seasons, get_guild_count_by_season
            
            # APIから総ギルド数も取得してみる
            status_msg = await ctx.send("📊 データベース状況を確認中...")
            
            if not self.api:
                self.api = WynncraftAPI()
            
            # 全ギルドリスト取得（総数把握のため）
            all_guilds_data = await self.api.get_all_guilds()
            total_guilds_api = len(all_guilds_data.keys()) if all_guilds_data else 0
            
            # 利用可能シーズンを取得
            seasons = get_available_seasons()
            
            if not seasons:
                await status_msg.edit(content="📊 **データベース状況:**\n❌ データが存在しません")
                return
            
            info_text = f"📊 **データベース状況:**\n\n"
            info_text += f"🌍 **Wynncraft総ギルド数:** {total_guilds_api:,}個\n"
            info_text += f"📈 **利用可能シーズン数:** {len(seasons)}個\n\n"
            
            total_records = 0
            unique_guilds = set()
            
            for season in seasons[:10]:  # 最新10シーズンのみ表示
                count = get_guild_count_by_season(season)
                info_text += f"**Season {season}:** {count:,}ギルド\n"
                total_records += count
            
            if len(seasons) > 10:
                info_text += f"... 他{len(seasons)-10}シーズン\n"
            
            # 未処理ギルドを確認
            if all_guilds_data:
                all_guild_names = list(all_guilds_data.keys())
                unprocessed_guilds = await self.get_unprocessed_guilds(all_guild_names, limit=None)
                processed_guilds = total_guilds_api - len(unprocessed_guilds)
                completion_rate = (processed_guilds / total_guilds_api * 100) if total_guilds_api > 0 else 0
                
                info_text += f"\n🎯 **処理進捗:**\n"
                info_text += f"• 処理済み: {processed_guilds:,}ギルド ({completion_rate:.1f}%)\n"
                info_text += f"• 未処理: {len(unprocessed_guilds):,}ギルド\n"
                
                if len(unprocessed_guilds) > 0:
                    estimated_hours = len(unprocessed_guilds) / 120 / 60  # 120req/min
                    info_text += f"• 推定完了時間: {estimated_hours:.1f}時間\n"
            
            info_text += f"\n📊 **総レコード数:** {total_records:,}個"
            
            await status_msg.edit(content=info_text)
            
        except Exception as e:
            logger.error(f"DB確認エラー: {e}", exc_info=True)
            await ctx.send(f"❌ データベース確認中にエラーが発生しました: {e}")

async def setup(bot):
    await bot.add_cog(SeasonalRatingSync(bot))