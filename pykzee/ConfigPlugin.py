import asyncio
import json
import logging
import os
import stat

import aiofiles
import aionotify

from pykzee.Plugin import Plugin
from pykzee.common import print_exception_task_callback

directory_watch_flags = (
    aionotify.Flags.MODIFY
    | aionotify.Flags.CREATE
    | aionotify.Flags.DELETE
    | aionotify.Flags.MOVED_FROM
    | aionotify.Flags.MOVED_TO
)


class ConfigPlugin(Plugin):
    async def init(self, path, directory, delay=2):
        self.__directory = directory
        self.__delay = delay

        mount = self.mount(path)
        self.__set = mount.set
        self.__set((), await load_json_tree(directory))
        self.__rereadEvent = asyncio.Event()

        watcher = self.__watcher = aionotify.Watcher()
        await watcher.setup(asyncio.get_event_loop())
        self.__watchTask = asyncio.create_task(self.__watchTaskImpl())
        self.__watchTask.add_done_callback(print_exception_task_callback)
        self.__rereadTask = asyncio.create_task(self.__rereadTaskImpl())
        self.__rereadTask.add_done_callback(print_exception_task_callback)

        dirs = [directory]
        watched_dirs = self.__watched_dirs = set()
        while dirs:
            d = dirs.pop()
            print(d)
            watcher.watch(d, directory_watch_flags)
            watched_dirs.add(d)
            dirs.extend(
                path
                for path in (os.path.join(d, fn) for fn in os.listdir(d))
                if os.path.isdir(path)
            )

    async def shutdown(self):
        self.__watchTask.cancel()
        self.__rereadTaskImpl.cancel()

    async def __watchTaskImpl(self):
        while True:
            event = await self.__watcher.get_event()
            logging.debug(
                f"read fs event: flags={ hex(event.flags) } "
                f"name={ event.name !r} alias={ event.alias !r}"
            )
            if event.flags & aionotify.Flags.ISDIR:
                d = os.path.join(event.alias, event.name)
                if event.flags & aionotify.Flags.CREATE:
                    if d not in self.__watched_dirs:
                        try:
                            self.__watcher.watch(d, directory_watch_flags)
                        except Exception as ex:
                            logging.warning(
                                f"Exception caught installing watch { d !r}: "
                                f"{ ex !r}"
                            )
                        else:
                            self.__watched_dirs.add(d)
                elif event.flags & aionotify.Flags.DELETE:
                    if d in self.__watched_dirs:
                        self.__watched_dirs.remove(d)
                        try:
                            self.__watcher.unwatch(d)
                        except Exception as ex:
                            logging.warning(
                                f"Exception caught uninstalling watch { d !r}: "
                                f"{ ex !r}"
                            )
            self.__rereadEvent.set()

    async def __rereadTaskImpl(self):
        while True:
            await self.__rereadEvent.wait()
            await asyncio.sleep(self.__delay)
            self.__rereadEvent.clear()
            try:
                new_state = await load_json_tree(self.__directory)
            except Exception as ex:
                logging.warning(f"Error reading configuration: { ex !r}")
                continue
            self.__set((), new_state)


async def load_json_tree(fspath):
    mode = os.stat(fspath).st_mode
    if stat.S_ISREG(mode):
        async with aiofiles.open(fspath) as f:
            return json.loads(await f.read())
    elif stat.S_ISDIR(mode):
        result = {}
        for filename in os.listdir(fspath):
            if filename.endswith("~"):
                continue
            result[filename] = await load_json_tree(
                os.path.join(fspath, filename)
            )
        return result
    else:
        logging.warning(f"ConfigPlugin: ignoring non-regular file f{ fspath }")
