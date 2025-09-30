import sys
import os
import pickle
from lib.map_renderer import MapRenderer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    # 標準入力からパラメータ受け取り
    params = pickle.load(sys.stdin.buffer)
    renderer = MapRenderer()
    # 画像生成
    file, embed = renderer.create_territory_map(
        territory_data=params['territory_data'],
        territories_to_render=params['territories_to_render'],
        guild_color_map=params['guild_color_map'],
        owned_territories_map=params['owned_territories_map']
    )
    # 結果をファイルバイト列で返す（Discord.Fileはファイル or BytesIOなのでバイト列送信）
    map_bytes = None
    if file is not None:
        file.fp.seek(0)
        map_bytes = file.fp.read()
        file.close()
    pickle.dump({
        'map_bytes': map_bytes,
        'embed_dict': embed.to_dict() if embed else None,
    }, sys.stdout.buffer)

if __name__ == "__main__":
    main()
