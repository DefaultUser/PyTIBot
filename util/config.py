# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2021>  <Sebastian Schmidt>

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

import yaml


class Config:
    def __init__(self, path):
        self._path = path
        self._data = dict()
        self.load()

    def load(self):
        with open(self._path) as f:
            self._data = yaml.load(f, Loader=yaml.SafeLoader)

    def write(self):
        with open(self._path, "w") as f:
            f.write(yaml.dump(self._data))

    def __getattr__(self, attr):
        return self[attr]

    def __getitem__(self, index):
        return self._data[index]
