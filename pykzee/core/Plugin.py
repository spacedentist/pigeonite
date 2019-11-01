from pykzee.core.Tree import Tree


class Plugin:
    __slots__ = (
        "path",
        "get",
        "subscribe",
        "command",
        "setState",
        "registerCommand",
    )

    def __init__(
        self, *, path, get, subscribe, command, set_state, register_command
    ):
        self.path = path
        self.get = get
        self.subscribe = subscribe
        self.command = command
        self.set = set_state
        self.registerCommand = register_command

    def createSubtree(self, path, *, immediate_updates=True):
        return Tree(
            path,
            parent_set=self.set,
            parent_register_command=self.registerCommand,
            immediate_updates=immediate_updates,
        )
