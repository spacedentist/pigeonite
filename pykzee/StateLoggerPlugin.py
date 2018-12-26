import logging

from pykzee.Plugin import Plugin


class StateLoggerPlugin(Plugin):
    def init(self, path=()):
        self.unsubscribe = self.subscribe(self.stateUpdate, path)

    def stateUpdate(self, state):
        logging.debug(repr(state))
