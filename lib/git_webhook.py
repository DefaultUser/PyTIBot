# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2017-2018>  <Sebastian Schmidt>

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
from twisted.python.failure import Failure
from twisted.logger import Logger
import treq
import codecs
import json
import hmac
from hashlib import sha1
import sys
from unidecode import unidecode

from util.formatting import colored, closest_irc_color, split_rgb_string,\
    good_contrast_with_black
from util.misc import str_to_bytes, bytes_to_str
from util.internet import shorten_github_url
from lib import webhook_actions


class GitWebhookServer(Resource):
    """
    HTTP(S) Server for GitHub/Gitlab webhooks
    """
    isLeaf = True
    log = Logger()

    def __init__(self, bot, config):
        self.bot = bot
        self.github_secret = config["GitWebhook"].get("github_secret", None)
        self.gitlab_secret = config["GitWebhook"].get("gitlab_secret", None)
        self.channels = config["GitWebhook"]["channels"]
        # local hooks and actions
        self.actions = config["GitWebhook"].get("Actions", {})
        self.hooks = config["GitWebhook"].get("Hooks", {})
        self.rungroup_settings = config["GitWebhook"].get("RungroupSettings",
                                                          {})
        users = config["GitWebhook"].get("hook_report_users", [])
        # don't fail if the config provides a single name instead of a list
        if isinstance(users, str):
            self.log.warn("GitWebhook expected a list of users for "
                          "'hook_report_users', but got a single string")
            users = [users]
        self.hook_report_users = users

    def render_POST(self, request):
        body = request.content.read()
        data = json.loads(bytes_to_str(body))
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
        eventtype = bytes_to_str(eventtype)

        secret = None
        if service == "github":
            secret = self.github_secret
        elif service == "gitlab":
            secret = self.gitlab_secret
        if secret:
            secret = str_to_bytes(secret)
            h = hmac.new(secret, body, sha1)
            if codecs.encode(h.digest(), "hex") != sig:
                self.log.warn("Request's signature does not correspond"
                              " with the given secret - ignoring request")
                request.setResponseCode(200)
                return b""
        if hasattr(self, "on_{}_{}".format(service, eventtype)):
            reactor.callLater(0, getattr(self, "on_{}_{}".format(service,
                                                                 eventtype)),
                              data)
        else:
            self.log.warn("Event {eventtype} not implemented for service "
                          "{service}", eventtype=eventtype, service=service)
        # always return 200
        request.setResponseCode(200)
        return b""

    def github_label_colors(self, label):
        color = label["color"]
        try:
            bg = closest_irc_color(*split_rgb_string(color))
            fg = "black" if good_contrast_with_black[bg] else "white"
        except Exception as e:
            self.log.error("Issue label: could not find a closest IRC "
                           "color for colorcode '{color}' ({error})",
                           color=color, error=e)
            bg = None
            fg = "dark_green"
        return fg, bg

    def report_hook_success_msg(self, success, actionname):
        """
        Send a success or fail message to the 'hook_report_users'
        """
        if isinstance(success, Failure):
            message = "Hook {} failed: {}".format(colored(actionname, "blue"),
                                                  success.getErrorMessage())
        else:
            message = "Hook {} finished without errors".format(
                colored(actionname, "blue"))
        for user in self.hook_report_users:
            self.bot.msg(user, message)

    def push_hooks(self, data):
        """
        Trigger the defined push hooks
        """
        repo_name = data["project"]["name"]
        projects = self.hooks.get("Push", [])
        if repo_name in projects:
            hooks = projects[repo_name]
        elif "default" in projects:
            hooks = projects["default"]
        else:
            return
        branch = data["branch"]
        for hook in hooks:
            # check for allowed branch
            branches = hook.get("branches", "<all>")
            if not (branches == "<all>" or branch in branches):
                continue
            # check for ignored users
            ignore_users = hook.get("ignore_users", [])
            if data["pusher"]["username"] in ignore_users:
                continue
            action_name = hook.get("action", None)
            if not action_name:
                self.log.warn("Push hook: Missing action for repo {name}",
                              name=repo_name)
                continue
            action = self.actions.get(action_name, None)
            if not action:
                self.log.warn("No webhook action '{name}' defined",
                              name=action_name)
                continue
            action_type = action.get("type", None)
            run_settings = self.rungroup_settings.get(action.get("rungroup",
                                                                 "default"),
                                                      {})
            if action_type and hasattr(webhook_actions, action_type):
                d = getattr(webhook_actions, action_type)(action_name, data,
                                                          action,
                                                          run_settings)
                d.addBoth(self.report_hook_success_msg, action_name)
            else:
                self.log.warn("No such action type: {action_type}",
                              action_type=action_type)

        # Push: github_push, gitlab_push
        # Tag: github_create (ref_type: tag), gitlab_tag_push
        # implement later
        # Issue: github_issues (opened, reopened, edited, closed),
        #        gitlab_issue (open, reopen, update, close)
        # PullRequest: github_pull_request (opened, reopened, closed, edited,
        #                                   synchronize),
        #              github_pull_request_review (review -> state == approved),
        #              gitlab_merge_request (open, reopen, merge, close, update,
        #                                    approved)
        # Comment: github_issue_comment, github_commit_comment,
        #          github_pull_request_review_comment, gitlab_note
        # TODO: issue_hooks, tag_hooks, pullrequest_hooks and comment_hooks

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
            self.log.warn("Recieved webhook for repo [{repo}], but no IRC "
                          "channel is configured for it, ignoring...",
                          repo=repo_name)
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
        branch = data["ref"].split("/", 2)[-1]
        msg = ("[{repo_name}] {pusher} {action} {num_commits} commit(s) to "
               "{branch}: {compare}".format(
                   repo_name=colored(repo_name, "blue"),
                   pusher=colored(unidecode(data["pusher"]["name"]),
                                  "dark_cyan"),
                   action=action,
                   num_commits=len(data["commits"]),
                   branch=colored(branch, "dark_green"),
                   compare=url))
        self.report_to_irc(repo_name, msg)
        self.commits_to_irc(repo_name, data["commits"], github=True)
        # subset of information that is common for both GitHUb and GitLab
        # only a few useful pieces of information
        subset = {"commits": data["commits"],
                  "branch": branch,
                  "project": {"name": data["repository"]["name"],
                              "namespace": data["repository"]["full_name"].split(
                                  "/")[0],
                              "description": data["repository"]["description"],
                              "url": data["repository"]["html_url"],
                              "homepage": data["repository"]["homepage"]},
                  "pusher": {"name": data["pusher"]["name"],
                             "username": data["sender"]["login"],
                             "id": data["sender"]["id"]}}
        self.push_hooks(subset)

    @defer.inlineCallbacks
    def on_github_issues(self, data):
        action = data["action"]
        payload = None
        repo_name = data["repository"]["name"]
        if action == "assigned" or action == "unassigned":
            payload = data["issue"]["assignee"]["login"]
        elif action == "labeled" or action == "unlabeled":
            url = yield shorten_github_url(data["issue"]["html_url"])
            fg, bg = self.github_label_colors(data["label"])
            payload = "{} ({})".format(colored(data["label"]["name"],
                                               fg, bg), url)
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
            url = yield shorten_github_url(data["pull_request"]["html_url"])
            fg, bg = self.github_label_colors(data["label"])
            payload = "{} ({})".format(colored(data["label"]["name"],
                                               fg, bg), url)
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
        elif action == "ready_for_review":
            action = "marked ready for review:"
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
                   title=unidecode(data["pull_request"]["title"]),
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
        branch = data["ref"].split("/", 2)[-1]
        msg = ("[{repo_name}] {pusher} pushed {num_commits} commit(s) to "
               "{branch}".format(repo_name=colored(repo_name, "blue"),
                                 pusher=colored(data["user_name"],
                                                "dark_cyan"),
                                 num_commits=len(data["commits"]),
                                 branch=colored(branch, "dark_green")))
        self.report_to_irc(repo_name, msg)
        self.commits_to_irc(repo_name, data["commits"])
        # subset of information that is common for both GitHUb and GitLab
        # only a few useful pieces of information
        subset = {"commits": data["commits"],
                  "branch": branch,
                  "project": {"name": data["project"]["name"],
                              "namespace": data["project"]["namespace"],
                              "description": data["project"]["description"],
                              "url": data["project"]["http_url"],
                              "homepage": data["project"]["homepage"]},
                  "pusher": {"name": data["user_name"],
                             "username": data["user_username"],
                             "id": data["user_id"]}}
        self.push_hooks(subset)

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
