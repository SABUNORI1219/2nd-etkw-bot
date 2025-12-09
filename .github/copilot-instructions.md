# Minister Chikuwa (2nd-etkw-bot) Development Guide

## Communication Guidelines
- 日本語で回答すること。
- 必ず使用者の指示に従うこと。指示外の行動はしない、ないしは必ず確認を取る。
- 断片的にコードを出すのではなく、修正が必要な箇所が入っている関数あるいはファイル全体を常に提示すること。
- 使用者の言っていることの意図がわかりにくい場合、必ず確認を取ること。
- Botを動かしているサービスのメモリとCPUは限られているため、常に軽量化を意識したコードを書くこと。
- できないことはできないと正直に答えること。
- 推論は避け、必ず事実に基づいて回答すること。
- 適当なことを言わないこと。
- 回答に自信がない場合は、その旨を明記すること。
- コードの整合性を必ず保つこと。

## Architecture Overview
- **Discord Bot**: Python-based bot using discord.py with cogs architecture for Empire of TKW [ETKW] guild
- **API Integration**: Wynncraft API client (`lib/api_stocker.py`) with automatic retry logic and caching (`lib/cache_handler.py`)
- **Database**: PostgreSQL with psycopg2, connection via `DATABASE_URL` environment variable
- **Rendering**: PIL-based image generation for guild profiles, banners, maps, and player cards
- **Tasks**: Background async tasks for member sync, territory tracking, and raid monitoring

## Key Components
- `main.py`: Entry point with bot setup, memory monitoring, persistent view registration
- `cogs/`: Discord command modules using discord.py cogs pattern
- `lib/`: Core libraries - API, database, rendering, caching, utilities
- `tasks/`: Background async tasks for data synchronization
- `assets/`: Static resources - fonts (Minecraftia), images, territory data

## Development Patterns

### Logging
- **CRITICAL**: Use `logger.info()`, `logger.warning()`, `logger.error()` exclusively
- **NEVER use**: `print()` or `logger.debug()`
- Logger setup in `logger_setup.py` with standardized formatting
- Example: `logger.info(f"[MemberSync] {mcid} ランク {db_rank}→{api_rank} で更新")`

### Error Handling & API Calls
- API calls use exponential backoff with specific retry logic in `WynncraftAPI._make_request()`
- Handle 404/400 as expected states, retry on 5xx/timeout
- Cache API responses with 1-minute expiration via `CacheHandler`
- Memory monitoring with `log_mem()` for image generation tasks

### Database Patterns
- Use `get_conn()` context manager from `lib/db.py`
- All queries use parameterized statements
- Database schema auto-created via `create_table()`
- Key tables: `guild_raid_history`, `linked_members`, `player_server_log`

### Image Rendering
- PIL-based rendering with custom font loading (Minecraftia)
- Memory-conscious rendering with explicit cleanup
- Template pattern: load assets → compose layers → return BytesIO
- Examples: `GuildProfileRenderer`, `BannerRenderer`, `MapRenderer`

### Discord Views & Modals
- Persistent views registered in `main.py` via `register_persistent_views()`
- Custom IDs for button persistence across bot restarts
- Application workflow: modal → database storage → staff review → role assignment

## Environment & Configuration
- Render.com deployment with `keep_alive.py` web server
- Environment variables: `DISCORD_TOKEN`, `DATABASE_URL`, `WYNN_API_TOKEN`
- Guild-specific constants in `config.py`: role mappings, emoji IDs, server IDs
- Memory limits enforced (450MB limit, 100MB for map generation)

## Testing & Debugging
- Use `test_cog.py` for experimental features
- Memory debugging with `psutil` integration
- Database connection testing via connection retry logic
- API testing with rate limit handling

## Common Workflows
- **Adding commands**: Create in appropriate cog, use `@app_commands.command()`
- **Database changes**: Update schema in `create_table()`, add helper functions in `db.py`
- **API integration**: Extend `WynncraftAPI` with caching support
- **Image generation**: Follow PIL patterns in `lib/` renderers with memory cleanup
