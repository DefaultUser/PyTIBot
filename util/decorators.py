# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2015>  <Sebastian Schmidt>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import functools


def memoize(f):
    f.cache = {}

    @functools.wraps(f)
    def inner(*args, **kwargs):
        key = "(" + ", ".join([str(arg) for arg in args]) + ")"
        key = key + "|" + str(kwargs)
        if key not in f.cache:
            f.cache[key] = f(*args, **kwargs)
        return f.cache[key]
    return inner


def memoize_deferred(f):
    """Cache the result of a function - result should be wraped in a
    defer.maybeDeferred"""
    f.cache = {}

    def save_to_cache(result, key):
        f.cache[key] = result
        return result

    @functools.wraps(f)
    def inner(*args, **kwargs):
        key = "(" + ", ".join([str(arg) for arg in args]) + ")"
        key = key + "|" + str(kwargs)
        if key not in f.cache:
            d = f(*args, **kwargs)
            return d.addCallback(save_to_cache, key)
        return f.cache[key]
    return inner
