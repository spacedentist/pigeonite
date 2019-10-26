import asyncio
import traceback

import watchdog.events
import watchdog.observers

from pykzee.common import print_exception_task_callback
from pykzee.JsonFileTree import load_json_tree


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
        self.__setRawState(await load_json_tree("."))

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
