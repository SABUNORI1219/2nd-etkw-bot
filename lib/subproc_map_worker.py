import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pickle
import ctypes
from lib.map_renderer import MapRenderer

def main():
    params = pickle.load(sys.stdin.buffer)
    renderer = MapRenderer()
    mode = params.get("mode", "map")

    result = {}
    if mode == "map":
        file, embed = renderer.create_territory_map(
            territory_data=params['territory_data'],
            territories_to_render=params['territories_to_render'],
            guild_color_map=params['guild_color_map'],
            show_held_time=params.get('show_held_time', False)
        )
        map_bytes = None
        if file is not None:
            file.fp.seek(0)
            map_bytes = file.fp.read()
            file.close()
        result = {
            'map_bytes': map_bytes,
            'embed_dict': embed.to_dict() if embed else None,
        }
    elif mode == "single":
        image_bytes = renderer.create_single_territory_image(
            params['territory'],
            params['territory_data'],
            params['guild_color_map'],
        )
        img_bytes = None
        if image_bytes:
            image_bytes.seek(0)
            img_bytes = image_bytes.read()
            image_bytes.close()
        result = {
            'image_bytes': img_bytes,
        }
    pickle.dump(result, sys.stdout.buffer)

    try:
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except Exception:
        pass

if __name__ == "__main__":
    main()
