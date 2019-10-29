import collections

from pyimmutable import ImmutableDict
from pykzee.common import Undefined, setDataForPath


class Tree:
    class RegisteredCommand:
        __slots__ = "function", "doc", "unregister", "disabled"

        def __init__(self, function, doc, unregister):
            self.function = function
            self.doc = doc
            self.unregister = unregister
            self.disabled = False

    TreeAccess = collections.namedtuple(
        "TreeAccess",
        (
            "set",
            "submitState",
            "registerCommand",
            "createSubtree",
            "clear",
            "deactivate",
        ),
    )

    def __init__(self, parent, path, *, immediate_updates=True):
        self.__parentSet = parent.set
        self.__parentRegisterCommand = parent.registerCommand
        self.__path = path
        self.__state = ImmutableDict()
        self.__reportedState = Undefined
        self.__registeredCommands = {}
        self.__immediate_updates = immediate_updates
        self.__deactivated = False
        self.__hidden = False

    @property
    def path(self):
        return self.__path

    def getAccessProxy(self):
        return self.TreeAccess(
            self.set,
            self.submitState,
            self.registerCommand,
            self.createSubtree,
            self.clear,
            self.deactivate,
        )

    def set(self, path, value):
        self.__state = setDataForPath(self.__state, path, value)
        if self.__immediate_updates:
            self.submitState()

    def registerCommand(self, path, name, function, doc=Undefined):
        if doc is Undefined:
            doc = function.__doc__
        existing_rc = self.__registeredCommands.get((path, name))
        if existing_rc is not None:
            existing_rc.disabled = True
            existing_rc.unregister()
        if self.__hidden:
            unregister = no_op
        else:
            unregister = self.__parentRegisterCommand(
                self.__path + path, name, function, doc
            )
        rc = self.RegisteredCommand(function, doc, unregister)
        self.__registeredCommands[path, name] = rc

        def unregister_command():
            if not rc.disabled:
                rc.disabled = True
                del self.__registeredCommands[path, name]
                rc.unregister()

        return unregister_command

    def createSubtree(self, path, *, immediate_updates=True):
        return Tree(self, path, immediate_updates=immediate_updates)

    def clear(self):
        for rc in self.__registeredCommands.values():
            rc.disabled = True
            rc.unregister()
        self.__registeredCommands = {}
        self.__state = ImmutableDict()
        self.__reportedState = Undefined
        self.__parentSet(self.__path, Undefined)

    def deactivate(self):
        if not self.__deactivated:
            self.clear()
            self.__parentSet = self.__parentRegisterCommand = raise_deactivated
            self.__deactivated = True

    def hide(self):
        if self.__hidden:
            return
        for rc in self.__registeredCommands.values():
            rc.unregister()
            rc.unregister = no_op
        self.__parentSet(self.__path, Undefined)
        self.__hidden = True

    def show(self, new_path=None):
        if not self.__hidden and (new_path is None or new_path == self.__path):
            return
        self.hide()
        if new_path is not None:
            self.__path = new_path
        self.__parentSet(self.__path, self.__state)
        self.__hidden = False
        self.__reportedState = self.__state
        for (path, name), rc in self.__registeredCommands.items():
            rc.unregister = self.__parentRegisterCommand(
                self.__path + path, name, rc.function, rc.doc
            )

    def submitState(self):
        if self.__reportedState is not self.__state and not self.__hidden:
            self.__parentSet(self.__path, self.__state)
            self.__reportedState = self.__state


def raise_deactivated(*args, **kwargs):
    raise Exception("Subtree has been deactivated")


def no_op():
    ...
