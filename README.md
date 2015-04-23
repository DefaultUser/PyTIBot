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
gdata-python-client (python module for google api)

For Ubuntu 14.04 the needed packages are "python2.7", "python-twisted" and "python-gdata".
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

[Commands]<br/>
You can specify which commands should be enabled here.
The key is the command you have to type in IRC, the value is the name of the
python function that should be executed.

[Triggers]<br/>
*enabled* - comma separated list of all triggers

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

Trigger commands that run a python command:<br/>
example: youtube url -> bot returns the title of the video

Simple Trigger that can be specified by the user in the ini file:<br/>
These can be specified under the [Simple Trigger] section<br/>
The key will be used as trigger and the value is send to irc<br/>
The key can be a regex


COPYRIGHT
---------
GPLv3, see LICENSE<br/>
Twisted is licensed under MIT license (see twistedmatrix.com)

Sebastian Schmidt<br/>
schro.sb@gmail.com
