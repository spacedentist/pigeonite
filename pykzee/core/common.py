import asyncio
from collections.abc import Mapping, Sequence
import enum
import inspect
import re
import typing
import urllib.parse

from pyimmutable import ImmutableDict, ImmutableList


__all__ = (
    "Undefined PathType InvalidPathElement PathElementTypeMismatch "
    "sanitize getDataForPath setDataForPath "
    "makePath stringToPathElement pathToString "
    "waitForOne call_soon print_exception_task_callback".split()
)


def _make_atom(name, *, bool=None):
    typedict = {"__repr__": lambda self: name}
    if bool is not None:
        typedict["__bool__"] = (
            (lambda self: True) if bool else (lambda self: False)
        )
    atomtype = type(f"{ name }Type", (object,), typedict)
    atom = atomtype()
    atomtype.__new__ = (lambda x: lambda cls: x)(atom)
    return atom


Undefined = _make_atom("Undefined", bool=False)

PathElementType = typing.Union[str, int]
PathType = typing.Tuple[PathElementType]


class StateType(enum.Enum):
    RAW = 0
    UNRESOLVED = 1
    RESOLVED = 2


class InvalidPathElement(Exception):
    def __init__(self, value):
        super(InvalidPathElement, self).__init__(
            f"Path elements must be str or int, not {type(value) !r}"
        )


class PathElementTypeMismatch(Exception):
    def __init__(self, elem, data):
        super(PathElementTypeMismatch, self).__init__(
            f"Path element of type { type(elem) !r} cannot be resolved "
            f"in data of type { type(data) !r}"
        )


def sanitize(data):
    t = type(data)
    if (t is ImmutableList or t is ImmutableDict) and data.isImmutableJson:
        return data
    if data is None or t is bool or t is str or t is int or t is float:
        return data
    elif isinstance(data, Sequence):
        data = ImmutableList(sanitize(x) for x in data if x is not Undefined)
        if data.isImmutableJson:
            return data
    elif isinstance(data, Mapping):
        data = ImmutableDict(
            (enforceKeyType(key), sanitize(value))
            for key, value in data.items()
            if value is not Undefined
        )
        if data.isImmutableJson:
            return data
    raise TypeError("data cannot be sanitized to immutable json")


def enforceKeyType(s):
    if type(s) is not str:
        raise TypeError("Dictionary keys must be strings")
    return s


def getDataForPath(data, path: PathType):
    for p in path:
        if type(data) not in (ImmutableDict, ImmutableList):
            return Undefined
        if type(p) not in (str, int):
            raise InvalidPathElement(p)
        try:
            data = data[p]
        except Exception:
            return Undefined
    return data


def setDataForPath(data, path: PathType, value, *, undefined=ImmutableDict()):
    if not path:
        if value is Undefined:
            return undefined
        else:
            return sanitize(value)
    p, path = path[0], path[1:]
    if type(p) is str:
        if data is Undefined:
            data = ImmutableDict()
        elif type(data) is not ImmutableDict:
            raise PathElementTypeMismatch(p, data)
        if value is Undefined and not path:
            return data.discard(p)
    elif type(p) is int:
        if data is Undefined:
            data = ImmutableList()
        elif type(data) is not ImmutableList:
            raise PathElementTypeMismatch(p, data)
        if value is Undefined and not path:
            if 0 <= p < len(data):
                return data[0:p] + data[p + 1 :]
            else:
                return data
        if p < 0 or p > len(data):
            raise IndexError
        if p == len(data):
            return data.append(setDataForPath(Undefined, path, value))
    else:
        raise InvalidPathElement(p)
    return data.set(p, setDataForPath(data.get(p, Undefined), path, value))


def makePath(
    s: typing.Union[str, typing.Sequence[PathElementType]],
    *,
    relativeTo: PathType = (),
) -> PathType:
    if type(s) is str:
        absolute = s.startswith("/")
        s = s.strip("/")
        if not s:
            return () if absolute else relativeTo
        result = [] if absolute else list(relativeTo)
        for e in s.split("/"):
            if e == "..":
                if result:
                    result.pop()
            elif e != ".":
                result.append(stringToPathElement(e))
        return tuple(result)
    elif isinstance(s, Sequence):
        result = tuple(s)
        for i in result:
            if type(i) not in (str, int):
                raise TypeError(
                    "Path sequence must only contain str and int elements"
                )
        return result
    else:
        raise TypeError(f"Cannot convert type { type(s).__name__ } to path")


_rex_integer_element = re.compile(r"^\[(\d+)\]$")


def stringToPathElement(e: str) -> PathElementType:
    res = _rex_integer_element.match(e)
    if res:
        return int(res.group(1))
    return urllib.parse.unquote(e)


def pathToString(path: PathType) -> str:
    return "/" + "/".join(pathElementToString(e) for e in path)


def pathElementToString(e: PathElementType) -> str:
    if type(e) is int:
        return f"[{ e }]"
    if e == ".":
        return "%2E"
    if e == "..":
        return "%2E."
    e = e.replace("%", "%25").replace("/", "%2F")
    if e.startswith("["):
        return f"%5B{ e[1:] }"
    return e


async def waitForOne(*aws):
    _, pending = await asyncio.wait(aws, return_when=asyncio.FIRST_COMPLETED)
    for f in pending:
        f.cancel()


def call_soon(func, *args, **kwargs):
    async def makeCall():
        ret = func(*args, **kwargs)
        if inspect.isawaitable(ret):
            await ret

    asyncio.get_event_loop().call_soon(
        lambda: asyncio.create_task(makeCall()).add_done_callback(
            print_exception_task_callback
        )
    )


def print_exception_task_callback(task):
    if not task.cancelled():
        ex = task.exception()
        if ex is not None and type(ex) is not KeyboardInterrupt:
            task.print_stack()
