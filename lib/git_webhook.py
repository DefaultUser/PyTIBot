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
from twisted.web.template import Tag, tags
from twisted.internet import reactor, defer
from twisted.python.failure import Failure
from twisted.logger import Logger
import codecs
from functools import partial
import json
import hmac
from hashlib import sha1
import textwrap

from util.formatting import ColorCodes, good_contrast_with_black, colored, from_human_readable
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

    # `a` tag to work around bug in element that automatically links text that remotely looks like an URL
    reponame_stub = '[<a><font color="lime"><t:slot name="repo_name"/></font></a>]'
    author_stub = '<font color="darkcyan"><t:slot name="author"/></font>'
    user_stub = '<font color="darkcyan"><t:slot name="user"/></font>'
    action_stub = '<font><t:attr name="color"><t:slot name="actioncolor"/></t:attr><t:slot name="action"/></font>'
    issue_description_stub = 'Issue #<font color="darkorange"><t:slot name="issue_id"/></font> <a><t:attr name="href"><t:slot name="issue_url"/></t:attr><t:slot name="issue_title"/></a>'
    pr_description_stub = 'Pull Request #<font color="darkorange"><t:slot name="pr_id"/></font> <a><t:attr name="href"><t:slot name="pr_url"/></t:attr><t:slot name="pr_title"/> (<font color="magenta"><t:slot name="head"/></font>-&gt;<font color="red"><t:slot name="base"/></font>)</a>'
    pr_description_without_href_stub = 'Pull Request #<font color="darkorange"><t:slot name="pr_id"/></font> <t:slot name="pr_title"/> (<font color="magenta"><t:slot name="head"/></font>-&gt;<font color="red"><t:slot name="base"/></font>)'
    ref_stub = '<t:slot name="ref_type"/> <font color="magenta"><t:slot name="ref"/></font>'

    push_stub = from_human_readable(f'{reponame_stub} {user_stub} pushed <t:slot name="num_commits"/> commit(s) to <font color="magenta"><t:slot name="branch"/></font>')
    github_push_stub = from_human_readable(f'{reponame_stub} {user_stub} {action_stub} <a><t:attr name="href"><t:slot name="compare_url"/></t:attr><t:slot name="num_commits"/> commit(s) to <font color="magenta"><t:slot name="branch"/></font></a>')
    commit_stub = from_human_readable(f'{author_stub}: <a><t:attr name="href"><t:slot name="url"/></t:attr><t:slot name="message"/></a>')
    issue_stub = from_human_readable(f'{reponame_stub} {user_stub} {action_stub} {issue_description_stub}')
    issue_comment_stub = from_human_readable(f'{reponame_stub} {user_stub} {action_stub} <a><t:attr name="href"><t:slot name="comment_url"/></t:attr>comment</a> on {issue_description_stub}')
    pr_stub = from_human_readable(f'{reponame_stub} {user_stub} {action_stub} {pr_description_stub}')
    pr_review_stub = from_human_readable(f'{reponame_stub} {user_stub} <t:slot name="action"/> <t:slot name="review_type"/> for {pr_description_without_href_stub}: ')
    create_stub = from_human_readable(f'{reponame_stub} {user_stub} created {ref_stub}')
    delete_stub = from_human_readable(f'{reponame_stub} {user_stub} <font color="red">deleted</font> {ref_stub}')
    fork_stub = from_human_readable(f'{reponame_stub} {user_stub} created <a><t:attr name="href"><t:slot name="url"/></t:attr>fork</a>')
    commit_comment_stub = from_human_readable(f'{reponame_stub} {user_stub} commented on <a><t:attr name="href"><t:slot name="url"/></t:attr>commit <t:slot name="commit_id"/></a>')
    release_stub = from_human_readable(f'{reponame_stub} {user_stub} {action_stub} <a><t:attr name="href"><t:slot name="url"/></t:attr>release <t:slot name="release_name"/></a>')
    gitlab_note_stub = from_human_readable(f'{reponame_stub} {user_stub} commented on <t:slot name="noteable_type"/> <t:slot name="id_prefix"/><font color="darkorange"><t:slot name="id"/></font> <a><t:attr name="href"><t:slot name="url"/></t:attr><t:slot name="title"/></a>')
    gitlab_mr_stub = from_human_readable(f'{reponame_stub} {user_stub} {action_stub} Merge Request !<font color="darkorange"><t:slot name="id"/></font> <a><t:attr name="href"><t:slot name="url"/></t:attr><t:slot name="title"/> (<font color="magenta"><t:slot name="source"/></font>-&gt;<font color="red"><t:slot name="target"/></font>)</a>')

    def __init__(self, botfactory, config):
        self.botfactory = botfactory
        self.github_secret = config["GitWebhook"].get("github_secret", None)
        self.gitlab_secret = config["GitWebhook"].get("gitlab_secret", None)
        self.channels = GitWebhookServer._setup_report_channels(
            config["GitWebhook"]["channels"])
        self.confidential_channels = GitWebhookServer._setup_report_channels(
            config["GitWebhook"].get("confidential_channels", {}))
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

    @staticmethod
    def _setup_report_channels(config: dict[str, list[str]]) -> dict[str, dict[str, list[str]]]:
        channel_setup = {}
        for key, chanlist in config.items():
            if "/" in key:
                space, repo = key.rsplit("/", 1)
            else:
                space = "*"
                repo = key
            if space == "default":
                space = "*"
            if repo == "default":
                repo = "*"
            space = space.lower()
            repo = repo.lower()
            if space not in channel_setup:
                channel_setup[space] = {}
            channel_setup[space][repo] = chanlist
        return channel_setup

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
        bg = "#" + label["color"]
        fg = ColorCodes.black if good_contrast_with_black(bg) else ColorCodes.white
        return fg, bg

    def report_hook_success_msg(self, success, actionname):
        """
        Send a success or fail message to the 'hook_report_users'
        """
        if self.botfactory.bot is None:
            return
        if isinstance(success, Failure):
            message = Tag("")("Hook ", colored(actionname, ColorCodes.red),
                              " failed: {}".format(success.getErrorMessage()))
        elif self.hook_report_success:
            message = Tag("")("Hook ", colored(actionname, ColorCodes.lime),
                              " finished without errors")
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

    def report_to_chat(self, repo_name, repo_space, message, confidential=False):
        if self.botfactory.bot is None:
            return
        channel_config = self.confidential_channels if confidential else self.channels
        repo_space = repo_space.lower()
        repo_name = repo_name.lower()
        config_space = repo_space if repo_space in channel_config else "*"
        config_repo = repo_name if repo_name in channel_config[config_space] else "*"
        try:
            channels = channel_config[config_space][config_repo]
        except KeyError:
            self.log.warn("Recieved webhook for repo [{space}/{repo}], but no chat "
                          "channel is configured for it, ignoring...",
                          space=repo_space, repo=repo_name)
            return
        if not isinstance(channels, list):
            # don't error out if the config has a string instead of a list
            channels = [channels]
        for channel in channels:
            self.botfactory.bot.msg(channel, message)

    @staticmethod
    def _github_get_namespace(data):
        return data["repository"]["full_name"].rsplit("/", 1)[0]

    @staticmethod
    def _gitlab_get_namespace(data):
        # use `path_with_namespace` to capture all groups and subgroups
        return data["project"]["path_with_namespace"].rsplit("/", 1)[0]

    @defer.inlineCallbacks
    def format_commits(self, commits, num_commits):
        msg = Tag("")
        for i, commit in enumerate(commits):
            if i == 3 and num_commits != 4:
                msg.children.append(tags.br)
                msg.children.append("+{} more commits".format(num_commits - 3))
                break
            url = yield self.url_shortener(commit["url"])
            message = commit["message"].split("\n")[0]
            if i != 0:
                msg.children.append(tags.br)
            line = GitWebhookServer.commit_stub.clone()
            line.fillSlots(author=commit["author"]["name"],
                           message=textwrap.shorten(message, 100),
                           url=url)
            msg.children.append(line)
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
            actioncolor = ColorCodes.darkgreen
            if data["forced"]:
                action = "force pushed"
                actioncolor = ColorCodes.red
            msg = GitWebhookServer.github_push_stub.clone()
            # NOTE: num_commits is limited to 20, but GitHub doesn't send the
            # exact number
            msg.fillSlots(repo_name=repo_name, user=data["pusher"]["name"],
                          action=action, actioncolor=actioncolor,
                          num_commits=str(len(data["commits"])),
                          branch=branch, compare_url=url)
            if not self.hide_github_commit_list:
                commit_msgs = yield self.format_commits(data["commits"],
                                                        len(data["commits"]))
                msg.children.append(tags.br)
                msg.children.append(commit_msgs)
            self.report_to_chat(repo_name,
                                GitWebhookServer._github_get_namespace(data),
                                msg)
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
        actioncolor = ColorCodes.darkorange
        if action == "assigned" or action == "unassigned":
            payload = data["issue"]["assignee"]["login"]
        elif action == "labeled" or action == "unlabeled":
            url = yield self.url_shortener(data["issue"]["html_url"])
            fg, bg = self.github_label_colors(data["label"])
            payload = colored(data["label"]["name"], fg, bg)
        elif action == "milestoned":
            payload = data["issue"]["milestone"]["title"]
        elif action == "opened":
            actioncolor = ColorCodes.red
        elif action == "reopened":
            actioncolor = ColorCodes.red
        elif action == "closed":
            actioncolor = ColorCodes.darkgreen
        msg = GitWebhookServer.issue_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=data["sender"]["login"],
                      action=action, actioncolor=actioncolor,
                      issue_id=str(data["issue"]["number"]),
                      issue_title=data["issue"]["title"],
                      issue_url=data["issue"]["html_url"])
        if payload:
            msg.children.append(": ")
            msg.children.append(payload)
        self.report_to_chat(repo_name,
                            GitWebhookServer._github_get_namespace(data),
                            msg)

    @defer.inlineCallbacks
    def on_github_issue_comment(self, data):
        comment_url = yield self.url_shortener(data["comment"]["html_url"])
        issue_url = yield self.url_shortener(data["issue"]["html_url"])
        repo_name = data["repository"]["name"]
        action = data["action"]
        if action == "created":
            actioncolor = ColorCodes.darkgreen
        elif action == "edited":
            actioncolor = ColorCodes.darkorange
        else:
            actioncolor = ColorCodes.red
        msg = GitWebhookServer.issue_comment_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=data["comment"]["user"]["login"],
                      action=action, actioncolor=actioncolor,
                      issue_id=str(data["issue"]["number"]),
                      issue_title=data["issue"]["title"],
                      issue_url=issue_url,
                      comment_url=comment_url)
        self.report_to_chat(repo_name,
                            GitWebhookServer._github_get_namespace(data),
                            msg)

    def on_github_create(self, data):
        repo_name = data["repository"]["name"]
        msg = GitWebhookServer.create_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=data["sender"]["login"],
                      ref_type=data["ref_type"], ref=data["ref"])
        self.report_to_chat(repo_name,
                            GitWebhookServer._github_get_namespace(data),
                            msg)

    def on_github_delete(self, data):
        repo_name = data["repository"]["name"]
        msg = GitWebhookServer.delete_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=data["sender"]["login"],
                      ref_type=data["ref_type"], ref=data["ref"])
        self.report_to_chat(repo_name,
                            GitWebhookServer._github_get_namespace(data),
                            msg)

    @defer.inlineCallbacks
    def on_github_fork(self, data):
        repo_name = data["repository"]["name"]
        url = yield self.url_shortener(data["forkee"]["html_url"])
        msg = GitWebhookServer.fork_stub.clone()
        msg.fillSlots(repo_name=repo_name,
                      user=data["forkee"]["owner"]["login"],
                      url=url)
        self.report_to_chat(repo_name,
                            GitWebhookServer._github_get_namespace(data),
                            msg)

    @defer.inlineCallbacks
    def on_github_commit_comment(self, data):
        repo_name = data["repository"]["name"]
        url = yield self.url_shortener(data["comment"]["html_url"])
        msg = GitWebhookServer.commit_comment_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=data["comment"]["user"]["login"],
                      commit_id=data["comment"]["commit_id"], url=url)
        self.report_to_chat(repo_name,
                            GitWebhookServer._github_get_namespace(data),
                            msg)

    @defer.inlineCallbacks
    def on_github_release(self, data):
        repo_name = data["repository"]["name"]
        action = data["action"]
        actioncolor = ColorCodes.darkorange
        if action in ("published", "created", "released"):
            actioncolor = ColorCodes.darkgreen
        elif action == "prereleased":
            actioncolor = ColorCodes.darkcyan
        elif action in ("unpublished", "deleted"):
            actioncolor = ColorCodes.red
        release_name = data["release"]["name"] or data["release"]["tag_name"]
        if data["release"]["draft"]:
            release_name += " (Draft)"
        elif data["release"]["prerelease"]:
            release_name += " (Prerelease)"
        user = data["sender"]["login"]
        url = yield self.url_shortener(data["release"]["html_url"])
        msg = GitWebhookServer.release_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=user, action=action,
                      actioncolor=actioncolor, release_name=release_name,
                      url=url)
        self.report_to_chat(repo_name,
                            GitWebhookServer._github_get_namespace(data),
                            msg)

    @defer.inlineCallbacks
    def on_github_pull_request(self, data):
        action = data["action"]
        payload = None
        repo_name = data["repository"]["name"]
        user = data["sender"]["login"]
        actioncolor = ColorCodes.darkorange
        if action == "assigned" or action == "unassigned":
            payload = data["pull_request"]["assignee"]["login"]
        elif action == "labeled" or action == "unlabeled":
            url = yield self.url_shortener(data["pull_request"]["html_url"])
            fg, bg = self.github_label_colors(data["label"])
            payload = tags.a(colored(data["label"]["name"], fg, bg), href=url)
        elif action == "milestoned":
            action = "set milestone"
            payload = data["pull_request"]["milestone"]["title"]
        elif action == "review_requested":
            action = "requested review for"
            payload = data["requested_reviewer"]["login"]
        elif action == "review_request_removed":
            action = "removed review request for"
            payload = data["requested_reviewer"]["login"]
        elif action == "opened":
            actioncolor = ColorCodes.darkgreen
        elif action == "reopened":
            actioncolor = ColorCodes.darkgreen
        elif action == "closed":
            if data["pull_request"]["merged"]:
                action = "merged"
                actioncolor = ColorCodes.darkgreen
                user = data["pull_request"]["merged_by"]["login"]
            else:
                actioncolor = ColorCodes.red
        elif action == "synchronize":
            action = "synchronized"
        elif action == "ready_for_review":
            action = "marked ready for review:"
        elif action == "converted_to_draft":
            action = "converted to draft:"
        url = yield self.url_shortener(data["pull_request"]["html_url"])
        msg = GitWebhookServer.pr_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=user, action=action,
                      actioncolor=actioncolor,
                      pr_number=str(data["pull_request"]["number"]),
                      pr_title=data["pull_request"]["title"],
                      pr_url=url, head=data["pull_request"]["head"]["ref"],
                      base=data["pull_request"]["head"]["ref"])
        if payload:
            msg.children.append(": ")
            msg.children.append(payload)
        self.report_to_chat(repo_name,
                            GitWebhookServer._github_get_namespace(data),
                            msg)

    def _github_PR_review_send_msg(self, is_comment, repo_name, repo_space, user,
                                   pr_number, title, action, head, base, urls):
        review_type = "Review Comment" if is_comment else "Review"
        msg = GitWebhookServer.pr_review_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=user, action=action,
                      review_type=review_type, pr_id=str(pr_number),
                      pr_title=title, head=head, base=base)
        for i, url in enumerate(urls):
            if i != 0:
                msg.children.append(", ")
            msg.children.append(tags.a(str(i), href=url))
        self.report_to_chat(repo_name, repo_space, msg)

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
            repo_space = GitWebhookServer._github_get_namespace(event)
            repo_name = event["repository"]["name"]
            user = event[type_]["user"]["login"]
            pr_number = event["pull_request"]["number"]
            action = event["action"]
            key = (repo_space, repo_name, pr_number, user, action)
            if key not in partition:
                partition[key] = []
            partition[key].append(event)
        for k, events in partition.items():
            repo_space, repo_name, pr_number, user, action = k
            title = events[0]["pull_request"]["title"]
            head = events[0]["pull_request"]["head"]["ref"]
            base = events[0]["pull_request"]["base"]["ref"]
            # remove duplicate urls
            full_urls = {e[type_]["html_url"] for e in events}
            urls_defers = [self.url_shortener(url) for url in full_urls]
            results = yield defer.DeferredList(urls_defers)
            urls = [res[1] for res in results]
            self._github_PR_review_send_msg(is_comment, repo_name, repo_space,
                                            user, pr_number, title, action,
                                            head, base, urls)

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
                GitWebhookServer._github_get_namespace(data),
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
                GitWebhookServer._github_get_namespace(data),
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
            msg = GitWebhookServer.delete_stub.clone()
            msg.fillSlots(repo_name=repo_name, user=data["user_name"],
                          ref_type="branch", ref=branch)
        else:
            msg = GitWebhookServer.push_stub.clone()
            msg.fillSlots(repo_name=repo_name, user=data["user_name"],
                          num_commits=str(data["total_commits_count"]),
                          branch=branch)
        commit_msgs = yield self.format_commits(data["commits"],
                                                int(data["total_commits_count"]))
        if commit_msgs:
            msg.children.append(tags.br)
            msg.children.append(commit_msgs)
        self.report_to_chat(repo_name,
                            GitWebhookServer._gitlab_get_namespace(data),
                            msg)
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
        msg = GitWebhookServer.create_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=data["user_name"],
                      ref_type="tag", ref=data["ref"].split("/", 2)[-1])
        commit_msgs = yield self.format_commits(data["commits"],
                                                int(data["total_commits_count"]))
        if commit_msgs:
            msg.children.append(tags.br)
            msg.children.append(commit_msgs)
        self.report_to_chat(repo_name,
                            GitWebhookServer._gitlab_get_namespace(data),
                            msg)

    @defer.inlineCallbacks
    def on_gitlab_issue(self, data):
        repo_name = data["project"]["name"]
        attribs = data["object_attributes"]
        action = attribs["action"]
        actioncolor = ColorCodes.darkorange
        if action == "open":
            action = "opened"
            actioncolor = ColorCodes.red
        elif action == "reopen":
            action = "reopened"
            actioncolor = ColorCodes.red
        elif action == "close":
            action = "closed"
            actioncolor = ColorCodes.darkgreen
        elif action == "update":
            action = "updated"
        url = yield self.url_shortener(attribs["url"])
        msg = GitWebhookServer.issue_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=data["user"]["name"],
                      action=action, actioncolor=actioncolor,
                      issue_id=str(attribs["iid"]),
                      issue_title=attribs["title"],
                      issue_url=url)
        self.report_to_chat(repo_name,
                            GitWebhookServer._gitlab_get_namespace(data),
                            msg, confidential=attribs.get("confidential",
                                                          False))

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
            title = textwrap.shorten(title, 100)
        elif noteable_type == "MergeRequest":
            id = str(data["merge_request"]["iid"])
            title = data["merge_request"]["title"]
            noteable_type = "Merge Request"
            id_prefix = "!"
        elif noteable_type == "Issue":
            id = str(data["issue"]["iid"])
            title = data["issue"]["title"]
            id_prefix = "#"
        elif noteable_type == "Snippet":
            id = data["snippet"]["id"]
            title = data["snippet"]["title"]
        else:
            return
        url = yield self.url_shortener(attribs["url"])
        msg = GitWebhookServer.gitlab_note_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=data["user"]["name"],
                      noteable_type=noteable_type, id_prefix=id_prefix, id=id,
                      title=title, url=url)
        self.report_to_chat(repo_name,
                            GitWebhookServer._gitlab_get_namespace(data),
                            msg, confidential=confidential)

    @defer.inlineCallbacks
    def on_gitlab_merge_request(self, data):
        attribs = data["object_attributes"]
        repo_name = attribs["target"]["name"]
        action = attribs["_extended_action"]
        actioncolor = ColorCodes.darkorange
        if action == "open":
            action = "opened"
            actioncolor = ColorCodes.darkgreen
        elif action == "reopen":
            action = "reopened"
            actioncolor = ColorCodes.darkgreen
        elif action == "close":
            action = "closed"
            actioncolor = ColorCodes.red
        elif action == "merge":
            action = "merged"
            actioncolor = ColorCodes.darkgreen
        elif action == "update":
            action = "updated"
        elif action == "mark_as_draft":
            action = "marked as draft:"
            actioncolor = ColorCodes.lightgray
        elif action == "mark_as_ready":
            action = "marked as ready:"
            actioncolor = ColorCodes.darkgreen
        elif action == "approved":
            action = "approved"
            actioncolor = ColorCodes.darkgreen
        elif action == "approval":
            action = "added approval for"
            actioncolor = ColorCodes.darkgreen
        elif action == "unapproved":
            action = "unapproved"
            actioncolor = ColorCodes.darkorange
        elif action == "unapproval":
            action = "removed approval for"
            actioncolor = ColorCodes.darkorange
        url = yield self.url_shortener(attribs["url"])
        msg = GitWebhookServer.gitlab_mr_stub.clone()
        msg.fillSlots(repo_name=repo_name, user=data["user"]["name"],
                      action=action, actioncolor=actioncolor,
                      id=str(attribs["iid"]), title=attribs["title"],
                      source=attribs["source_branch"],
                      target=attribs["target_branch"],
                      url=url)
        self.report_to_chat(repo_name,
                            GitWebhookServer._gitlab_get_namespace(data),
                            msg)
