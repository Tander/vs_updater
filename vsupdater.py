import json
from datetime import datetime
import click
from os import path
from os import makedirs
from os import rename
import plistlib
import re
import requests
import tarfile
import toml
from shutil import copy2
from shutil import rmtree


class Updater:

    def __init__(self, config_name='config.toml'):
        self.config_name = config_name

        # Loading config
        with open(self.config_name, 'r') as fp:
            config = toml.load(fp)
        try:
            self.fileserver_url = config['fileserver']['url']
            self.cdn_url = config['fileserver']['cdn_url']
            self.server_fullpath = path.abspath(config['local_server']['server_fullpath'])
            self.backup_fullpath = path.abspath(config['local_server']['backup_fullpath'])
            self.data_fullpath = path.abspath(config['local_server']['data_fullpath'])
            self.worldbackup_fullpath = path.abspath(config['local_server']['worldbackup_fullpath'])
            # (NIY) 0 - nothing, 10 - success/fail, 20 - info, 50 - debug
            self.verbosity = config['settings']['verbosity_level']
        except Exception:
            raise Exception('Configuration file "{}" doesn\'t contain required parameters! '
                            'Fix it and try again.'.format(self.config_name))

        # Remember if paths are valid
        self.server_valid = True if self._is_valid_server_path(self.server_fullpath) else False
        self.data_valid = True if self._is_valid_data_path(self.data_fullpath) else False

    @staticmethod
    def _is_valid_server_path(server_path):
        if path.isfile(path.join(server_path, 'server.sh')) and path.isfile(path.join(server_path, 'Info.plist')):
            return True
        return False

    @staticmethod
    def _is_valid_data_path(server_path):
        if path.isfile(path.join(server_path, 'serverconfig.json')):
            return True
        return False

    def ensure_valid_server_path(self):
        if not self.server_valid:
            msg = 'Stored server path "{}" is incorrect! Please run "vsupdater.py configure /path/to/your/server" ' \
                  'to set up correct path.'
            raise Exception(msg.format(self.server_fullpath))

    def ensure_valid_data_path(self):
        if not self.data_valid:
            msg = 'Stored data path "{}" is incorrect! Please run "vsupdater.py configure /path/to/your/server" ' \
                  'to set up correct data path according to DATAPATH variable in server.sh file.'
            raise Exception(msg.format(self.data_fullpath))

    def display_exception(self, e):
        if self.verbosity >= 50:
            raise e
        elif self.verbosity >= 10:
            click.echo(e)

    def get_last_version(self):
        re_filename = re.compile(r'href="vs_server_([\d.]+)\.tar\.gz"')  # https://regex101.com/r/WSNbFw/4

        vspage = requests.get(self.fileserver_url, {'C': 'M', 'O': 'D'})
        if vspage.status_code != 200:
            raise Exception('VS file server doesn\'t respond properly. Response code: {}'.format(vspage.status_code))

        for line in vspage.iter_lines():
            match = re_filename.search(str(line))
            if match is not None:
                return match.group(1)
        # if there is no match in entire page
        raise Exception('Can\'t find latest version number on VS file server!')

    def get_current_version(self):
        with open(path.join(self.server_fullpath, 'Info.plist'), 'rb') as fp:
            info = plistlib.load(fp)
        return info['CFBundleShortVersionString']

    def download_server(self, version):
        click.echo('Downloading server files for version {}...'.format(version))
        new_server_url = '{}vs_server_{}.tar.gz'.format(self.cdn_url, version)
        file = requests.get(new_server_url, stream=True)
        if file.status_code != 200:
            raise Exception('VS file server doesn\'t respond properly. Response code: {}'.format(file.status_code))
        with open(path.join(self.server_fullpath, 'vs_server.tar.gz'), 'wb') as f:
            for chunk in file:
                f.write(chunk)
        return

    def swap_server_folders(self):
        click.echo('Preparing folders for update...')
        if not path.exists(self.server_fullpath):
            raise Exception('Server folder "{}" not found'.format(self.server_fullpath))

        # rename old folder
        if path.exists(self.backup_fullpath):
            rmtree(self.backup_fullpath)
        rename(self.server_fullpath, self.backup_fullpath)

        # create new one
        makedirs(self.server_fullpath)

    def unpack_server(self):
        click.echo('Unpacking server...')
        tar = tarfile.open(path.join(self.server_fullpath, 'vs_server.tar.gz'))
        tar.extractall(self.server_fullpath)

    def patch_server(self):
        click.echo('Copying server.sh from previous server instance...')
        sh_file = path.join(self.backup_fullpath, 'server.sh')
        if path.exists(sh_file):
            copy2(sh_file, self.server_fullpath)
        else:
            click.echo(
                'Warning! There is no server.sh in previous server folder, you should adjust settings in default '
                'server.sh manually if you need!')

    def update_server(self, version):
        self.ensure_valid_server_path()
        self.ensure_valid_data_path()

        click.echo('Server update started...')
        self.swap_server_folders()
        try:
            self.download_server(version)
            self.unpack_server()
            self.patch_server()
        except Exception as e:
            click.echo('Error during update detected, restoring old version of server...')
            if path.exists(self.server_fullpath):
                rmtree(self.server_fullpath)
            rename(self.backup_fullpath, self.server_fullpath)
            raise Exception('Update was failed. Error message: {}'.format(e))
        else:
            click.echo('Server was successfully updated to version {}!'.format(version))

    @staticmethod
    def get_datapath(server_fullpath):
        keyword = 'DATAPATH='
        with open(path.join(server_fullpath, 'server.sh'), 'rt', encoding='utf-8') as fp:
            for line in fp:
                index = line.find(keyword)
                if index != -1:
                    start = index + len(keyword)
                    datapath = line[start:].strip().strip('\"\'')
                    return datapath
        # if nothing found
        raise Exception('Can\'t find "{}" in your server.sh. Please fix it and try again.'.format(keyword))

    @staticmethod
    def get_worldfile_path(data_fullpath):
        with open(path.join(data_fullpath, 'serverconfig.json'), 'rt', encoding='utf-8') as fp:
            config = json.load(fp)
        return config['WorldConfig']['SaveFileLocation']

    # =======================
    # ENDPOINT METHODS
    # =======================
    def configure(self, server_path):
        click.echo('Gathering values for config file...')
        config = toml.load(self.config_name)

        server_fullpath = path.abspath(server_path)
        if not self._is_valid_server_path(server_fullpath):
            raise Exception('"{}" is not valid VS server folder! Use --help to learn more.'.format(server_fullpath))

        config['local_server']['server_fullpath'] = server_fullpath
        config['local_server']['backup_fullpath'] = path.join(path.split(server_fullpath)[0], 'server_backup')

        data_fullpath = self.get_datapath(server_fullpath)
        if not self._is_valid_data_path(data_fullpath):
            click.echo('Warning: DATAPATH in your server.sh doesn\'t point on valid /data/ folder. '
                       'But the value will be set anyway.')

        config['local_server']['data_fullpath'] = data_fullpath
        config['local_server']['worldbackup_fullpath'] = path.join(data_fullpath, 'WorldBackup')

        with open(self.config_name, 'w') as fp:
            toml.dump(config, fp)
        report = toml.dumps({'local_server': config['local_server']})
        click.echo('Done! Now current config values for your server instance are:\n{}'.format(report))

    def check_for_update(self):
        self.ensure_valid_server_path()

        click.echo('Getting information about current and latest version...')
        last_version = self.get_last_version()
        cur_version = self.get_current_version()

        if cur_version == last_version:  # assuming if your version isn't the latest on official server - it's outdated
            click.echo('Current VS server version {} is latest. No need to update.'.format(cur_version))
            # return False
            return False, last_version
        else:
            click.echo('Current VS server version {} is outdated. The latest is {}'.format(cur_version, last_version))
            # return last_version
            return True, last_version

    def backup_world_file(self):
        self.ensure_valid_server_path()
        self.ensure_valid_data_path()

        click.echo('Making backup for current world file...')
        world_file_path = self.get_worldfile_path(self.data_fullpath)

        if not path.isfile(world_file_path):
            raise Exception('World file "{}" not found! Fix your serverconfig.json or launch your server instance '
                            'to let it create world file.'.format(world_file_path))

        version = self.get_current_version()
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_fullpath = path.join(self.worldbackup_fullpath, version, timestamp)

        makedirs(backup_fullpath, exist_ok=True)
        dst = copy2(world_file_path, backup_fullpath)
        click.echo('Backup was successfully made and stored in "{}". You may remove it when you don\'t need it '
                   'anymore.'.format(dst))

    def perform_update(self, force):
        self.ensure_valid_server_path()
        self.ensure_valid_data_path()

        check_result = self.check_for_update()
        if check_result[0] or force:
            if force:
                click.echo('"--force" option received, updating the server anyway!')
            # shutting down the server will be here
            self.backup_world_file()
            self.update_server(check_result[1])
            # starting updated server will be here


# Click commands
@click.group()
def cli():
    """This is utility for updating your linux Vintage Story server.

    IMPORTANT: vsupdater needs to be configured before using!

    \b
    You may do this by typing:
        vsupdater.py configure /path/to/your/server/
    Also you can modify config file to get more control over paths vsupdater will use.

    \b
    Then you may run update:
        vsupdater.py update

    Also you can use "upate" command with "--force" parameter if you need to update server regardless its version.

    Use "vsupdater.py [COMMAND] --help" to learn more about each command.
    """
    pass


@cli.command()
@click.argument('server_fullpath')
def configure(server_fullpath):
    """Configures this tool to use server instance on given path.

    You should run your server instance at least once to let it create /data/ folder and world savefile,
    so vsupdater could determine what world file it should backup before performing update.

    SERVER_FULLPATH - absolute path to your server folder.

    \b
    Folder should contain:
    server.sh - for operating server and reading /data/ directory location;
    Info.plist - for reading version of server instance;
    """
    try:
        u.configure(server_fullpath)
    except Exception as e:
        u.display_exception(e)


@cli.command()
def check():
    """Checking if your VS server requires update."""
    try:
        u.check_for_update()
    except Exception as e:
        u.display_exception(e)


@cli.command()
def worldbackup():
    """Performing backup of your current world.

    It's highly recommended to do it when server is not running."""
    try:
        u.backup_world_file()
    except Exception as e:
        u.display_exception(e)


@cli.command()
@click.option('--force', is_flag=True, help='Update the server regardless the need')
def update(force: bool):
    """Performing update for your server.

    Actually, it's doing more than just that:

    vsupdater is checking if server need to be updated (you can override this checking by using "--force" flag),
    backing up your current world file in case in new version will corrupt it, backing up current server folder
    (to be able to revert changes if update will fail for some reason), downloading newest stable server build,
    unpacking it and replacing default server.sh with yours (from previous server folder).

    As result, you will get safely updated server, completely ready to run!"""
    try:
        u.perform_update(force)
    except Exception as e:
        u.display_exception(e)


if __name__ == '__main__':
    u = Updater()
    cli()
    # print(u.get_datapath('D:\\sept\\vintagestory\\server'))
    # print(u.get_worldfile_path('D:\\sept\\vintagestory\\data'))
