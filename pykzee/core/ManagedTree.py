import asyncio
import collections
import functools

import importlib
import inspect
import logging
import sys
import traceback

from pyimmutable import ImmutableDict, ImmutableList

from pykzee.core.common import (
    call_soon,
    getDataForPath,
    makePath,
    pathToString,
    PathType,
    print_exception_task_callback,
    sanitize,
    setDataForPath,
    StateType,
    Undefined,
)
from pykzee.core import AttachedInfo


SubscriptionSlot = collections.namedtuple(
    "SubscriptionSlot", ("path", "directory", "stateType")
)


class Subscription:
    __slots__ = (
        "plugin",
        "slots",
        "callback",
        "__currentState",
        "__reportedState",
        "disabled",
    )

    def __init__(self, plugin, slots, callback, state, initial: bool):
        if (
            type(slots) != tuple
            or any(type(slot) is not SubscriptionSlot for slot in slots)
            or type(state) != ImmutableList
            or not len(slots) == len(state)
        ):
            logging.error(  # FIXME REMOVE
                "Subscription constructor called with invalid arguments: "
                f"slots={ slots !r} len(state)={ len(state) }"
            )
            raise Exception(
                "Subscription constructor called with invalid arguments: "
                f"slots={ slots !r} len(state)={ len(state) }"
            )
        self.plugin = plugin
        self.slots = slots
        self.callback = callback
        self.__currentState = state
        self.__reportedState = (
            ImmutableList(Undefined for _ in slots) if initial else state
        )
        self.disabled = False

    def setCurrentState(self, idx, state):
        old_state = self.__currentState
        self.__currentState = self.__currentState.set(idx, state)
        return self.__currentState is not old_state

    def getState(self):
        return self.__currentState

    def update(self):
        if (
            not self.disabled
            and self.__reportedState is not self.__currentState
        ):
            self.__reportedState = self.__currentState
            call_soon(self.callback, *self.__currentState)


class Directory:
    __slots__ = (
        "parent",
        "pathElement",
        "subdirectories",
        "subscriptions",
        "state",
    )

    def __init__(self, parent, path_element):
        self.parent = parent
        self.pathElement = path_element
        self.subdirectories = {}
        self.subscriptions = set()  # (sub, idx) tuples
        self.state = Undefined
        try:
            if type(parent.state) in (ImmutableDict, ImmutableList):
                self.state = parent.state[path_element]
        except Exception:
            ...

    def get(self, path: PathType, *, create=True):
        d = self
        for p in path:
            sd = d.subdirectories.get(p)
            if sd is None:
                if create:
                    sd = d.subdirectories[p] = type(self)(d, p)
                else:
                    return
            d = sd
        return d

    def garbageCollect(self):
        parent = self.parent
        if (
            parent is not None
            and not self.subdirectories
            and not self.subscriptions
        ):
            del parent.subdirectories[self.pathElement]
            self.parent = None
            parent.garbageCollect()

    def update(self, new_state, updated_subscriptions):
        if new_state is self.state:
            return

        for sub, idx in self.subscriptions:
            if sub.setCurrentState(idx, new_state):
                updated_subscriptions.add(sub)

        for key, subdir in self.subdirectories.items():
            sdata = Undefined
            if type(new_state) in (ImmutableDict, ImmutableList):
                try:
                    sdata = new_state[key]
                except Exception:
                    ...

            subdir.update(sdata, updated_subscriptions)

        self.state = new_state


class Command:
    __slots__ = "path", "name", "function", "doc", "plugin", "disabled"

    def __init__(self, path, name, function, doc, plugin):
        self.path = path
        self.name = name
        self.function = function
        self.doc = doc
        self.plugin = plugin
        self.disabled = False


class PluginInfo:
    __slots__ = (
        "path",
        "configuration",
        "plugin_object",
        "state",
        "subscriptions",
        "registeredCommands",
        "disabled",
    )

    def __init__(self, *, path, configuration):
        self.path = path
        self.configuration = configuration
        self.plugin_object = None
        self.state = None
        self.subscriptions = set()
        self.registeredCommands = set()
        self.disabled = False


class ManagedTree:
    __slots__ = """
    __rawState __unresolvedState __resolvedState __nextState __realpath
    __rawSubscriptionRoot __unresolvedSubscriptionRoot
    __resolvedSubscriptionRoot __updatedSubscriptions
    __pluginInfos __pluginList __coreState __corePluginPaths
    __commands
    __stateUpdateEvent __stateUpdateTask
    """.strip().split()

    def __init__(self):
        self.__rawState = self.__unresolvedState = ImmutableDict()
        self.__resolvedState = self.__nextState = ImmutableDict()
        self.__realpath = makePath
        self.__rawSubscriptionRoot = Directory(None, None)
        self.__unresolvedSubscriptionRoot = Directory(None, None)
        self.__resolvedSubscriptionRoot = Directory(None, None)
        self.__updatedSubscriptions = set()
        self.__pluginInfos = []
        self.__pluginList = ImmutableList()
        self.__coreState = ImmutableDict(commands=ImmutableDict())
        self.__corePluginPaths = []
        self.__commands = {}  # path -> {name: Command}
        self.__stateUpdateEvent = asyncio.Event()
        self.__stateUpdateTask = asyncio.create_task(
            self.__stateUpdateTaskImpl()
        )
        self.__stateUpdateTask.add_done_callback(print_exception_task_callback)

    def get(self, path: PathType, *, type: StateType = StateType.RESOLVED):
        if type == StateType.RAW:
            state = self.__rawState
        elif type == StateType.UNRESOLVED:
            state = self.__unresolvedState
        else:
            state = self.__resolvedState

        return getDataForPath(state, makePath(path))

    def setRawState(self, new_state: ImmutableDict):
        new_state = sanitize(new_state)
        if self.__rawState is new_state:
            return
        if not new_state.isImmutableJson:
            raise Exception("Invalid state (not immutable json)")
        self.__rawState = new_state
        self.__updatePlugins()

        for plugin in self.__pluginInfos:
            new_state = setDataForPath(new_state, plugin.path, plugin.state)

        self.__nextState = new_state
        self.__setCore(
            ("plugins",),
            {pathToString(path): config for path, config in self.__pluginList},
            force=True,
        )

    def __updatePlugins(self):
        new_plugin_list = AttachedInfo.plugins(self.__rawState)
        if new_plugin_list is self.__pluginList:
            return

        old_plugin_infos = self.__pluginInfos
        new_plugin_infos = []
        core_plugin_paths = []
        old_index = new_index = 0

        while True:
            have_old = old_index < len(old_plugin_infos)
            have_new = new_index < len(new_plugin_list)

            if not (have_new or have_old):
                break

            if have_new:
                npath, nconfig = new_plugin_list[new_index]
                if nconfig["__plugin__"] == "core-plugin":
                    core_plugin_paths.append(npath)
                    new_index += 1
                    continue

            if have_old:
                opi = old_plugin_infos[old_index]

            if not have_new or (have_old and opi.path < npath):
                self.__removePlugin(opi)
                old_index += 1
            elif not have_old or (have_new and npath < opi.path):
                new_plugin_infos.append(self.__newPlugin(npath, nconfig))
                new_index += 1
            else:
                old_index += 1
                new_index += 1
                new_plugin_infos.append(self.__updatePlugin(opi, nconfig))

        self.__pluginInfos = new_plugin_infos
        self.__pluginList = new_plugin_list
        self.__corePluginPaths = core_plugin_paths

    def __removePlugin(self, plugin_info):
        plugin_info.disabled = True
        plugin_object = plugin_info.plugin_object
        subscriptions = plugin_info.subscriptions
        registered_commands = plugin_info.registeredCommands

        plugin_info.configuration = None
        plugin_info.plugin_object = None
        plugin_info.state = None
        plugin_info.subscriptions = set()
        plugin_info.registeredCommands = set()

        for sub in subscriptions:
            self.unsubscribe(sub)

        for cmd in registered_commands:
            self.unregisterCommand(cmd)

        try:
            plugin_object.shutdown()
        except Exception:
            ...

    def __newPlugin(self, path, config):
        plugin_info = PluginInfo(path=path, configuration=config)

        try:
            plugin_identifier = config["__plugin__"]
            module, class_ = plugin_identifier.rsplit(".", 1)

            sys.modules.pop(module, None)
            mod = importlib.import_module(module)

            PluginType = getattr(mod, class_)
            plugin_info.plugin_object = PluginType(
                path=path,
                get=lambda path: self.get(path),
                subscribe=lambda callback, *paths, initial=True: (
                    self.subscribe(
                        plugin_info, paths, callback, initial=initial
                    )
                ),
                command=self.command,
                set_state=functools.partial(
                    self.__setPluginState, plugin_info
                ),
                register_command=functools.partial(
                    self.registerCommand, plugin_info
                ),
            )
            plugin_info.plugin_object.init(config)
        except Exception as ex:
            traceback.print_exc()
            plugin_info.state = ImmutableDict(
                exception=str(ex), traceback=traceback.format_exc()
            )
            plugin_info.plugin_object = None

        return plugin_info

    def __updatePlugin(self, plugin_info, new_config):
        if plugin_info.configuration is new_config:
            return plugin_info

        try:
            if (
                plugin_info.configuration["__plugin__"]
                == new_config["__plugin__"]
                and plugin_info.plugin_object
                and hasattr(plugin_info.plugin_object, "updateConfig")
                and plugin_info.plugin_object.updateConfig(new_config)
            ):
                plugin_info.configuration = new_config
                return plugin_info
        except Exception:
            traceback.print_exc()

        self.__removePlugin(plugin_info)
        return self.__newPlugin(plugin_info.path, new_config)

    def __set(self, path: PathType, value):
        self.__nextState = setDataForPath(self.__nextState, path, value)
        if self.__nextState is not self.__unresolvedState:
            self.__stateUpdateEvent.set()

    def __setCore(self, path, value, *, force=True):
        new_core_state = setDataForPath(self.__coreState, path, value)
        if self.__coreState is new_core_state and not force:
            return
        self.__coreState = new_core_state
        next_state = self.__nextState
        for core_plugin_path in self.__corePluginPaths:
            next_state = setDataForPath(
                next_state, core_plugin_path, new_core_state
            )
        if next_state is not self.__nextState:
            self.__nextState = next_state
            self.__stateUpdateEvent.set()

    def __setPluginState(self, plugin_info, path, value):
        if not plugin_info.disabled:
            new_state = setDataForPath(
                plugin_info.state, path, value, undefined=None
            )
            if plugin_info.state is not new_state:
                plugin_info.state = new_state
                self.__set(plugin_info.path, new_state)

    def command(self, path, cmd):
        return self.__commands[makePath(path)][cmd].function

    def subscribe(
        self,
        plugin_info,
        paths,
        callback,
        *,
        initial=True,
        state_type=StateType.RESOLVED,
    ):
        if plugin_info.disabled:
            raise Exception("disabled plugin must not subscribe")
        slots = tuple(
            SubscriptionSlot(
                path,
                (
                    self.__rawSubscriptionRoot
                    if state_type == StateType.RAW
                    else self.__unresolvedSubscriptionRoot
                    if state_type == StateType.UNRESOLVED
                    else self.__resolvedSubscriptionRoot
                ).get(path),
                state_type,
            )
            for path in map(makePath, paths)
        )
        state = ImmutableList(slot.directory.state for slot in slots)
        sub = Subscription(plugin_info, slots, callback, state, initial)
        plugin_info.subscriptions.add(sub)
        for idx, slot in enumerate(slots):
            slot.directory.subscriptions.add((sub, idx))
        if initial:
            self.__updatedSubscriptions.add(sub)
            self.__stateUpdateEvent.set()
        return lambda: self.unsubscribe(sub)

    def unsubscribe(self, sub):
        sub.disabled = True
        for idx, slot in enumerate(sub.slots):
            slot.directory.subscriptions.discard((sub, idx))
            slot.directory.garbageCollect()
        sub.plugin.subscriptions.discard(sub)

    def registerCommand(
        self, plugin_info, path, name, function, *, doc=Undefined
    ):
        if plugin_info.disabled:
            raise Exception("Disabled plugins cannot register commands")
        path = plugin_info.path + makePath(path)
        if doc is Undefined:
            doc = function.__doc__
        sig = inspect.signature(function)
        try:
            path_commands = self.__commands[path]
        except KeyError:
            path_commands = self.__commands[path] = {}
        if name in path_commands:
            raise Exception("Command { path }:{ name } already registered")
        cmd = Command(path, name, function, doc, plugin_info)
        plugin_info.registeredCommands.add(cmd)
        path_commands[name] = cmd

        self.__setCore(
            ("commands", pathToString(path), name),
            {"doc": doc, "signature": str(sig)},
        )

        return lambda: self.__unregisterCommand(cmd)

    def unregisterCommand(self, cmd):
        if cmd.disabled:
            return
        cmd.disabled = True
        path_commands = self.__commands[cmd.path]
        path_commands.pop(cmd.name)
        cmd.plugin.registeredCommands.discard(cmd)
        if not path_commands:
            del self.__commands[cmd.path]
            self.__setCore(("commands", pathToString(cmd.path)), Undefined)
        else:
            self.__setCore(
                ("commands", pathToString(cmd.path), cmd.name), Undefined
            )

    async def __stateUpdateTaskImpl(self):
        while True:
            await self.__stateUpdateEvent.wait()
            self.__stateUpdateEvent.clear()

            next_state = self.__nextState
            if self.__unresolvedState is not next_state:
                for path_prefix in self.__corePluginPaths:
                    next_state = setDataForPath(
                        next_state,
                        path_prefix + ("symlinks",),
                        AttachedInfo.symlinkInfoDict(next_state),
                    )

                self.__resolvedState = AttachedInfo.resolved(next_state)
                self.__realpath = (
                    lambda func: lambda path: func(makePath(path))
                )(AttachedInfo.realpath(next_state))
                self.__unresolvedState = self.__nextState = next_state

            self.__rawSubscriptionRoot.update(
                self.__rawState, self.__updatedSubscriptions
            )
            self.__unresolvedSubscriptionRoot.update(
                self.__unresolvedState, self.__updatedSubscriptions
            )
            self.__resolvedSubscriptionRoot.update(
                self.__resolvedState, self.__updatedSubscriptions
            )

            updated_subscriptions = self.__updatedSubscriptions
            self.__updatedSubscriptions = set()
            for sub in updated_subscriptions:
                sub.update()
