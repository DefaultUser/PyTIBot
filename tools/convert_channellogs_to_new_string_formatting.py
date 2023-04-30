# PyTIBot - misc
# Copyright (C) <2023>  <Sebastian Schmidt>

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

import os
import sys
import shutil
import yaml

from util.formatting import Tag
from util.formatting.irc import parse_irc
from util import filesystem as fs
from util import log
from util.config import Config


def convert(input_folder, output_folder):
    for name in os.listdir(input_folder):
        if name.endswith(".yaml"):
            inpath = os.path.join(input_folder, name)
            with open(inpath) as f:
                content = []
                for element in yaml.full_load_all(f.read()):
                    if element["levelname"] == "MSG":
                        msg = element["message"]
                        if not isinstance(msg, Tag):
                            element["message"] = parse_irc(msg)
                    content.append(element)
            outpath = os.path.join(output_folder, name)
            with open(outpath, "w") as f:
                f.write(yaml.dump_all(content, explicit_start=True, default_flow_style=False))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        config_name = sys.argv[1]
    else:
        config_name = "pytibot.yaml"
    config = Config(path=fs.config_file(config_name))
    log.channellog_dir_from_config(config)
    log_dir = log.get_channellog_dir()
    backup_dir = os.path.abspath(os.path.join(log_dir, "..", "channellogs_bak"))
    if os.path.exists(backup_dir):
        print(f"Backup directory `{backup_dir}` already exists, exiting")
        exit(-1)
    shutil.move(log_dir, backup_dir)
    os.makedirs(log_dir)
    convert(backup_dir, log_dir)
