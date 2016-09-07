PyTIBot - a IRC Bot using python and the twisted library
========================================================
PyTIBot is a simple IRC Bot written in python using the twisted library.
It supports several commands and can be easily extended. One instance of the
bot can only connect to one server at a time.


Dependencies
------------
python2 (as twisted does not support python3 yet)<br/>
twisted<br/>
configmanager (https://github.com/DefaultUser/configmanager)<br/>
apiclient (python module for google api)<br/>
xmlrpclib<br/>
Unix fortune

For Ubuntu 14.04 the needed packages are "python2.7", "python-twisted" and "python-googleapi".
Either adjust your PYTHONPATH to include configmanager or copy/link
configmanager.py to the base directory of this bot.

Starting the bot
----------------
Adjust the configuration file to your needs.
Start the bot with
```
python run.py
```
or if your system defaults to python 3
```
python2 run.py
```
By default pytibot.ini is used, but you can specify another configuration
file like this
```
python run.py otherconfig.ini
```


Configuration
-------------
Look at pytibot.ini.example for all keys.

[Connection]<br/>
*server*, *port*, *nickname* and *admins* are the mandatory fields<br/>
*admins*, *channels* and *ignore* can be comma separated lists<br/>
By default, admins are determined by the **nonstandard** irc reply 330. This
returns the auth name and therefor is safe. This reply is for example sent on
Quakenet. If the server does not support this reply, you can alternatively set
```
adminbyhost = True
```
which let's you specify admins by their IRC host name.<br/>
**!!ATTENTION!!**
If you don't have a cloaked host, your host will be your IP which will be
periodically changed. If you are using a bouncer, every user of that bouncer
will have the same host and therefor will be admin unless you are using a
cloaked host. Use this option with care.

[Auth]<br/>
*service* - Auth Service(eg: NickServ, Q@CServe.quakenet.org)<br/>
*command* - Auth command(eg: IDENTIFY, AUTH)<br/>
Set *username*, *password* according to your account.<br/>
*modes* - User modes for the bot (eg: +ix-d)

[Commands]<br/>
You can specify which commands should be enabled here.
The key is the command you have to type in IRC, the value is the name of the
python function that should be executed.

[Triggers]<br/>
*enabled* - comma separated list of all triggers<br/>
specific options for the triggers

[Simple Triggers]<br/>
User defineable lines that the bot should send when a certain word or pattern
is used in a message. See below.


Commands
--------
If an IRC message starts with the nick of the bot, the message will be
interpreted as a command. In private chat, every message will be interpreted
as a command.

standard commands (can't be changed):
```
quit - quit the bot
ignore - add an user to the ignore list (user will be ignored by the bot)
join - join one or more channel
part - leave one or more channel
nick - change the nick
help - print help
reload - reload the config file
```

additional commands can be configured in the ini file (see pytibot.ini.example)


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
[Triggers]
enabled = youtube
youtube_api_key = REPLACE_ME
```

Simple Trigger that can be specified by the user in the ini file:<br/>
These can be specified under the [Simple Trigger] section<br/>
The key will be used as trigger and the value is send to irc<br/>
The key can be a regex

"$USER" and "$CHANNEL" will be expanded to the user and channel, which triggered
the line. Also you can specify colors with "$COLOR(1,2)", where the first number
stands for the font color and the second one is the background [optional]. Color
range is from 0 to 15.
**Attention**: don't put a whitespace between these numbers.


Telnet access
-------------
Additionally to IRC commands this bot can also be controlled via telnet.
To turn this feature on, you need to set
```
open_telnet = True
```
under the **Connection** section.

Once you are connected via telnet, you have access to a python interpreter. Run
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


Logging
-------
This bot can also be used to log channel activity.
```
[Logging]
channels = #mysuperchannel, #myweirdchannel
directory = /tmp/log/
rotation_policy = w0
```
Every channel is logged to a different file<br/>
**rotation_policy** follows the same rules as the **TimedRotatingFileHandler** from python's **logging** module
(https://docs.python.org/2/library/logging.handlers.html#logging.handlers.TimedRotatingFileHandler)


COPYRIGHT
---------
GPLv3, see LICENSE<br/>
Twisted is licensed under MIT license (see twistedmatrix.com)

Sebastian Schmidt<br/>
schro.sb@gmail.com
