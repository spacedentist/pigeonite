import argparse
import asyncio
import logging

import pykzee.PluginLoaderPlugin
import pykzee.ConfigPlugin
import pykzee.ManagedTree

logging.getLogger().setLevel(logging.DEBUG)

try:
    import coloredlogs
except ImportError:
    ...
else:
    coloredlogs.install(level="DEBUG")


parser = argparse.ArgumentParser()
parser.add_argument("--config", help="path to config directory", required=True)
options = parser.parse_args()


async def amain():
    shutdown = asyncio.Event()
    tree = pykzee.ManagedTree.ManagedTree()
    tree.addPlugin(
        pykzee.ConfigPlugin.ConfigPlugin, None, ("config",), options.config
    )
    tree.addPlugin(
        pykzee.PluginLoaderPlugin.PluginLoaderPlugin,
        None,
        configPath=("config", "plugins"),
        mountPath=("pluginloader",),
    )
    await shutdown.wait()


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
