import logging

from pyimmutable import ImmutableDict, ImmutableList
from pykzee.core.common import makePath
from pykzee.core.Plugin import Plugin


class StateLoggerPlugin(Plugin):
    def init(self, config):
        self.__pretty = bool(config.get("pretty", False))
        self.unsubscribe = self.subscribe(
            self.stateUpdate, makePath(config.get("path", ()))
        )

    def updateConfig(self, new_config):
        self.unsubscribe()
        self.__pretty = new_config["pretty"]
        self.unsubscribe = self.subscribe(
            self.stateUpdate, new_config.get("path", ())
        )
        return True

    def stateUpdate(self, state):
        if not self.__pretty:
            logging.debug(repr(state))
            return

        logging.debug("StateLoggerPlugin: new state:")
        pretty_print(state, OutputLines(logging.debug))


class OutputLines:
    def __init__(self, write):
        self.__write = write
        self.__data = ""

    def __call__(self, x):
        self.__data += x
        pos = self.__data.rfind("\n")
        if pos < 0:
            return
        out = self.__data[0:pos]
        self.__data = self.__data[pos + 1 :]
        for line in out.split("\n"):
            self.__write(line)

    def __del__(self):
        if self.__data:
            self.__write(self.__data)


def pretty_print(data, write, indent=""):
    if type(data) is ImmutableDict:
        more_indent = indent + "  "
        write("{\n")
        for key, value in data.items():
            write(f"{ indent }  { key !r}: ")
            pretty_print(value, write, more_indent)
            write(",\n")
        write(f"{ indent }}}")
    elif type(data) is ImmutableList:
        more_indent = indent + "  "
        write("[\n")
        for value in data:
            write(more_indent)
            pretty_print(value, write, more_indent)
            write(",\n")
        write(f"{ indent }]")
    else:
        write(repr(data))
