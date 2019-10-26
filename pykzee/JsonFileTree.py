import json
import logging
import os
import stat

import aiofiles


async def load_json_tree(fspath):
    mode = os.stat(fspath).st_mode
    if stat.S_ISREG(mode):
        async with aiofiles.open(fspath) as f:
            return json.loads(await f.read())
    elif stat.S_ISDIR(mode):
        result = {}
        for filename in os.listdir(fspath):
            if filename.startswith(".") or filename.endswith("~"):
                continue
            result[filename] = await load_json_tree(
                os.path.join(fspath, filename)
            )
        return result
    else:
        logging.warning(f"ConfigPlugin: ignoring non-regular file f{ fspath }")
