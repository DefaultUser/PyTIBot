# PyTIBot - IRC Bot using python and the twisted library
# Copyright (C) <2017-2023>  <Sebastian Schmidt>

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
from functools import partial
import json
import hmac
from hashlib import sha1
import re
import sys
import textwrap

from util.formatting import ColorCodes, good_contrast_with_black
from util.formatting.common import closest_colorcode
from util.formatting.irc import colored
from util.misc import str_to_bytes, bytes_to_str, filter_dict
from util.internet import shorten_url, DirectAccessor, HeaderAccessor, JsonAccessor
from lib import webhook_actions


class GitWebhookServer(Resource):
    """
    HTTP(S) Server for GitHub/Gitlab webhooks
    """
    isLeaf = True
    log = Logger()
    GH_ReviewFloodPrevention_Delay = 10

    def __init__(self, botfactory, config):
        self.botfactory = botfactory
        self.github_secret = config["GitWebhook"].get("github_secret", None)
        self.gitlab_secret = config["GitWebhook"].get("gitlab_secret", None)
        self.channels = config["GitWebhook"]["channels"]
        self.confidential_channels = config["GitWebhook"].get("confidential_channels", {})
        # filter settings
        self.filter_rules = config["GitWebhook"].get("FilterRules", [])
        self.prevent_github_review_flood = config["GitWebhook"].get(
                "PreventGitHubReviewFlood", False)
        self.hide_github_commit_list = config["GitWebhook"].get("HideGitHubCommitList", False)
        self._gh_review_buffer = []
        self._gh_review_delayed_call = None
        self._gh_review_comment_buffer = []
        self._gh_review_comment_delayed_call = None
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
        self.hook_report_success = config["GitWebhook"].get("hook_report_success", True)
        # URL shortener
        self.url_shortener = defer.succeed
        url_shortener_settings = config["GitWebhook"].get("url_shortener", None)
        if url_shortener_settings:
            try:
                service_url = url_shortener_settings["service_url"]
                method = url_shortener_settings.get("method", "POST").upper()
                headers = url_shortener_settings.get("headers", None)
                post_data = url_shortener_settings.get("post_data", None)
                request_params = url_shortener_settings.get("request_params", None)
                payload_accessor_settings = url_shortener_settings.get(
                        "payload_accessor", "DirectAccessor")
                if payload_accessor_settings == "DirectAccessor":
                    accessor = DirectAccessor()
                else:
                    if not isinstance(payload_accessor_settings, dict):
                        raise ValueError("payload_accessor requires further "
                                         "configuration")
                    type_name = payload_accessor_settings.keys()[0] # there can only be one
                    if type_name == "JsonAccessor":
                        accessor = JsonAccessor(**payload_accessor_settings[type_name])
                    elif type_name == "HeaderAccessor":
                        accessor = HeaderAccessor(**payload_accessor_settings[type_name])
                    else:
                        raise ValueError("No such payload_accessor: {}".format(type_name))
                self.url_shortener = partial(shorten_url, service_url=service_url,
                                             method=method, headers=headers,
                                             post_data=post_data,
                                             request_params=request_params,
                                             payload_accessor=accessor)
            except Exception as e:
                self.log.warn("Couldn't set up url shortener: {error}", error=e)

    def render_POST(self, request):
        body = request.content.read()
        data = json.loads(bytes_to_str(body))
        service = None
        # GitHub
        if request.getHeader(b"X-GitHub-Event"):
            eventtype = bytes_to_str(request.getHeader(b"X-GitHub-Event"))
            sig = request.getHeader(b"X-Hub-Signature")
            if sig:
                sig = sig[5:]
            service = "github"
        # Gitlab
        elif request.getHeader(b"X-Gitlab-Event"):
            eventtype = data["object_kind"]
            sig = request.getHeader(b"X-Gitlab-Token")
            service = "gitlab"
        # other: not implemented
        else:
            request.setResponseCode(403)
            return b""

        secret = None
        if service == "github":
            secret = self.github_secret
        elif service == "gitlab":
            secret = self.gitlab_secret
        if secret:
            secret = str_to_bytes(secret)
            if service == "github":
                h = hmac.new(secret, body, sha1)
                if not hmac.compare_digest(codecs.encode(h.digest(), "hex"), sig):
                    self.log.warn("Request's signature does not correspond"
                                  " with the given secret - ignoring request")
                    request.setResponseCode(200)
                    return b""
            else:
                if secret != sig:
                    self.log.warn("Request's signature does not correspond"
                                  " with the given secret - ignoring request")
                    request.setResponseCode(200)
                    return b""
        # insert pseudo keys into data for better filtering
        GitWebhookServer.insert_pseudo_data(service, data, eventtype)
        if self.filter_event(data):
            self.log.debug("filtering out event {event}", event=data)
        elif hasattr(self, "on_{}_{}".format(service, eventtype)):
            reactor.callLater(0, getattr(self, "on_{}_{}".format(service,
                                                                 eventtype)),
                              data)
        else:
            self.log.warn("Event {eventtype} not implemented for service "
                          "{service}", eventtype=eventtype, service=service)
        # always return 200
        request.setResponseCode(200)
        return b""

    @staticmethod
    def insert_pseudo_data(service, data, eventtype):
        """
        Insert additional filter data into webhook data to enable better
        reporting and filtering for cases that are not covered by the
        webhook APIs.
        """
        # filtering: inject eventtype for filtering
        data["eventtype"] = eventtype
        if service == "gitlab":
            if data["object_kind"] == "merge_request":
                action = data["object_attributes"]["action"]
                if action == "update":
                    if "title" in data["changes"]:
                        previous = data["changes"]["title"]["previous"]
                        current = data["changes"]["title"]["current"]
                        if current == "Draft: " + previous:
                            action = "mark_as_draft"
                        elif previous == "Draft: " + current:
                            action = "mark_as_ready"
                data["object_attributes"]["_extended_action"] = action


    def filter_event(self, data):
        """
        Returns True if the event should be filtered out according to user rules
        """
        return any(filter_dict(data, rule) for rule in self.filter_rules)

    def github_label_colors(self, label):
        color = label["color"]
        try:
            if not color.startswith("#"):
                color = "#" + color
            bg = closest_colorcode(color)
            fg = ColorCodes.black if good_contrast_with_black[bg] else ColorCodes.white
        except Exception as e:
            self.log.error("Issue label: could not find a closest IRC "
                           "color for colorcode '{color}' ({error})",
                           color=color, error=e)
            bg = None
            fg = ColorCodes.dark_green
        return fg, bg

    def report_hook_success_msg(self, success, actionname):
        """
        Send a success or fail message to the 'hook_report_users'
        """
        if self.botfactory.bot is None:
            return
        if isinstance(success, Failure):
            message = "Hook {} failed: {}".format(colored(actionname, ColorCodes.blue,
                                                          ColorCodes.gray),
                                                  success.getErrorMessage())
        elif self.hook_report_success:
            message = "Hook {} finished without errors".format(
                colored(actionname, ColorCodes.blue, ColorCodes.gray))
        else:
            return
        for user in self.hook_report_users:
            self.botfactory.bot.msg(user, message)

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
        for hook in hooks:
            filters = hook.get("filter", [])
            if any(filter_dict(data, rule) for rule in filters):
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

    def report_to_irc(self, repo_name, message, confidential=False):
        if self.botfactory.bot is None:
            return
        channels = []
        channel_config = self.confidential_channels if confidential else self.channels
        if repo_name in channel_config:
            channels = channel_config[repo_name]
        elif "default" in channel_config:
            channels = channel_config["default"]
        if not isinstance(channels, list):
            # don't error out if the config has a string instead of a list
            channels = [channels]
        if not channels:
            self.log.warn("Recieved webhook for repo [{repo}], but no IRC "
                          "channel is configured for it, ignoring...",
                          repo=repo_name)
            return
        for channel in channels:
            self.botfactory.bot.msg(channel, message)

    @defer.inlineCallbacks
    def format_commits(self, commits, num_commits):
        msg = ""
        for i, commit in enumerate(commits):
            if i == 3 and num_commits != 4:
                msg += "\n+{} more commits".format(num_commits - 3)
                break
            url = yield self.url_shortener(commit["url"])
            message = commit["message"].split("\n")[0]
            if i != 0:
                msg += "\n"
            msg += "{author}: {message} ({url})".format(
                        author=colored(commit["author"]["name"],
                                       ColorCodes.dark_cyan),
                        message=textwrap.shorten(message, 100), url=url)
        return msg

    @defer.inlineCallbacks
    def on_github_push(self, data):
        url = yield self.url_shortener(data["compare"])
        repo_name = data["repository"]["name"]
        branch = data["ref"].split("/", 2)[-1]
        action = "pushed"
        # don't send any message to the chat if the push event was a deletion
        # as this is already handled by the "delete" event, but still trigger
        # the push hooks as they might be required
        if not data["deleted"]:
            if data["forced"]:
                action = colored("force pushed", ColorCodes.red)
            msg = ("[{repo_name}] {pusher} {action} {num_commits} commit(s) to "
                   "{branch}: {compare}".format(
                       repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
                       pusher=colored(data["pusher"]["name"],
                                      ColorCodes.dark_cyan),
                       action=action,
                       num_commits=len(data["commits"]),
                       branch=colored(branch, ColorCodes.dark_green),
                       compare=url))
            if not self.hide_github_commit_list:
                commit_msgs = yield self.format_commits(data["commits"],
                                                        len(data["commits"]))
                if commit_msgs:
                    msg += "\n" + commit_msgs
            self.report_to_irc(repo_name, msg)
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
            url = yield self.url_shortener(data["issue"]["html_url"])
            fg, bg = self.github_label_colors(data["label"])
            payload = "{} ({})".format(colored(data["label"]["name"],
                                               fg, bg), url)
        elif action == "milestoned":
            payload = data["issue"]["milestone"]["title"]
        elif action == "opened":
            action = colored(action, ColorCodes.red)
        elif action == "reopened":
            action = colored(action, ColorCodes.red)
        elif action == "closed":
            action = colored(action, ColorCodes.dark_green)
        if not payload:
            payload = yield self.url_shortener(data["issue"]["html_url"])
        msg = ("[{repo_name}] {user} {action} Issue #{number} {title}: "
               "{payload}".format(repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
                                  user=colored(data["sender"]["login"],
                                               ColorCodes.dark_cyan),
                                  action=action,
                                  number=colored(str(data["issue"]["number"]),
                                                 ColorCodes.dark_yellow),
                                  title=data["issue"]["title"],
                                  payload=payload))
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_issue_comment(self, data):
        url = yield self.url_shortener(data["comment"]["html_url"])
        repo_name = data["repository"]["name"]
        msg = ("[{repo_name}] {user} {action} comment on Issue #{number} "
               "{title} {url}".format(
                   repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
                   user=colored(data["comment"]["user"]["login"],
                                ColorCodes.dark_cyan),
                   action=data["action"],
                   number=colored(str(data["issue"]["number"]),
                                  ColorCodes.dark_yellow),
                   title=data["issue"]["title"],
                   url=url))
        self.report_to_irc(repo_name, msg)

    def on_github_create(self, data):
        repo_name = data["repository"]["name"]
        msg = "[{repo_name}] {user} created {ref_type} {ref}".format(
            repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
            user=colored(data["sender"]["login"], ColorCodes.dark_cyan),
            ref_type=data["ref_type"],
            ref=colored(data["ref"], ColorCodes.dark_magenta))
        self.report_to_irc(repo_name, msg)

    def on_github_delete(self, data):
        repo_name = data["repository"]["name"]
        msg = "[{repo_name}] {user} {action} {ref_type} {ref}".format(
            repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
            user=colored(data["sender"]["login"], ColorCodes.dark_cyan),
            action=colored("deleted", ColorCodes.red),
            ref_type=data["ref_type"],
            ref=colored(data["ref"], ColorCodes.dark_magenta))
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_fork(self, data):
        repo_name = data["repository"]["name"]
        url = yield self.url_shortener(data["forkee"]["html_url"])
        msg = "[{repo_name}] {user} created fork {url}".format(
            repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
            user=colored(data["forkee"]["owner"]["login"], ColorCodes.dark_cyan),
            url=url)
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_commit_comment(self, data):
        repo_name = data["repository"]["name"]
        url = yield self.url_shortener(data["comment"]["html_url"])
        msg = "[{repo_name}] {user} commented on commit {url}".format(
            repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
            user=colored(data["comment"]["user"]["login"], ColorCodes.dark_cyan),
            url=url)
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_release(self, data):
        repo_name = data["repository"]["name"]
        action = data["action"]
        if action in ("published", "created", "released"):
            action = colored(action, ColorCodes.dark_green)
        elif action == "prereleased":
            action = colored(action, ColorCodes.dark_cyan)
        elif action in ("unpublished", "deleted"):
            action = colored(action, ColorCodes.red)
        type_ = ""
        if data["release"]["draft"]:
            type_ = " (Draft)"
        elif data["release"]["prerelease"]:
            type_ = " (Prerelease)"
        release_name = data["release"]["name"] or data["release"]["tag_name"]
        user = data["sender"]["login"]
        url = yield self.url_shortener(data["release"]["html_url"])
        msg = ("[{repo_name}] {user} {action} release {release_name}{type_} "
               "({url})".format(user=user, action=action,
                                release_name=colored(release_name,
                                                     ColorCodes.dark_yellow),
                                type_=type_,
                                repo_name=colored(data["repository"]["name"],
                                                  ColorCodes.blue,
                                                  ColorCodes.gray),
                                url=url))
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_github_pull_request(self, data):
        action = data["action"]
        payload = None
        repo_name = data["repository"]["name"]
        user = data["sender"]["login"]
        if action == "assigned" or action == "unassigned":
            payload = data["pull_request"]["assignee"]["login"]
        elif action == "labeled" or action == "unlabeled":
            url = yield self.url_shortener(data["pull_request"]["html_url"])
            fg, bg = self.github_label_colors(data["label"])
            payload = "{} ({})".format(colored(data["label"]["name"],
                                               fg, bg), url)
        elif action == "milestoned":
            payload = data["pull_request"]["milestone"]["title"]
        elif action == "review_requested":
            action = "requested review for"
            payload = data["requested_reviewer"]["login"]
        elif action == "review_request_removed":
            action = "removed review request for"
            payload = data["requested_reviewer"]["login"]
        elif action == "opened":
            action = colored(action, ColorCodes.dark_green)
        elif action == "reopened":
            action = colored(action, ColorCodes.dark_green)
        elif action == "closed":
            if data["pull_request"]["merged"]:
                action = colored("merged", ColorCodes.dark_green)
                user = data["pull_request"]["merged_by"]["login"]
            else:
                action = colored(action, ColorCodes.red)
        elif action == "synchronize":
            action = "synchronized"
        elif action == "ready_for_review":
            action = "marked ready for review:"
        elif action == "converted_to_draft":
            action = "converted to draft:"
        if not payload:
            payload = yield self.url_shortener(
                data["pull_request"]["html_url"])
        msg = ("[{repo_name}] {user} {action} Pull Request #{number} {title} "
               "({head} -> {base}): {payload}".format(
                   repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
                   user=colored(user, ColorCodes.dark_cyan),
                   action=action,
                   number=colored(str(data["pull_request"]["number"]),
                                  ColorCodes.dark_yellow),
                   title=data["pull_request"]["title"],
                   head=colored(data["pull_request"]["head"]["ref"],
                                ColorCodes.magenta),
                   base=colored(data["pull_request"]["base"]["ref"],
                                ColorCodes.dark_red),
                   payload=payload))
        self.report_to_irc(repo_name, msg)

    def _github_PR_review_send_msg(self, is_comment, repo_name, user,
                                   pr_number, title, action, head, base, urls):
        type_ = "Review Comment" if is_comment else "Review"
        msg = ("[{repo_name}] {user} {action} {type_} for Pull Request "
               "#{number} {title} ({head} -> {base}): {url}".format(
                   repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
                   user=colored(user, ColorCodes.dark_cyan),
                   action=action,
                   type_=type_,
                   number=colored(pr_number, ColorCodes.dark_yellow),
                   title=title,
                   head=colored(head, ColorCodes.magenta),
                   base=colored(base, ColorCodes.dark_red),
                   url=", ".join(urls)))
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def github_handle_review_flood(self, is_comment):
        # Clear buffer and callID first as later async calls give control
        # back to the reactor. This way, the buffer could be changed in the
        # middle of this function and events could be lost
        if is_comment:
            buffer = self._gh_review_comment_buffer
            self._gh_review_comment_buffer = []
            self._gh_review_comment_delayed_call = None
            type_ = "comment"
        else:
            buffer = self._gh_review_buffer
            self._gh_review_buffer = []
            self._gh_review_delayed_call = None
            type_ = "review"
        partition = {}
        for event in buffer:
            repo_name = event["repository"]["name"]
            user = event[type_]["user"]["login"]
            pr_number = event["pull_request"]["number"]
            action = event["action"]
            key = (repo_name, pr_number, user, action)
            if key not in partition:
                partition[key] = []
            partition[key].append(event)
        for k, events in partition.items():
            repo_name, pr_number, user, action = k
            title = events[0]["pull_request"]["title"]
            head = events[0]["pull_request"]["head"]["ref"]
            base = events[0]["pull_request"]["base"]["ref"]
            # remove duplicate urls
            full_urls = {e[type_]["html_url"] for e in events}
            urls_defers = [self.url_shortener(url) for url in full_urls]
            results = yield defer.DeferredList(urls_defers)
            urls = [res[1] for res in results]
            self._github_PR_review_send_msg(is_comment, repo_name, user,
                                            pr_number, title, action, head,
                                            base, urls)

    @defer.inlineCallbacks
    def on_github_pull_request_review(self, data):
        if self.prevent_github_review_flood:
            self._gh_review_buffer.append(data)
            if self._gh_review_delayed_call:
                self._gh_review_delayed_call.cancel()
            self._gh_review_delayed_call = reactor.callLater(
                    GitWebhookServer.GH_ReviewFloodPrevention_Delay,
                    self.github_handle_review_flood, False)
        else:
            url = yield self.url_shortener(data["review"]["html_url"])
            self._github_PR_review_send_msg(
                False,
                data["repository"]["name"],
                data["review"]["user"]["login"],
                data["pull_request"]["number"],
                data["pull_request"]["title"],
                data["action"],
                data["pull_request"]["head"]["ref"],
                data["pull_request"]["base"]["ref"],
                [url])

    @defer.inlineCallbacks
    def on_github_pull_request_review_comment(self, data):
        if self.prevent_github_review_flood:
            self._gh_review_comment_buffer.append(data)
            if self._gh_review_comment_delayed_call:
                self._gh_review_comment_delayed_call.cancel()
            self._gh_review_comment_delayed_call = reactor.callLater(
                    GitWebhookServer.GH_ReviewFloodPrevention_Delay,
                    self.github_handle_review_flood, True)
        else:
            url = yield self.url_shortener(data["comment"]["html_url"])
            self._github_PR_review_send_msg(
                True,
                data["repository"]["name"],
                data["comment"]["user"]["login"],
                data["pull_request"]["number"],
                data["pull_request"]["title"],
                data["action"],
                data["pull_request"]["head"]["ref"],
                data["pull_request"]["base"]["ref"],
                [url])

    @defer.inlineCallbacks
    def on_gitlab_push(self, data):
        repo_name = data["project"]["name"]
        branch = data["ref"].split("/", 2)[-1]
        if data["checkout_sha"] is None:
            action = colored("deleted", ColorCodes.red)
            msg = ("[{repo_name}] {pusher} {action} branch {branch}".format(
                repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
                pusher=colored(data["user_name"], ColorCodes.dark_cyan),
                action=action,
                branch=colored(branch, ColorCodes.dark_green)))
        else:
            msg = ("[{repo_name}] {pusher} pushed {num_commits} commit(s) to "
                   "{branch}".format(repo_name=colored(repo_name, ColorCodes.blue,
                                                       ColorCodes.gray),
                                     pusher=colored(data["user_name"],
                                                    ColorCodes.dark_cyan),
                                     num_commits=data["total_commits_count"],
                                     branch=colored(branch, ColorCodes.dark_green)))
        commit_msgs = yield self.format_commits(data["commits"],
                                                int(data["total_commits_count"]))
        if commit_msgs:
            msg += "\n" + commit_msgs
        self.report_to_irc(repo_name, msg)
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

    @defer.inlineCallbacks
    def on_gitlab_tag_push(self, data):
        repo_name = data["project"]["name"]
        msg = ("[{repo_name}] {pusher} added tag {tag}".format(
            repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
            pusher=colored(data["user_name"], ColorCodes.dark_cyan),
            tag=colored(data["ref"].split("/", 2)[-1], ColorCodes.dark_green)))
        commit_msgs = yield self.format_commits(data["commits"],
                                                int(data["total_commits_count"]))
        if commit_msgs:
            msg += "\n" + commit_msgs
        self.report_to_irc(repo_name, msg)

    @defer.inlineCallbacks
    def on_gitlab_issue(self, data):
        repo_name = data["project"]["name"]
        attribs = data["object_attributes"]
        action = attribs["action"]
        if action == "open":
            action = colored("opened", ColorCodes.red)
        elif action == "reopen":
            action = colored("reopened", ColorCodes.red)
        elif action == "close":
            action = colored("closed", ColorCodes.dark_green)
        elif action == "update":
            action = "updated"
        url = yield self.url_shortener(attribs["url"])
        msg = ("[{repo_name}] {user} {action} Issue #{number} {title} "
               "{url}".format(repo_name=colored(repo_name, ColorCodes.blue,
                                                ColorCodes.gray),
                              user=colored(data["user"]["name"],
                                           ColorCodes.dark_cyan),
                              action=action,
                              number=colored(str(attribs["iid"]),
                                             ColorCodes.dark_yellow),
                              title=attribs["title"],
                              url=url))
        self.report_to_irc(repo_name, msg, confidential=attribs.get("confidential", False))

    @defer.inlineCallbacks
    def on_gitlab_note(self, data):
        repo_name = data["project"]["name"]
        attribs = data["object_attributes"]
        noteable_type = attribs["noteable_type"]
        confidential = data["event_type"] == "confidential_note"
        id_prefix = ""
        if noteable_type == "Commit":
            id = attribs["commit_id"]
            title = data["commit"]["message"].split("\n")[0]
            if len(title) > 100:
                title = title[:100] + "..."
        elif noteable_type == "MergeRequest":
            id = data["merge_request"]["iid"]
            title = data["merge_request"]["title"]
            noteable_type = "Merge Request"
            id_prefix = "!"
        elif noteable_type == "Issue":
            id = data["issue"]["iid"]
            title = data["issue"]["title"]
            id_prefix = "#"
        elif noteable_type == "Snippet":
            id = data["snippet"]["id"]
            title = data["snippet"]["title"]
        else:
            return
        url = yield self.url_shortener(attribs["url"])
        msg = ("[{repo_name}] {user} commented on {noteable_type} {id_prefix}{number} "
               "{title} {url}".format(
                   repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
                   user=colored(data["user"]["name"], ColorCodes.dark_cyan),
                   noteable_type=noteable_type,
                   id_prefix=id_prefix,
                   number=colored(str(id), ColorCodes.dark_yellow),
                   title=title,
                   url=url))
        self.report_to_irc(repo_name, msg, confidential=confidential)

    @defer.inlineCallbacks
    def on_gitlab_merge_request(self, data):
        attribs = data["object_attributes"]
        repo_name = attribs["target"]["name"]
        action = attribs["_extended_action"]
        if action == "open":
            action = colored("opened", ColorCodes.dark_green)
        elif action == "reopen":
            action = colored("reopened", ColorCodes.dark_green)
        elif action == "close":
            action = colored("closed", ColorCodes.red)
        elif action == "merge":
            action = colored("merged", ColorCodes.dark_green)
        elif action == "update":
            action = "updated"
        elif action == "mark_as_draft":
            action = colored("marked as draft:", ColorCodes.gray)
        elif action == "mark_as_ready":
            action = colored("marked as ready:", ColorCodes.dark_green)
        elif action == "approved":
            action = colored("approved", ColorCodes.dark_green)
        elif action == "approval":
            action = colored("added approval for", ColorCodes.dark_green)
        elif action == "unapproved":
            action = colored("unapproved", ColorCodes.dark_yellow)
        elif action == "unapproval":
            action = colored("removed approval for", ColorCodes.dark_yellow)
        url = yield self.url_shortener(attribs["url"])
        msg = ("[{repo_name}] {user} {action} Merge Request !{number} "
               "{title} ({source} -> {target}): {url}".format(
                   repo_name=colored(repo_name, ColorCodes.blue, ColorCodes.gray),
                   user=colored(data["user"]["name"], ColorCodes.dark_cyan),
                   action=action,
                   number=colored(str(attribs["iid"]), ColorCodes.dark_yellow),
                   title=attribs["title"],
                   source=colored(attribs["source_branch"], ColorCodes.magenta),
                   target=colored(attribs["target_branch"], ColorCodes.dark_red),
                   url=url))
        self.report_to_irc(repo_name, msg)
