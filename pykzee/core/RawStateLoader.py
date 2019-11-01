import asyncio
import json
import logging
import os
import stat
import traceback

import aiofiles
from pyimmutable import ImmutableDict
import watchdog.events
import watchdog.observers

from pykzee.core.common import print_exception_task_callback


class RawStateLoader:
    def __init__(self, set_raw_state):
        self.__setRawState = set_raw_state
        self.__shutdown = asyncio.Future()
        self.__reread_tree_event = asyncio.Event()

        asyncio.create_task(self.__rereadTaskImpl()).add_done_callback(
            print_exception_task_callback
        )

        observer = self.__observer = watchdog.observers.Observer()
        loop = asyncio.get_event_loop()
        observer.schedule(
            WatchdogEventHandler(
                lambda: loop.call_soon_threadsafe(self.__reread_tree_event.set)
            ),
            ".",
            recursive=True,
        )
        observer.start()

    def __del__(self):
        self.__observer.stop()
        self.__observer.join()

    async def readStateFromDisk(self):
        self.__reread_tree_event.clear()
        self.__setRawState(
            ImmutableDict([x async for x in load_state_tree(".")])
        )

    async def run(self):
        return await self.__shutdown

    async def __rereadTaskImpl(self):
        while True:
            await self.__reread_tree_event.wait()
            await asyncio.sleep(2)
            if self.__reread_tree_event.is_set():
                try:
                    await self.readStateFromDisk()
                except Exception:
                    traceback.print_exc()


class WatchdogEventHandler(watchdog.events.FileSystemEventHandler):
    def __init__(self, callback):
        self.__callback = callback

    def on_any_event(self, event):
        self.__callback()


async def load_state_tree(dirpath):
    for filename in sorted(os.listdir(dirpath)):
        if filename.startswith(".") or filename.endswith("~"):
            continue

        key = filename
        fspath = os.path.join(dirpath, filename)
        mode = os.stat(fspath).st_mode

        if stat.S_ISDIR(mode):
            yield key, ImmutableDict(
                [x async for x in load_state_tree(fspath)]
            )
        elif stat.S_ISREG(mode):
            async with aiofiles.open(fspath) as f:
                content = await f.read()
            if key.endswith(".json"):
                key = key[:-5]
                content = json.loads(content)
            elif key.endswith(".txt"):
                key = key[:-4]
            yield key, content
        else:
            logging.warning(
                f"ConfigPlugin: ignoring non-regular file f{ fspath }"
            )
