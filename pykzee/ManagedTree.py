import asyncio
import functools
import inspect
import logging

from pyimmutable import ImmutableDict, ImmutableList

from pykzee.common import (
    InvalidPathElement,
    PathType,
    Undefined,
    call_soon,
    pathToString,
    setDataForPath,
)
from pykzee.Plugin import Plugin
from pykzee.Tree import Tree


class Subscription:
    __slots__ = (
        "plugin",
        "paths",
        "directories",
        "callback",
        "__currentState",
        "__reportedState",
        "disabled",
    )

    def __init__(
        self, plugin, paths, directories, callback, state, initial: bool
    ):
        if (
            type(paths) != tuple
            or type(directories) != tuple
            or type(state) != ImmutableList
            or not len(paths) == len(directories) == len(state)
        ):
            logging.error(  # FIXME REMOVE
                "Subscription constructor called with invalid arguments: "
                f"paths={ paths !r} directories={ directories !r}"
            )
            raise Exception(
                "Subscription constructor called with invalid arguments: "
                f"paths={ paths !r} directories={ directories !r}"
            )
        self.plugin = plugin
        self.paths = paths
        self.directories = directories
        self.callback = callback
        self.__currentState = state
        self.__reportedState = (
            ImmutableList([Undefined] * len(paths)) if initial else state
        )
        self.disabled = False

    def setCurrentState(self, idx, state):
        self.__currentState = self.__currentState.set(idx, state)

    def needsUpdate(self):
        return self.__reportedState is not self.__currentState

    def updated(self):
        self.__reportedState = self.__currentState

    def getState(self):
        return self.__currentState


class Mount:
    __slots__ = "plugin", "directory", "tree", "disabled"

    def __init__(self, plugin, directory, tree):
        self.plugin = plugin
        self.directory = directory
        self.tree = tree
        self.disabled = False


class Directory:
    __slots__ = "parent subdirectories mount subscriptions".split()

    def __init__(self, parent):
        self.parent = parent
        self.subdirectories = {}
        self.mount = None
        self.subscriptions = set()  # (sub, idx) tuples


class Command:
    __slots__ = "path", "name", "function", "doc", "disabled"

    def __init__(self, path, name, function, doc):
        self.path = path
        self.name = name
        self.function = function
        self.doc = doc
        self.disabled = False


class PluginInfo:
    __slots__ = "subscriptions", "mounts", "plugInsAdded", "disabled", "plugin"

    def __init__(self):
        self.subscriptions = set()
        self.mounts = set()
        self.plugInsAdded = set()
        self.disabled = False


class ManagedTree:
    __slots__ = """
    __state __root __pluginInfos __commands
    __subscriptionCheckScheduled __subscriptionCheckLock
    __corePluginInfo __coreMount __coreSet
    """.strip().split()

    def __init__(self):
        self.__state = ImmutableDict()
        self.__root = Directory(None)
        self.__pluginInfos = set()
        self.__commands = {}  # path -> {name: Command}
        self.__subscriptionCheckScheduled = False
        self.__subscriptionCheckLock = asyncio.Lock()

        self.addPlugin(Plugin, None)
        self.__corePluginInfo, = list(self.__pluginInfos)
        self.__coreMount = self.__corePluginInfo.plugin.mount(("core",))
        self.__coreSet = self.__coreMount.set

    def get(self, path: PathType):
        data = self.__state
        for p in path:
            if type(p) not in (str, int):
                raise InvalidPathElement(p)
            try:
                data = data[p]
            except (KeyError, IndexError, TypeError):
                return Undefined
        return data

    def set(self, path: PathType, value):
        new_state = setDataForPath(self.__state, path, value)
        if not new_state.isImmutableJson:
            raise Exception("invalid data")
        if self.__state is new_state:
            return
        old_data = self.__state
        data = self.__state = new_state
        directory = self.__root

        self.__scheduleSubscriptionCheck()
        self.__setSubscriptionsState(directory, data)

        for p in path:
            directory = directory.subdirectories.get(p)
            if directory is None:
                return
            if data is not Undefined:
                try:
                    data = data[p]
                except Exception:
                    data = Undefined
            if old_data is not Undefined:
                try:
                    old_data = old_data[p]
                except Exception:
                    old_data = Undefined
            self.__setSubscriptionsState(directory, data)
        self.__recurseToUpdateSubscriptionState(directory, data, old_data)

    def command(self, path, cmd):
        return self.__commands[path][cmd].function

    def subscribe(self, plugin_info, paths, callback, initial=True):
        if plugin_info.disabled or plugin_info not in self.__pluginInfos:
            raise Exception("disabled/unregistered plugin must not subscribe")
        directories = tuple(self.__getDirectory(path) for path in paths)
        state = ImmutableList(self.get(path) for path in paths)
        sub = Subscription(
            plugin_info, paths, directories, callback, state, initial
        )
        plugin_info.subscriptions.add(sub)
        for idx, directory in enumerate(directories):
            directory.subscriptions.add((sub, idx))
        if initial:
            self.__scheduleSubscriptionCheck()
        return lambda: self.unsubscribe(sub)

    def unsubscribe(self, sub):
        sub.disabled = True
        for idx, directory in enumerate(sub.directories):
            directory.subscriptions.discard((sub, idx))
        sub.plugin.subscriptions.discard(sub)

    def mount(self, plugin_info, path):
        directory = self.__getDirectory(path)
        if any(d.mount for d in self.__relatedDirectories(directory)):
            raise Exception("conflicting mount")

        mount = Mount(plugin_info, directory, Tree(self, path))
        plugin_info.mounts.add(mount)
        directory.mount = mount
        return mount.tree.getAccessProxy()._replace(
            deactivate=functools.partial(self.unmount, mount)
        )

    def unmount(self, mount):
        if mount.disabled:
            return
        mount.disabled = True
        mount.directory.mount = None
        mount.plugin.mounts.discard(mount)
        mount.tree.deactivate()

    # def registerCommand(self, mount, path, name, function, doc):
    def registerCommand(self, path, name, function, doc=Undefined):
        if doc is Undefined:
            doc = function.__doc__
        sig = inspect.signature(function)
        cmd = Command(path, name, function, doc)
        try:
            path_commands = self.__commands[path]
        except KeyError:
            path_commands = self.__commands[path] = {}
        if name in path_commands:
            raise Exception("Command { path }:{ name } already registered")
        path_commands[name] = cmd

        self.__coreSet(
            ("commands", pathToString(path), name),
            {"doc": doc, "signature": str(sig)},
        )

        def unregisterCommand():
            if cmd.disabled:
                return
            cmd.disabled = True
            path_commands = self.__commands[cmd.path]
            path_commands.pop(cmd.name)
            if not path_commands:
                del self.__commands[cmd.path]
                self.__coreSet(("commands", pathToString(cmd.path)), Undefined)
            else:
                self.__coreSet(
                    ("commands", pathToString(cmd.path), cmd.name), Undefined
                )

        return unregisterCommand

    def addPlugin(
        self, PluginType: type, added_by: PluginInfo, *args, **kwargs
    ):
        if added_by is not None:
            if added_by.disabled:
                raise Exception("Disabled plugin tried to register a plugin")
            if added_by not in self.__pluginInfos:
                raise Exception("Parent plugin not registered with this tree")
        if not issubclass(PluginType, Plugin):
            raise TypeError("Plugin type must derive from Plugin class")
        plugin_info = PluginInfo()
        plugin_info.plugin = PluginType(
            get=lambda path: self.get(path),
            subscribe=lambda callback, *paths, initial=True: self.subscribe(
                plugin_info, paths, callback, initial
            ),
            mount=lambda path: self.mount(plugin_info, path),
            addPlugin=lambda PluginType, *args, **kwargs: self.addPlugin(
                PluginType, plugin_info, *args, **kwargs
            ),
            removePlugin=lambda: self.__removePlugin(plugin_info),
            command=lambda path, cmd: self.command(path, cmd),
        )
        self.__pluginInfos.add(plugin_info)
        if added_by is not None:
            added_by.plugInsAdded.add(plugin_info)
        init = getattr(plugin_info.plugin, "init", None)
        if init is not None:
            call_soon(init, *args, **kwargs)
        elif args or kwargs:
            logging.warning("plugin has no init method - ignoring arguments")
        return lambda: self.__removePlugin(plugin_info)

    def __removePlugin(self, plugin_info):
        if plugin_info.disabled:
            return
        self.__pluginInfos.remove(plugin_info)
        plugin_info.disabled = True

        for p in plugin_info.plugInsAdded:
            self.__removePlugin(p)

        plugin_info.subscriptions = set()
        for sub in plugin_info.subscriptions:
            self.unsubscribe(sub)

        plugin_info.mounts = set()
        for mount in plugin_info.mounts:
            self.unmount(mount)

        shutdown = getattr(plugin_info.plugin, "shutdown", None)
        if shutdown is not None:
            call_soon(shutdown)

    def __scheduleSubscriptionCheck(self):
        if not self.__subscriptionCheckScheduled:
            self.__subscriptionCheckScheduled = True
            call_soon(self.__subscriptionCheck)

    async def __subscriptionCheck(self):
        async with self.__subscriptionCheckLock:
            self.__subscriptionCheckScheduled = False

            for sub in list(
                sub
                for plugin_info in self.__pluginInfos
                for sub in plugin_info.subscriptions
            ):
                if sub.disabled:
                    continue
                if sub.needsUpdate():
                    call_soon(sub.callback, *sub.getState())
                    sub.updated()

    def __getDirectory(self, path: PathType, create=True):
        d = self.__root
        for p in path:
            sd = d.subdirectories.get(p)
            if sd is None:
                if create:
                    sd = d.subdirectories[p] = Directory(d)
                else:
                    return
            d = sd
        return d

    def __relatedDirectories(self, directory):
        yield directory

        parent = directory.parent
        while parent is not None:
            yield parent
            parent = parent.parent

        subdirs = list(directory.subdirectories.values())
        while subdirs:
            sd = subdirs.pop()
            yield sd
            subdirs.extend(sd.subdirectories.values())

    @staticmethod
    def __setSubscriptionsState(directory, state):
        for sub, idx in directory.subscriptions:
            sub.setCurrentState(idx, state)

    @classmethod
    def __recurseToUpdateSubscriptionState(cls, directory, data, old_data):
        for name, subdir in directory.subdirectories.items():
            if type(data) in (ImmutableDict, ImmutableList):
                try:
                    sdata = data[name]
                except Exception:
                    sdata = Undefined
            else:
                sdata = Undefined

            if type(old_data) in (ImmutableDict, ImmutableList):
                try:
                    old_sdata = old_data[name]
                except Exception:
                    old_sdata = Undefined
            else:
                old_sdata = Undefined

            if sdata is old_sdata:
                continue

            cls.__setSubscriptionsState(subdir, sdata)
            cls.__recurseToUpdateSubscriptionState(subdir, sdata, old_sdata)
