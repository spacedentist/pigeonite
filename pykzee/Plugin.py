class Plugin:
    __slots__ = (
        "get",
        "subscribe",
        "mount",
        "addPlugin",
        "removePlugin",
        "command",
    )

    def __init__(
        self, get, subscribe, mount, removePlugin, addPlugin, command
    ):
        self.get = get
        self.subscribe = subscribe
        self.mount = mount
        self.addPlugin = addPlugin
        self.removePlugin = removePlugin
        self.command = command
