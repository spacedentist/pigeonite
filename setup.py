from setuptools import setup

setup(
    name="pykzee",
    version="0.1.0",
    description=(
        "Core engine allowing plug-ins to operate on a JSON-like state tree"
    ),
    url="https://github.com/spacedentist/pykzee",
    author="Sven Over",
    author_email="sp@cedenti.st",
    license="MIT",
    packages=["pykzee"],
    install_requires=["aiofiles", "aionotify", "pyimmutable"],
    entry_points={"console_scripts": ["pykzee=pykzee.__main__:main"]},
)
