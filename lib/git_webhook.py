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
from twisted.internet import reactor, defer
import treq
import codecs
import json
import hmac
from hashlib import sha1
import logging
import sys
from unidecode import unidecode

from util.formatting import colored


@defer.inlineCallbacks
def shorten_github_url(url):
    """
    Shorten a github url using git.io - if it fails, return the original url
    """
    try:
        response = yield treq.post("https://git.io", data={"url": url},
                                   timeout=5)
    except Exception as e:
        logging.warn(e)
        defer.returnValue(url)
    defer.returnValue(response.headers.getRawHeaders("Location", [url])[0])


class GitWebhookServer(Resource):
    """
    HTTP(S) Server for GitHub/Gitlab webhooks
    """
    isLeaf = True

    def __init__(self, bot, config):
        self.bot = bot
        self.github_secret = config["GitWebhook"].get("github_secret", None)
        self.gitlab_secret = config["GitWebhook"].get("gitlab_secret", None)
        self.channels = config["GitWebhook"]["channels"]

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
            reactor.callLater(0, getattr(self, "on_{}_{}".format(service,
                                                                 eventtype)),
                              data)
        else:
            logging.warn("Event {} not implemented for service {}".format(
                eventtype, service))
        # always return 200
        request.setResponseCode(200)
        return b""

    def report_to_irc(self, repo_name, message):
        channels = []
        if repo_name in self.channels:
            channels = self.channels[repo_name]
        elif "default" in self.channels:
            channels = self.channels["default"]
        if not isinstance(channels, list):
            # don't error out if the config has a string instead of a list
            channels = [channels]
        if not channels:
            logging.warn("Recieved webhook for repo [{repo}], but no IRC "
                         "channel is configured for it, ignoring...")
            return
        for channel in channels:
            self.bot.msg(channel, message)

    @defer.inlineCallbacks
    def commits_to_irc(self, repo_name, commits, github=False):
        for i, commit in enumerate(commits):
            if i == 3:
                self.report_to_irc(repo_name, "+{} more commits".format(
                    len(commits) - 3))
                break
            if github:
                url = yield shorten_github_url(commit["url"])
            else:
                url = commit["url"]
            message = unidecode(commit["message"].split("\n")[0])
            if len(message) > 100:
                message = message[:100] + "..."
            self.report_to_irc(repo_name, "{author}: {message} ({url})".format(
                author=colored(unidecode(commit["author"]["name"]),
                               "dark_cyan"),
                message=message,
                url=url))

    @defer.inlineCallbacks
    def on_github_push(self, data):
        action = "pushed"
        if data["deleted"]:
            action = colored("deleted", "red")
        elif data["forced"]:
            action = colored("force pushed", "red")
        url = yield shorten_github_url(data["compare"])
        repo_name = data["repository"]["name"]
        msg = ("[{repo_name}] {pusher} {action} {num_commits} commit(s) to "
               "{branch}: {compare}".format(
                   repo_name=colored(repo_name, "blue"),
                   pusher=colored(unidecode(data["pusher"]["name"]),
                                  "dark_cyan"),
                   action=action,
                   num_commits=len(data["commits"]),
                   branch=colored(data["ref"].split("/", 2)[-1], "dark_green"),
                   compare=url))
        self.report_to_irc(repo_name, msg)
        self.commits_to_irc(repo_name, data["commits"], github=True)

    @defer.inlineCallbacks
    def on_github_issues(self, data):
        action = data["action"]
        payload = None
        repo_name = data["repository"]["name"]
        if action == "assigned" or action == "unassigned":
            payload = data["issue"]["assignee"]["login"]
        elif action == "labeled" or action == "unlabeled":
            url = yield shorten_github_url(data["issue"]["html_url"])
            payload = "{} ({})".format(colored(data["label"]["name"],
                                               "dark_green"), url)
        elif action == "milestoned":
            payload = data["issue"]["milestone"]["title"]
        elif action == "opened":
            action = colored(action, "red")
        elif action == "reopened":
            action = colored(action, "red")
        elif action == "closed":
            action = colored(action, "dark_green")
        if not payload:
            payload = yield shorten_github_url(data["issue"]["html_url"])
        msg = ("[{repo_name}] {user} {action} Issue #{number} {title}: "
               "{payload}".format(repo_name=colored(repo_name, "blue"),
                                  user=colored(data["sender"]["login"],
                                               "dark_cyan"),
                                  action=action,
                                  number=colored(str(data["issue"]["number"]),
                                                 "dark_yellow"),
                                  title=unidecode(data["issue"]["title"]),
                                  payload=payload))
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_issue_comment(self, data):
        url = yield shorten_github_url(data["comment"]["html_url"])
        repo_name = data["repository"]["name"]
        msg = ("[{repo_name}] {user} {action} comment on Issue #{number} "
               "{title} {url}".format(
                   repo_name=colored(repo_name, "blue"),
                   user=colored(data["comment"]["user"]["login"], "dark_cyan"),
                   action=data["action"],
                   number=colored(str(data["issue"]["number"]), "dark_yellow"),
                   title=unidecode(data["issue"]["title"]),
                   url=url))
        self.report_to_irc(repo_name, msg)

    def on_github_create(self, data):
        repo_name = data["repository"]["name"]
        msg = "[{repo_name}] {user} created {ref_type} {ref}".format(
            repo_name=colored(repo_name, "blue"),
            user=colored(data["sender"]["login"], "dark_cyan"),
            ref_type=data["ref_type"],
            ref=colored(data["ref"], "dark_magenta"))
        self.report_to_irc(repo_name, msg)

    def on_github_delete(self, data):
        repo_name = data["repository"]["name"]
        msg = "[{repo_name}] {user} deleted {ref_type} {ref}".format(
            repo_name=colored(repo_name, "blue"),
            user=colored(data["sender"]["login"], "dark_cyan"),
            ref_type=data["ref_type"],
            ref=colored(data["ref"], "dark_magenta"))
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_fork(self, data):
        repo_name = data["repository"]["name"]
        url = yield shorten_github_url(data["forkee"]["html_url"])
        msg = "[{repo_name}] {user} created fork {url}".format(
            repo_name=colored(repo_name, "blue"),
            user=colored(data["forkee"]["owner"]["login"], "dark_cyan"),
            url=url)
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_commit_comment(self, data):
        repo_name = data["repository"]["name"]
        url = yield shorten_github_url(data["comment"]["html_url"])
        msg = "[{repo_name}] {user} commented on commit {url}".format(
            repo_name=colored(repo_name, "blue"),
            user=colored(data["comment"]["user"]["login"], "dark_cyan"),
            url=url)
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_release(self, data):
        repo_name = data["repository"]["name"]
        url = yield shorten_github_url(data["release"]["html_url"])
        msg = "[{repo_name}] New release {url}".format(
            repo_name=colored(data["repository"]["name"], "blue"),
            url=url)
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_pull_request(self, data):
        action = data["action"]
        payload = None
        repo_name = data["repository"]["name"]
        user = data["pull_request"]["user"]["login"]
        if action == "assigned" or action == "unassigned":
            payload = data["pull_request"]["assignee"]["login"]
        elif action == "labeled" or action == "unlabeled":
            payload = data["pull_request"]["label"]
        elif action == "milestoned":
            payload = data["pull_request"]["milestone"]["title"]
        elif action == "review_requested":
            action = "requested review for"
            payload = data["requested_reviewer"]["login"]
        elif action == "review_request_removeded":
            action = "removed review request for"
            payload = data["requested_reviewer"]["login"]
        elif action == "opened":
            action = colored(action, "dark_green")
        elif action == "reopened":
            action = colored(action, "dark_green")
        elif action == "closed":
            if data["pull_request"]["merged"]:
                action = colored("merged", "dark_green")
                user = data["pull_request"]["merged_by"]["login"]
            else:
                action = colored(action, "red")
                user = data["sender"]["login"]
        elif action == "synchronize":
            action = "synchronized"
        if not payload:
            payload = yield shorten_github_url(
                data["pull_request"]["html_url"])
        msg = ("[{repo_name}] {user} {action} Pull Request #{number} {title} "
               "({head} -> {base}): {payload}".format(
                   repo_name=colored(repo_name, "blue"),
                   user=colored(user, "dark_cyan"),
                   action=action,
                   number=colored(str(data["pull_request"]["number"]),
                                  "dark_yellow"),
                   title=unidecode(data["pull_request"]["title"]),
                   head=colored(data["pull_request"]["head"]["ref"],
                                "dark_blue"),
                   base=colored(data["pull_request"]["base"]["ref"],
                                "dark_red"),
                   payload=payload))
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_pull_request_review(self, data):
        repo_name = data["repository"]["name"]
        url = yield shorten_github_url(data["review"]["html_url"])
        msg = ("[{repo_name}] {user} reviewed Pull Request #{number} {title} "
               "({head} -> {base}): {url}".format(
                   repo_name=colored(repo_name, "blue"),
                   user=colored(data["review"]["user"]["login"], "dark_cyan"),
                   number=colored(str(data["pull_request"]["number"]),
                                  "dark_yellow"),
                   title=data["pull_request"]["title"],
                   head=colored(data["pull_request"]["head"]["ref"],
                                "dark_blue"),
                   base=colored(data["pull_request"]["base"]["ref"],
                                "dark_red"),
                   url=url))
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_pull_request_review_comment(self, data):
        repo_name = data["repository"]["name"]
        url = yield shorten_github_url(data["comment"]["html_url"])
        msg = ("[{repo_name}] {user} commented on Pull Request #{number} "
               "{title} ({head} -> {base}): {url}".format(
                   repo_name=colored(repo_name, "blue"),
                   user=colored(data["comment"]["user"]["login"], "dark_cyan"),
                   number=colored(str(data["pull_request"]["number"]),
                                  "dark_yellow"),
                   title=unidecode(data["pull_request"]["title"]),
                   head=colored(data["pull_request"]["head"]["ref"],
                                "dark_blue"),
                   base=colored(data["pull_request"]["base"]["ref"],
                                "dark_red"),
                   url=url))
        self.report_to_irc(repo_name, msg)

    def on_gitlab_push(self, data):
        repo_name = data["project"]["name"]
        msg = ("[{repo_name}] {pusher} pushed {num_commits} commit(s) to "
               "{branch}".format(repo_name=colored(repo_name, "blue"),
                                 pusher=colored(data["user_name"],
                                                "dark_cyan"),
                                 num_commits=len(data["commits"]),
                                 branch=colored(data["ref"].split("/", 2)[-1],
                                                "dark_green")))
        self.report_to_irc(repo_name, msg)
        self.commits_to_irc(repo_name, data["commits"])

    def on_gitlab_tag_push(self, data):
        repo_name = data["project"]["name"]
        msg = ("[{repo_name}] {pusher} added tag {tag}".format(
            repo_name=colored(repo_name, "blue"),
            pusher=colored(data["user_name"], "dark_cyan"),
            tag=colored(data["ref"].split("/", 2)[-1], "dark_green")))
        self.report_to_irc(repo_name, msg)
        self.commits_to_irc(repo_name, data["commits"])

    def on_gitlab_issue(self, data):
        repo_name = data["project"]["name"]
        attribs = data["object_attributes"]
        action = attribs["action"]
        if action == "open":
            action = colored("opened", "red")
        elif action == "reopen":
            action = colored("reopened", "red")
        elif action == "close":
            action = colored("closed", "dark_green")
        elif action == "update":
            action = "updated"
        msg = ("[{repo_name}] {user} {action} Issue #{number} {title} "
               "{url}".format(repo_name=colored(repo_name, "blue"),
                              user=colored(data["user"]["name"], "dark_cyan"),
                              action=action,
                              number=colored(str(attribs["iid"]),
                                             "dark_yellow"),
                              title=unidecode(attribs["title"]),
                              url=attribs["url"]))
        self.report_to_irc(repo_name, msg)

    def on_gitlab_note(self, data):
        repo_name = data["project"]["name"]
        attribs = data["object_attributes"]
        noteable_type = attribs["noteable_type"]
        if noteable_type == "Commit":
            id = attribs["commit_id"]
            title = data["commit"]["message"].split("\n")[0]
            if len(title) > 100:
                title = title[:100] + "..."
        elif noteable_type == "MergeRequest":
            id = data["merge_request"]["iid"]
            title = data["merge_request"]["title"]
            noteable_type = "Merge Request"
        elif noteable_type == "Issue":
            id = data["issue"]["iid"]
            title = data["issue"]["title"]
        elif noteable_type == "Snippet":
            id = data["snippet"]["id"]
            title = data["snippet"]["title"]
        else:
            return
        msg = ("[{repo_name}] {user} commented on {noteable_type} {number} "
               "{title} {url}".format(
                   repo_name=colored(repo_name, "blue"),
                   user=colored(data["user"]["name"], "dark_cyan"),
                   noteable_type=noteable_type,
                   number=colored(str(id), "dark_yellow"),
                   title=unidecode(title),
                   url=attribs["url"]))
        self.report_to_irc(repo_name, msg)

    def on_gitlab_merge_request(self, data):
        attribs = data["object_attributes"]
        repo_name = attribs["target"]["name"]
        action = attribs["action"]
        if action == "open":
            action = colored("opened", "dark_green")
        elif action == "reopen":
            action = colored("reopened", "dark_green")
        elif action == "close":
            action = colored("closed", "red")
        elif action == "merge":
            action = colored("merged", "dark_green")
        elif action == "update":
            action = "updated"
        elif action == "approved":
            action = colored("approved", "dark_green")
        msg = ("[{repo_name}] {user} {action} Merge Request #{number} "
               "{title} ({source} -> {target}): {url}".format(
                   repo_name=colored(repo_name, "blue"),
                   user=colored(data["user"]["name"], "dark_cyan"),
                   action=action,
                   number=colored(str(attribs["iid"]), "dark_yellow"),
                   title=unidecode(attribs["title"]),
                   source=colored(attribs["source_branch"], "dark_blue"),
                   target=colored(attribs["target_branch"], "dark_red"),
                   url=attribs["url"]))
        self.report_to_irc(repo_name, msg)
