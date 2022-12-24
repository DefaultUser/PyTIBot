# PyTIBot - Formatting Helper
# Copyright (C) <2015-2022>  <Sebastian Schmidt>

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

from enum import IntEnum


_ANSI_CSI = "\x1b["
_ANSI_FG_START = 30
_ANSI_BG_START = 40
ANSIColors = IntEnum("ANSIColors", "black red green yellow blue magenta cyan white",
                     start=0)

def colored(text: str, fg: ANSIColors=None, bg: ANSIColors=None) -> str:
    infocodes = []
    if fg is not None:
        infocodes.append(str(fg.value + _ANSI_FG_START))
    if bg is not None:
        infocodes.append(str(bg.value + _ANSI_BG_START))
    return _ANSI_CSI + ";".join(infocodes) + "m" + text + _ANSI_CSI + "0m"


