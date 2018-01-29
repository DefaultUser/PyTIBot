PyTIBot - a IRC Bot using python and the twisted library
========================================================
PyTIBot is a simple IRC Bot written in python using the twisted library.
It supports several commands and can be easily extended. One instance of the
bot can only connect to one server at a time.


Dependencies
------------
Development and testing was mainly done with python2, python3 should work but is not extensively tested.
```
twisted
treq
python-yaml
yamlcfg
xmlrpclib
appdirs
whoosh
bidict
unidecode
colormath
apiclient (python module for google api) (optional)
Unix fortune (optional)
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
the line. Also you can specify colors with "$COLOR(1,2)", where the first number
stands for the font color and the second one is the background [optional]. Color
range is from 0 to 15.
**Attention**: don't put a whitespace between these numbers.


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
      # simple spam protection
      buffer_length: 6 # default 5
      repeat_count: 3 # default 3
      max_highlights: 3 # default 5
  -
    Greeter:
      standard_nicks: [test]
      patterns: ["*!webchat@*", "*!*@gateway/web/*"] # shell like pattern matching
      message: Welcome, $USER!
```
*ChannelLogger* also needs some configuration that is shared by all ChannelLoggers (see section *Logging*).<br/>
*user_blacklist* and *msg_blacklist* in *Autokick* accept regular expressions. If *repeat_count* of a user's last *buffer_length* messages are the same or a user highlights more than *max_highlights* users with the same message, this user will also be kicked.<br/>
The *Greeter* channelmodule will greet new users when they join the given channel if their whois information (`nick!ident@host`) matches one of the given *patterns*. For every nick this will only happen once unless this nick is part of the *standard_nicks* (this is persistent even after restart/lost connection). For the patterns, you can use shell like pattern matching. The above *patterns* are examples to greet webchat users on Quakenet and Freenode.


Logging
-------
This bot can also be used to log channel activity.
```
Logging:
  directory = /tmp/log/
  log_minor = True
  yaml = True
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

You can also use the builtin http server to create a webpage that shows the channel logs
(only works if you use yaml logs)
```
HTTPLogServer:
  channels: ["#mysuperchannel"]
  port: 8080
  sslport: 8081
  certificate: /path/to/cert.pem
  privkey: /path/to/privkey.pem
  title: Awesome Log Server
```
The style of the website can be customized by adding apropriate files to the "resources" folder
of your user data directory. You can also add a "favicon.ico". All files in that folder that do
not end with ".html" or ".inc" will be publicly available.


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
Alternatively to *sslport* you can specify *port* to create a plain HTTP server without SSL/TLS encryption. However this is only recommended with a local SSL/TLS encrypted Proxy Server.<br/>
Certain Webhook events can be used to trigger actions that the bot will execute (currently only Push events are supported). Success or failure will be reported to *hook_report_users*.<br/>
Currently these types of actions are supported:
  * noop: do nothing, useful for excluding a project from the default hook
  * process: run a subprocess, only one process of every rungroup can run at the same time


COPYRIGHT
---------
GPLv3, see LICENSE<br/>
Twisted is licensed under MIT license (see twistedmatrix.com)<br/>
Modernizr is licensed under MIT license

Sebastian Schmidt<br/>
schro.sb@gmail.com
