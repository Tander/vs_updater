# VintageStory server updater

```Usage: vsupdater.py [OPTIONS] COMMAND [ARGS]...

  This is utility for updating your linux Vintage Story server.

  IMPORTANT: vsupdater needs to be configured before using!

  You may do this by typing:
      vsupdater.py configure /path/to/your/server/
  Also you can modify config file to get more control over paths vsupdater will use.

  Then you may run update:
      vsupdater.py update

  Also you can use "upate" command with "--force" parameter if you need to
  update server regardless its version.

  Use "vsupdater.py [COMMAND] --help" to learn more about each command.

Options:
  --help  Show this message and exit.

Commands:
  check        Checking if your VS server requires update.
  configure    Configures this tool to use server instance on given path.
  update       Performing update for your server.
  worldbackup  Performing backup of your current world.
```
