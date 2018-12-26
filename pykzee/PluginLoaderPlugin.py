import asyncio
import functools
import importlib
import logging
import sys
import time
import traceback

from pyimmutable import ImmutableDict

from pykzee.Plugin import Plugin
from pykzee.common import Undefined


class PluginLoaderPlugin(Plugin):
    def init(self, configPath, mountPath):
        self.lock = asyncio.Lock()
        self.configState = ImmutableDict()
        self.plugins = {}
        self.unsubscribe = self.subscribe(self.stateUpdate, configPath)
        self.mnt = self.mount(mountPath)

    def unloadModule(self, key):
        unload = self.plugins.pop(key, None)
        if unload is not None:
            unload()
        self.mnt.set((key,), Undefined)

    def loadModule(self, key, config):
        if key in self.plugins:
            self.unloadModule(key)
        info = {"time": time.time(), "config": config}
        try:
            module = config.get("module", Undefined)
            class_ = config.get("class", Undefined)
            if module is Undefined or class_ is Undefined:
                error(
                    info,
                    f"PluginLoaderPlugin: { key !r}: plugin description "
                    "is missing module or class key",
                )
                return
            try:
                sys.modules.pop(module, None)
                mod = importlib.import_module(module)
            except Exception as ex:
                traceback.print_exc()
                error(
                    info,
                    f"PluginLoaderPlugin: { key !r}: error importing module: "
                    f"{ ex !r}",
                )
                return
            try:
                cls = getattr(mod, class_)
            except Exception as ex:
                error(
                    info,
                    f"PluginLoaderPlugin: { key !r}: error accessing class "
                    f"{ class_ !r} in module { module !r}: { ex !r}",
                )
                return
            params = config.get("params", {})
            try:
                remove_plugin = self.addPlugin(cls, **params)
            except Exception as ex:
                remove_plugin = noop
                error(
                    info,
                    f"PluginLoaderPlugin: { key !r}: adding plugin failed: "
                    f"{ ex !r}",
                )
            else:
                p = ", ".join(f"{k}={v!r}" for k, v in params.items())
                logging.info(
                    f"PluginLoaderPlugin: { key !r}: added plugin "
                    f"{ module }:{ class_}({ p })"
                )
            remove_command = self.mnt.registerCommand(
                (key,),
                "reload",
                functools.partial(self.reloadModule, key),
                "Reload this module",
            )
            self.plugins[key] = lambda: (remove_plugin(), remove_command())
        except Exception as ex:
            info["exception"] = repr(ex)
        finally:
            self.mnt.set((key,), info)

    def reloadModule(self, key):
        try:
            self.loadModule(key, self.configState[key])
        except Exception:
            traceback.print_exc()
            raise

    async def stateUpdate(self, new_state):
        async with self.lock:
            if type(new_state) is not ImmutableDict:
                new_state = ImmutableDict()

            loaded_plugin_keys = set(self.configState)
            new_plugin_keys = set(new_state) - loaded_plugin_keys
            unload_plugin_keys = loaded_plugin_keys.difference(new_state)
            check_update_keys = loaded_plugin_keys.intersection(new_state)

            for key in sorted(unload_plugin_keys):
                logging.info(f"PluginLoaderPlugin: { key !r}: unloading")
                self.unloadModule(key)

            for key in sorted(check_update_keys):
                if new_state[key] is not self.configState[key]:
                    logging.info(f"PluginLoaderPlugin: { key !r}: unloading")
                    new_plugin_keys.add(key)
                    self.unloadModule(key)

            for key in sorted(new_plugin_keys):
                self.loadModule(key, new_state[key])

            self.configState = new_state


def error(info, message):
    info["error"] = message
    logging.error(message)


def noop():
    ...
