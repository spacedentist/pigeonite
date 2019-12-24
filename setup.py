from setuptools import setup

with open("README.rst", "r") as fh:
    long_description = fh.read()

with open("pykzee/core/__version__.py", "r") as fh:
    versiondict = {"__builtins__": {}}
    exec(fh.read(), versiondict)
    version = versiondict["version"]

setup(
    name="pykzee",
    version=version,
    description=(
        "Core engine allowing plug-ins to operate on a JSON-like state tree"
    ),
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://github.com/spacedentist/pykzee",
    download_url=(
        f"https://github.com/spacedentist/pykzee/archive/{ version }.tar.gz"
    ),
    author="Sven Over",
    author_email="sp@cedenti.st",
    license="MIT",
    packages=["pykzee", "pykzee.core"],
    install_requires=[
        "aiofiles>=0.4.0",
        "watchdog>=0.9.0",
        "pyimmutable>=0.2.0",
    ],
    entry_points={"console_scripts": ["pykzee=pykzee.core.__main__:main"]},
    test_suite="pykzee.core.tests",
)
