import argparse
import asyncio
import logging
import os


from pykzee.RawStateLoader import RawStateLoader
import pykzee.ManagedTree

logging.getLogger().setLevel(logging.DEBUG)

try:
    import coloredlogs
except ImportError:
    ...
else:
    coloredlogs.install(level="DEBUG")


parser = argparse.ArgumentParser()
parser.add_argument(
    "--config",
    help="path to config directory (defaults to current working directory)",
)
options = parser.parse_args()


async def amain():
    if options.config:
        os.chdir(options.config)

    mtree = pykzee.ManagedTree.ManagedTree()
    raw_state_loader = RawStateLoader(mtree.setRawState)
    await raw_state_loader.readStateFromDisk()
    await raw_state_loader.run()


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
