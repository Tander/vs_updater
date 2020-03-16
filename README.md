# VintageStory server updater

```Usage: vsupdater.py [OPTIONS] COMMAND [ARGS]...

  This is utility for updating your linux Vintage Story server.

  IMPORTANT: Before updating please set correct ABSOLUTE path to your server
  instance.

  You may do this by typing:
      vsupdater.py setpath /absolute/path/to/your/server/
  Or you may modify config.toml FOR BOTH PATHS.

  Then you may run update:
      vsupdater.py update

  Also you can use "upate" command with "--force" parameter if you need to
  update server regardless its version.

Options:
  --help  Show this message and exit.

Commands:
  check    Checking if there is need to update your VS server
  setpath  Setting full path to your VS server in config for vsupdater
  update   Performing update for your server
```
