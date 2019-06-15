# -*- coding: utf-8 -*-

# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2019>  <Sebastian Schmidt>

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

import markovify
import random
import os

from . import abstract
from util import filesystem as fs


class MarkovChat(abstract.ChannelWatcher):
    def __init__(self, bot, channel, config):
        super(MarkovChat, self).__init__(bot, channel, config)
        self.corpus = os.path.join(fs.adirs.user_config_dir, "markov",
                                   self.channel, config["corpus"])
        if not os.path.isfile(self.corpus):
            raise IOError("No such file: {}".format(self.corpus))
        with open(self.corpus) as f:
            self.model = markovify.Text(f.read())
        self.keywords = config["keywords"]
        self.chat_rate = config.get("chat_rate", 0.1)
        self.add_rate = config.get("add_rate", 0.4)

    def add_to_corpus(self, message):
        if not message.endswith("."):
            message = message + "."
        temp = markovify.Text(message)
        self.model = markovify.combine([self.model, temp])

    def msg(self, user, message):
        if not(any([keyword in message.lower() for keyword in self.keywords])):
            return
        if random.random() < self.chat_rate:
            self.bot.msg(self.channel, self.model.make_short_sentence(240))
        if random.random() < self.add_rate and len(message.split()) > 5:
            self.add_to_corpus(message)

    def connectionLost(self, reason):
        with open(self.corpus, "w") as f:
            f.write(self.model.rejoined_text.replace(".", ".\n"))

