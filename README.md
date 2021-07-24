PyTIBot - a IRC Bot using python and the twisted library
========================================================
PyTIBot is a simple IRC Bot written in python using the twisted library.
It supports several commands and can be easily extended. One instance of the
bot can only connect to one server at a time.


Dependencies
------------
This bot requires Python3. Python2 is no longer supported.
The following packages are needed (also see requirements.txt):
```
twisted
treq
PyYAML>=5.1.2
yamlcfg
appdirs
whoosh
bidict
colormath
dateparser
apiclient (python module for google api) (optional)
Unix fortune (optional)
```
The optional packages will not be installed by
```
pip install -r requirements.txt
```


Starting the bot
----------------
Adjust the configuration file to your needs.
Start the bot with
```
twist PyTIBot
```
By default pytibot.yaml is used, but you can specify another configuration
file like this
```
twist PyTIBot -c otherconfig.yaml
```


Configuration
-------------
Configuration files need to be located in the OS specific config directory.
On Linux and Unix:
```
~/.config/PyTIBot/
```
On Mac OS X:
```
~/Library/Application Support/PyTIBot/
```
On Windows:
```
C:\Users\<username>\AppData\Local\PyTIBot
```

Look at pytibot.yaml.example for all keys.

[Connection]<br/>
*server*, *nickname* and *admins* are the mandatory fields.<br/>
Additionally either *port* or *sslport* have to be specified.<br/>
*admins*, *channels* and *ignore* can be comma separated lists<br/>
By default, admins are determined by the **nonstandard** irc reply 330. This
returns the auth name and therefor is safe. This reply is for example sent on
Quakenet. If the server does not support this reply, you can alternatively set
```
adminbyhost: True
```
which let's you specify admins by their IRC host name.<br/>
**!!ATTENTION!!**
If you don't have a cloaked host, your host will be your IP which will be
periodically changed. If you are using a bouncer, every user of that bouncer
will have the same host and therefor will be admin unless you are using a
cloaked host. Use this option with care.

Auth:<br/>
*service* - Auth Service(eg: NickServ, Q@CServe.quakenet.org)<br/>
*command* - Auth command(eg: IDENTIFY, AUTH)<br/>
Set *username*, *password* according to your account.<br/>
*modes* - User modes for the bot (eg: +ix-d)

Commands:<br/>
You can specify which commands should be enabled here.
The key is the command you have to type in IRC, the value is the name of the
python function that should be executed.

Aliases:<br/>
Aliases allow defining pseudo-commands so that command-argument combinations
can be called using these aliases. *$USER* will be expanded to the nickname
of the caller.

Triggers:<br/>
*enabled* - list of all triggers<br/>
specific options for the triggers

Simple Triggers:<br/>
User defineable lines that the bot should send when a certain word or pattern
is used in a message. See below.

User supplied content (like additional files for the fortune command) can be read
from the user's data directory:
On Linux and Unix:
```
~/.local/share/PyTIBot/
```
On Mac OS X:
```
~/Library/Application Support/PyTIBot/
```
On Windows:
```
C:\Users\<username>\AppData\Local\PyTIBot
```


Commands
--------
If an IRC message starts with the nick of the bot, the message will be
interpreted as a command. In private chat, every message will be interpreted
as a command.

Standard commands (can't be changed):
```
quit - quit the bot
ignore - add an user to the ignore list (user will be ignored by the bot)
join - join one or more channel
part - leave one or more channel
nick - change the nick
help - print help
reload - reload the config file
```

Additional commands can be configured in the ini file (see pytibot.ini.example)


Trigger commands
----------------
Additionally to commands, the bot can also be triggered by words and patterns
in any message. There are two kinds of trigger commands:

Trigger commands that run a python function:<br/>
```
from $NICKNAME.commands import cmd as name
```
where $NICKNAME is the nick of the bot enables the command `cmd` using the name `name`.

```
from $NICKNAME.triggers import trigger
```
where $NICKNAME is the nick of the bot enables the trigger `trigger`.

youtube url -> bot returns the title of the video<br/>
*ATTENTION* This trigger needs a google API key from https://code.google.com/apis/console
```
Triggers:
  enabled: [youtube]
  youtube_api_key: REPLACE_ME
```

Simple Trigger that can be specified by the user in the ini file:<br/>
These can be specified under the [Simple Trigger] section<br/>
*trigger* will be used as trigger and the *answer* is send to irc.<br/>
If *answer* is a list, a random element of that list is chosen.

"$USER" and "$CHANNEL" will be expanded to the user and channel, which triggered
the line. Text formatting described in section [Text Formatting](#text-formatting).


Manhole access
-------------
Additionally to IRC commands this bot can also be controlled via telnet.
To turn this feature on, you need to set the port in the configuration file:
```
Manhole:
  telnetport = 9999
```
You also need to specify login credentials in the file *manhole_cred* in the form of *user:password*.

Once you are connected via telnet, you have **full** access to a python interpreter -
**ONLY GIVE LOGIN CREDENTIALS TO PEOPLE YOU ABSOLUTELY TRUST**. Run
```
bot = get_bot()
```
to retrieve the instance of the bot.

You can send messages with
```
bot.msg(reciever, message)
```
where *reciever* can be a nick or channel.<br/>
You can quit the bot with
```
bot.quit()
```
For the full list of class methods, check the source and the twisted api
(http://twistedmatrix.com/documents/current/api/twisted.words.protocols.irc.IRCClient.html)


Channelmodules
--------------
This section is used for channel specific modules.
```
Channelmodules:
  "#mysuperchannel":
  -
    ChannelLogger
  -
    Autokick:
      user_blacklist:
      - bad_user
      - evil_user
      msg_blacklist:
      - "evil word"
      user_whitelist:
      - trusted_user
      msg_whitelist:
      - $BOTNAME:\s*fortune
      # simple spam protection
      buffer_length: 6 # default 5
      repeat_count: 3 # default 3
      max_highlights: 3 # default 5
  -
    Greeter:
      standard_nicks: [test]
      patterns: 
      - "realname == *webchat*" # similar to webhook event filter (nick, user, host, realname)
      - "*!webchat@* # shell like pattern matching"
      - "*!*@gateway/web/*"
      message: Welcome, $USER!
  -
    MarkovChat: # needs a list
    - corpus: mycorpus # file in <config dir>/markov/<channel>/
      chat_rate: 0.01 # chance of a chat message, default 0.1
      add_rate: 0.6 # chance of extending the model, default 0.4
      keywords:
      - special
      - markov
    - corpus: second_corpus
      keywords:
      - python
      - pytibot
```
*ChannelLogger* also needs some configuration that is shared by all ChannelLoggers (see section *Logging*).<br/>
*user_blacklist* and *msg_blacklist* in *Autokick* accept regular expressions. If *repeat_count* of a user's last *buffer_length* messages are the same or a user highlights more than *max_highlights* users with the same message, this user will also be kicked.<br/>
The *Greeter* channelmodule will greet new users when they join the given channel if their whois information (`nick!ident@host`) matches one of the given *patterns*. For every nick this will only happen once unless this nick is part of the *standard_nicks* (this is persistent even after restart/lost connection). For the patterns, you can use shell like pattern matching. The above *patterns* are examples to greet webchat users on Quakenet and Freenode.


Text Formatting
---------------
Several control codes are available for formatting messages sent to IRC:
- `$COLOR`
- `$RAINBOW`
- `$BOLD`
- `$ITALIC`
- `$UNDERLINE`
- `$NOFORMAT`

The `$COLOR` control code can take parameters: `$COLOR(fg,bg)`
The first parameter stands for the font color and the second one for the
background [optional]. These colors can either be the color names (seen util/formatting.py)
or directly the color code ranging from 0 to 15.<br/>
**Attention**: Don't put a whitespace between the colors.<br/>
`$RAINBOW` takes the text that should be colorized as paramter:
`$RAINBOW(Example text in rainbow) - no colors here`


Logging
-------
This bot can also be used to log channel activity.
```
Logging:
  directory: /tmp/log/
  log_minor: true
  yaml: true
```
For every channel that should be logged, you need to add the *ChannelLogger* to the Channelmodules section (see above).<br/>
Every channel is logged to a different file<br/>
If **log_minor** is **False**, join and part messages are not logged to file<br/>
If **yaml** is **True**, channel logs are saved as yaml documents<br/>
Log rotation will be applied at midnight.

If the log directory is not set, the standard user log directory is used:
On Linux and Unix:
```
~/.cache/PyTIBot/log/channellogs/
```
On Mac OS X:
```
~/Library/Logs/PyTIBot/channellogs/
```
On Windows:
```
C:\Users\<username>\AppData\Local\PyTIBot\Logs\channellogs\
```

Vote Module
-----------
The `Vote` channelmodule allows setting up an environment where IRC users can create
and vote for polls. These users need to be registered/authed on the IRC server in order
to be identifiable.

This channelmodule has the following options:
```
prefix: @ # default !
poll_url: https://my.domain/path/to/vote/page
http_secret: mysecret
```
For `poll_url` and `http_secret` see section `HTTP Server`.

Before voting, users have to be added to a database. This can be done by admins or users
that have `ADMIN` privileges in the user database.
```
<prefix>user add [--privilege=USER|ADMIN] <nickname>
```

Polls can be created, modified etc with the `poll` command.<br/>
Votes can be cast with the `vote` command.<br/>
Polls can be organized in categories (`category` command).<br/>
Help is available with the `vhelp` command.

HTTP Server
-----------
You can also use the builtin http server to create a webpage that shows information
generated by the Bot.
```
HTTPServer:
  port: 8080
  sslport: 8081
  certificate: /path/to/cert.pem
  privkey: /path/to/privkey.pem
  root:
    type: OverviewPage
    title: Page title
    children:
      channel1: # available at /channel1
        type: LogPage # automatically adds search page at /channel1/search
        title: IRC logs for my channel
        channel: '#mysuperchannel'
      channel2:
        type: LogPage
        channel: '#myotherchannel'
      static:
        type: Static
        path: path/to/static/content # relative to "resources" folder
```
The style of the website can be customized by adding apropriate files to the "resources/assets" folder
of your user data directory.

Every Page can have multiple subpages specified by its `children` setting.

`OverviewPage` creates a page with links to its children.<br/>
`LogPage` creates a page that displays channel logs from the specified channel. This will only
work if you use yaml logs. A search page is implicitly added as child.

GitHub/Gitlab webhook integration
---------------------------------
This bot can also listen for GitHub/Gitlab webhooks.<br/>
The webhook server can send messages to multiple IRC channels as defined in the **channels** section.
The keys are the names of your repo (**CASE SENSITIVE**) or **default**. The values need to be a list of channels.<br/>
**WARNING: Gitlab integration is currently untested and might contain bugs**<br/>
For GitHub the supported events currently are: push, issues, issue_comment, create, delete, fork, commit_comment, release, pull_request, pull_request_review and pull_request_review_comment<br/>
For Gitlab the supported events are: push, issue, note, merge_request<br/>
```
GitWebhook:
  channels:
    my_project:
    - "#mysuperchannel"
    - "#myotherchannel"
    default:
    - "#mydefaultchannel"
  sslport: 4041
  certificate: /path/to/cert.pem
  privkey: /path/to/privkey.pem
  github_secret: SECRETKEY
  gitlab_secret: SECRETKEY
  hook_report_users: [myadmin]
  # option to prevent multiple PR review and review comment messages on github in short intervals by grouping events
  # events will be delayed by 10 seconds
  PreventGitHubReviewFlood: true
  FilterRules:
  # filter out webhook shots using the following rules
  # for a single rule, 'AND' can be used to join multiple conditions
  # using 'OR' to join multiple conditions is not supported
  # use '|' to compare an element to different values
  # example for github (API: https://developer.github.com/v3/activity/events/types/)
  - eventtype == issues AND action == pinned | unpinned
  # use '.' to access subelements, accessing lists is not supported
  - eventtype == push AND pusher.name == filteredUser
  # example for gitlab (API: https://docs.gitlab.com/ce/user/project/integrations/webhooks.html)
  - eventtype == note AND object_attributes.noteable_type == Snippet
  # url shortener for gitlab
  url_shortener:
    # $URL will be replaced by the url to shorten
    service_url: "https://example.com/shorten"
    method: GET # Defaults to POST
    headers:
      TOKEN: SECRET_TOKEN
    request_params: # GET parameters
      url: $URL
    #post_data: # POST data
    #  TOKEN: SECRET_TOKEN
    #  long_url: $URL
    payload_accessor:
      #DirectAccessor # received payload is plaintext shortened url, DEFAULT
      JsonAccessor: # extract shortened url from a received Json response
        path: # keys to the shortened url value
        - response
        - shortened_url
      #HeaderAccessor: # shortened url is contained in the HTTP headers
      #  key: Location
  Hooks:
    Push:
      default:
      - action: act1
        branches: <all>
        ignore_users: []
      my_project:
      - action: do_noop # exclude my_project from the default Push hook
  Actions:
    act1:
      type: process
      command: ./my_process
      path: /some/path/
      args: ["1", test] # should be strings
      rungroup: run1
    do_noop:
      type: noop
      # rungroup is automatically set to default if not specified
  RungroupSettings:
    run1:
      clear_previous: True
      stop_running: False
```
Alternatively to *sslport* you can specify *port* to create a plain HTTP server without SSL/TLS encryption. However this is only recommended with a local SSL/TLS encrypted Proxy Server.

Urls in GitHub events will be shortened using `https://git.io`. This service is free, but can only be used with urls for GitHub domains. For urls in Gitlab events, you can supply a service
of your choice. As these services tend to require access tokens and have no common API, the interface is very generic.

Certain Webhook events can be used to trigger actions that the bot will execute (currently only Push events are supported). Success or failure will be reported to *hook_report_users*.<br/>
Currently these types of actions are supported:
  * noop: do nothing, useful for excluding a project from the default hook
  * process: run a subprocess, only one process of every rungroup can run at the same time


COPYRIGHT
---------
GPLv3, see LICENSE<br/>
Twisted is licensed under MIT license (see twistedmatrix.com)<br/>

Sebastian Schmidt<br/>
schro.sb@gmail.com
