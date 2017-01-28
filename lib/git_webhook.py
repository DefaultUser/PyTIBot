# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2017>  <Sebastian Schmidt>

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

from twisted.web.resource import Resource
import codecs
import json
import hmac
from hashlib import sha1
import logging
import sys

from util.formatting import colored


class GitWebhookServer(Resource):
    """
    HTTP(S) Server for GitHub/Gitlab webhooks
    """
    isLeaf = True

    def __init__(self, bot, config):
        self.bot = bot
        self.github_secret = config["GitWebhook"].get("github_secret", None)
        self.gitlab_secret = config["GitWebhook"].get("gitlab_secret", None)
        self.channel = config["GitWebhook"]["channel"]

    def render_POST(self, request):
        body = request.content.read()
        service = None
        # GitHub
        if request.getHeader(b"X-GitHub-Event"):
            eventtype = request.getHeader(b"X-GitHub-Event")
            sig = request.getHeader(b"X-Hub-Signature")
            if sig:
                sig = sig[5:]
            service = "github"
        # Gitlab
        elif request.getHeader(b"X-Gitlab-Event"):
            eventtype = body["object_kind"]
            sig = request.getHeader(b"X-Gitlab-Token")
            service = "gitlab"
        if sys.version_info.major == 3:
            eventtype = str(eventtype, "utf-8")

        secret = None
        if service == "github":
            secret = self.github_secret
        elif service == "gitlab":
            secret = self.gitlab_secret
        if secret:
            h = hmac.new(secret, body, sha1)
            if codecs.encode(h.digest(), "hex") != sig:
                logging.warn("X-Hub-Signature does not correspond with "
                             "the given secret - ignoring request")
                request.setResponseCode(200)
                return b""
        data = json.loads(body)
        if hasattr(self, "on_{}_{}".format(service, eventtype)):
            getattr(self, "on_{}_{}".format(service, eventtype))(data)
        else:
            logging.warn("Event {} not implemented for service {}".format(
                eventtype, service))
        # always return 200
        request.setResponseCode(200)
        return b""

    def on_push(self, data):
        action = "pushed"
        if data.get("deleted", False):
            action = colored("deleted", "red")
        if data.get("forced", False):
            action = colored("force pushed", "red")
        msg = ("[{repo_name}] {pusher} {action} {num_commits} to {branch}:"
               " {compare}".format(repo_name=colored(data["repository"]
                                                     ["name"], "blue"),
                                   pusher=colored(data["pusher"]["name"],
                                                  "cyan"),
                                   action=action,
                                   num_commits=len(data["commits"]),
                                   branch=colored(data["ref"].split("/")[-1],
                                                  "green"),
                                   compare=data["compare"]))
        self.bot.msg(self.channel, msg)
        for i, commit in enumerate(data["commits"]):
            if i == 3:
                self.bot.msg(self.channel,
                             "+{} more commits".format(len(data["commits"]-3)))
                break
            self.bot.msg(self.channel, "{author}: {message} ({url})".format(
                author=colored(commit["author"]["name"], "cyan"),
                message=commit["message"], url=commit["url"]))

    def on_github_push(self, data):
        self.on_push(data)

    def on_gitlab_push(self, data):
        self.on_push(data)
