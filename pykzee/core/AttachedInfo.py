import functools

from pyimmutable import ImmutableList, ImmutableDict
from pykzee.core.common import Undefined, makePath, pathToString

SameAsData = object()


def attribute(key):
    def decorator(func):
        def modified_func(data):
            try:
                result = data.meta[key]
            except KeyError:
                ...
            else:
                return data if result is SameAsData else result

            result = func(data)
            data.meta[key] = SameAsData if result is data else result
            return result

        modified_func.uncached = func
        return modified_func

    return decorator


##############################################################################


def getSubtree(data, path):
    if not path:
        return data
    if type(data) not in (ImmutableDict, ImmutableList):
        return Undefined

    meta = data.meta
    try:
        cache = meta["subtree-cache"]
    except KeyError:
        cache = meta["subtree-cache"] = {}

    try:
        return cache[path]
    except KeyError:
        ...

    try:
        child = data[path[0]]
    except Exception:
        cache[path] = Undefined
        return Undefined

    if len(path) < 2:
        cache[path] = child
        return child

    result = cache[path] = getSubtree(child, path[1:])
    return result


@attribute("plugins")
def plugins(data):
    if type(data) is ImmutableDict:
        if "__plugin__" in data:
            return ImmutableList([((), data)])

    gen = (
        sorted(data.items())
        if type(data) is ImmutableDict
        else enumerate(data)
    )
    return ImmutableList(
        ((key,) + path, plugin)
        for key, value in gen
        if type(value) in (ImmutableDict, ImmutableList)
        for path, plugin in plugins(value)
    )


def symlink(data):
    if type(data) is ImmutableDict and len(data) == 1:
        (key, value), = data.items()
        if key == "__symlink__":
            try:
                return makePath(value)
            except TypeError:
                return False


@attribute("symlinks")
def symlinks(data):
    sl = symlink(data)
    if sl is False:
        return ImmutableList()
    elif sl is not None:
        return ImmutableList([((), sl)])

    gen = (
        sorted(data.items())
        if type(data) is ImmutableDict
        else enumerate(data)
    )
    return ImmutableList(
        ((key,) + path, dest)
        for key, value in gen
        if type(value) in (ImmutableDict, ImmutableList)
        for path, dest in symlinks(value)
    )


@attribute("_symlinkInfoDict")
def _symlinkInfoDict(data):
    return ImmutableDict((pathToString(k), pathToString(v)) for k, v in data)


def symlinkInfoDict(data):
    return _symlinkInfoDict(symlinks(data))


@attribute("realpath")
def realpath(data):
    return functools.partial(_realpathImpl, dict(symlinks(data)))


def _realpathImpl(symlink_table, location):
    location = list(location)
    result = ()
    location_length_when_symlink_encountered = {}

    while location:
        first_element = location.pop(0)
        result = result + (first_element,)
        dest = symlink_table.get(result)
        if dest is not None:
            prevlength = location_length_when_symlink_encountered.get(result)
            if prevlength is not None and len(location) >= prevlength:
                # We encountered some sort of cycle
                return
            location_length_when_symlink_encountered[result] = len(location)
            location = list(dest) + location
            result = ()

    return result


@attribute("_realpaths")
def _realpaths(data):
    rp = functools.partial(_realpathImpl, dict(data))
    return ImmutableList(
        (location, real_destination)
        for location, real_destination in (
            (location, rp(destination)) for location, destination in data
        )
        if real_destination is not None
    )


def realpaths(data):
    return _realpaths(symlinks(data))


@attribute("_resolveStep")
def _resolveStep(data):
    # remove all symlinks that resolve back to a ancestor of its
    # own location
    real_paths = [
        (loc, dest)
        for loc, dest in realpaths(data)
        if loc[0 : len(dest)] != dest
    ]

    if not real_paths:
        return data

    return _resolveImpl.uncached(
        (
            data,
            *(
                i
                for loc, dest in real_paths
                for i in (loc, getSubtree(data, dest))
            ),
        )
    )


@attribute("_resolveStepBack")
def _resolveStepBack(data):
    return _resolveImpl.uncached(
        (
            data,
            *(
                i
                for loc, dest in realpaths(data)
                for i in (loc, getSubtree(data, dest))
            ),
        )
    )


def resolved(data, *, max_steps=5, max_backresolve_steps=1):
    for level in range(max_steps):
        next_data = (
            _resolveStepBack(data)
            if level < max_backresolve_steps
            else _resolveStep(data)
        )
        if data is next_data:
            break
        else:
            data = next_data
    return data


@attribute("_resolveImpl")
def _resolveImpl(resolve_data):
    if len(resolve_data) == 3 and resolve_data[1] == ():
        return resolve_data[2]

    data = resolve_data[0]
    replacements = [
        (resolve_data[i], resolve_data[i + 1])
        for i in range(1, len(resolve_data), 2)
    ]

    if not replacements:
        return data

    try:
        keep_alive = data.meta["_resolveImpl-keep_alive"]
    except KeyError:
        keep_alive = data.meta["_resolveImpl-keep_alive"] = []

    keep_alive = []
    i = 0
    while i < len(replacements):
        first_elem = replacements[i][0][0]
        j = i + 1
        while j < len(replacements):
            if replacements[j][0][0] == first_elem:
                j += 1
            else:
                break

        if j - i == 1 and len(replacements[i][0]) == 1:
            data = _set_helper(data, first_elem, replacements[i][1])
        else:
            subreplacements = ImmutableList(
                [
                    _get_helper(data, first_elem),
                    *(
                        item
                        for k in range(i, j)
                        for item in (
                            replacements[k][0][1:],
                            replacements[k][1],
                        )
                    ),
                ]
            )
            keep_alive.append(subreplacements)
            data = _set_helper(data, first_elem, _resolveImpl(subreplacements))
        i = j

    return data


def _get_helper(data, key):
    try:
        return data[key]
    except Exception:
        return Undefined


def _set_helper(data, key, value):
    if value is Undefined:
        if type(data) is ImmutableDict:
            return data.discard(key)
        else:
            if 0 <= key < len(data):
                return data[0:key] + data[key + 1 :]
            else:
                return data
    else:
        return data.set(key, value)
