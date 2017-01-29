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
        data = json.loads(body)
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
            eventtype = data["object_kind"]
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
        if hasattr(self, "on_{}_{}".format(service, eventtype)):
            getattr(self, "on_{}_{}".format(service, eventtype))(data)
        else:
            logging.warn("Event {} not implemented for service {}".format(
                eventtype, service))
        # always return 200
        request.setResponseCode(200)
        return b""

    def commits_to_irc(self, commits):
        for i, commit in enumerate(commits):
            if i == 3:
                self.bot.msg(self.channel,
                             "+{} more commits".format(len(commits-3)))
                break
            self.bot.msg(self.channel, "{author}: {message} ({url})".format(
                author=colored(commit["author"]["name"], "cyan"),
                message=commit["message"], url=commit["url"]))

    def on_github_push(self, data):
        action = "pushed"
        if data["deleted"]:
            action = colored("deleted", "red")
        if data["forced"]:
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
        self.commits_to_irc(data["commits"])

    def on_github_issues(self, data):
        action = data["action"]
        payload = None
        if action == "assigned" or action == "unassigned":
            payload = data["issue"]["assignee"]["login"]
        if action == "labeled" or action == "unlabeled":
            payload = data["issue"]["label"]
        if action == "milestoned":
            payload = data["issue"]["milestone"]["title"]
        if action == "opened":
            action = colored(action, "red")
        if action == "reopened":
            action = colored(action, "red")
        if action == "closed":
            action = colored(action, "dark_green")
        if not payload:
            payload = data["issue"]["url"]
        msg = ("[{repo_name}] {user} {action} Issue #{number} {title}: "
               "{payload}".format(repo_name=colored(data["repository"]
                                                    ["name"], "blue"),
                                  user=colored(data["issue"]["sender"]
                                               ["login"],
                                               "cyan"),
                                  action=action,
                                  number=data["issue"]["number"],
                                  title=data["issue"]["title"],
                                  payload=payload))
        self.bot.msg(self.channel, msg)

    def on_github_issue_comment(self, data):
        msg = ("[{repo_name}] {user} {action} comment on Issue #{number}"
               " {title}".format(repo_name=colored(data["repository"]["name"],
                                                   "blue"),
                                 user=colored(data["comment"]["user"]["login"],
                                              "cyan"),
                                 action=data["action"],
                                 number=data["issue"]["number"],
                                 title=data["issue"]["title"]))
        self.bot.msg(self.channel, msg)

    def on_github_create(self, data):
        msg = "[{repo_name}] {user} created {ref_type} {ref}".format(
            repo_name=colored(data["repository"]["name"], "blue"),
            user=colored(data["sender"]["login"], "cyan"),
            ref_type=data["ref_type"], ref=data["ref"])
        self.bot.msg(self.channel, msg)

    def on_github_delete(self, data):
        msg = "[{repo_name}] {user} deleted {ref_type} {ref}".format(
            repo_name=colored(data["repository"]["name"], "blue"),
            user=colored(data["sender"]["login"], "cyan"),
            ref_type=data["ref_type"], ref=data["ref"])
        self.bot.msg(self.channel, msg)

    def on_github_fork(self, data):
        msg = "[{repo_name}] {user} created fork {url}".format(
            repo_name=colored(data["repository"]["name"], "blue"),
            user=colored(data["forkee"]["owner"]["login"], "cyan"),
            url=data["forkee"]["html_url"])
        self.bot.msg(self.channel, msg)

    def on_gitlab_push(self, data):
        msg = ("[{repo_name}] {pusher} pushed {num_commits} to "
               "{branch}".format(repo_name=colored(data["repository"]
                                                   ["name"], "blue"),
                                 pusher=colored(data["user_name"],
                                                "cyan"),
                                 num_commits=len(data["commits"]),
                                 branch=colored(data["ref"].split("/")[-1],
                                                "green")))
        self.bot.msg(self.channel, msg)
        self.commits_to_irc(data["commits"])

    def on_gitlab_issue(self, data):
        attribs = data["object_attributes"]
        action = attribs["action"]
        if action == "open":
            action = colored("opened", "red")
        if action == "reopen":
            action = colored("reopened", "red")
        if action == "close":
            action = colored("closed", "dark_green")
        if action == "update":
            action = "updated"
        msg = ("[{repo_name}] {user} {action} Issue #{number} {title}"
               "{url}".format(repo_name=colored(data["repository"]
                                                    ["name"], "blue"),
                              user=colored(data["user"]["name"],
                                           "cyan"),
                              action=action,
                              number=attribs["iid"],
                              title=attribs["title"],
                              url=attribs["url"]))
        self.bot.msg(self.channel, msg)
