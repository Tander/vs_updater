import json
import shlex
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
import subprocess


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
            self.discord = config['discord']
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

    @staticmethod
    def _is_major_minor_equal(ver1, ver2):
        def get_major_minor(version):
            v = str(version).split('.')
            return '.'.join(v[:2])
        return get_major_minor(ver1) == get_major_minor(ver2)

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
            self.notify_about_error(str(e))
            raise e
        elif self.verbosity >= 10:
            self.notify_about_error(str(e))
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
        return str(info['CFBundleShortVersionString'])

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

        if path.exists(self.backup_fullpath):
            rmtree(self.backup_fullpath)
        rename(self.server_fullpath, self.backup_fullpath)

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
            raise Exception('Update of server files was failed. Error message: {}'.format(e))
        else:
            click.echo('Server files were successfully updated to version {}!'.format(version))

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

    def send_to_server(self, command):
        sh_path = path.join(self.server_fullpath, 'server.sh')
        parameters = shlex.split(command)
        result = subprocess.run((sh_path, *parameters), capture_output=True, encoding='utf-8')
        # stdout line separators are always '\n'
        return result.returncode, result.stdout

    @staticmethod
    def indent_text(text, indent='\t'):
        return indent + str(text).strip('\n').replace('\n', '\n'+indent)

    def server_start(self):
        click.echo('Starting VS server...')
        code, stdout = self.send_to_server('start')
        click.echo('Server output:\n{}'.format(self.indent_text(stdout)))
        if code != 0:
            raise Exception('Failed to start VS server!')

    def server_stop(self):
        click.echo('Stopping VS server...')
        code, stdout = self.send_to_server('stop')
        click.echo('Server output:\n{}'.format(self.indent_text(stdout)))
        if code != 0:
            raise Exception('Failed to stop VS server!')

    def server_command(self, text):
        text = str(text)
        click.echo('Executing command "{}" on VS server...'.format(text))
        code, stdout = self.send_to_server('command "{}"'.format(text))
        if code != 0:
            click.echo('Server output:\n{}'.format(self.indent_text(stdout)))
            raise Exception('Failed to execute command!')

    def send_to_discord(self, message: str, m_type='info'):
        if m_type in self.discord['webhook']:
            if self.discord['webhook'][m_type] != '':
                response = requests.post(self.discord['webhook'][m_type], data=message,
                                         headers={'Content-Type': 'application/json'},)
                if response.status_code < 400:
                    click.echo('Message was successfully sent')
                    return True
                else:
                    click.echo('Sending a message to discord failed: {}'.format(response.content))
                    return False
        click.echo('Note: Discord Webhook for type "{}" isn\'t set in config, message won\'t be sent'.format(m_type))
        return False

    def notify_about_update(self, version):
        click.echo('Notifying about update by Discord WebHook...')
        with open('files/d_template_update.jsonp', encoding='utf-8') as fp:
            message = fp.read()
        # discord api require color in decimal
        message = message.format(color=int(0x6f7a27), version=version, cdn_url=self.cdn_url)
        self.send_to_discord(message, 'success')

    def notify_about_error(self, text):
        click.echo('Notifying about error by Discord WebHook...')
        with open('files/d_template_error.jsonp', encoding='utf-8') as fp:
            message = fp.read()
        text = text.replace('\\', '\\\\').replace('\"', '\\\"')
        if len(text) > 1960:
            text = text[:1960] + '...'
        error = 'vsupdater encountered error:```{}```'.format(text)
        print(error)
        message = message.format(message=error)
        self.send_to_discord(message, 'error')

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
            return False, cur_version, last_version
        else:
            click.echo('Current VS server version {} is outdated. The latest is {}'.format(cur_version, last_version))
            # return last_version
            return True, cur_version, last_version

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

    def perform_update(self, force, no_discord):
        self.ensure_valid_server_path()
        self.ensure_valid_data_path()

        need_update, _, new_version = self.check_for_update()
        if need_update or force:
            if force:
                click.echo('"--force" option received, updating the server anyway!')
            self.update_server(new_version)
            if not no_discord:
                self.notify_about_update(new_version)

    def perform_auto_update(self, safe_update, no_discord):
        self.ensure_valid_server_path()
        self.ensure_valid_data_path()

        need_update, cur_version, new_version = self.check_for_update()
        if need_update:
            # safe_update means only patches (major.minor.**patch**) should be auto-installed
            if safe_update and not self._is_major_minor_equal(cur_version, new_version):
                raise Exception('Update was blocked by flag "--safe-update", because updating from {} to {} may be '
                                'unsafe. Try again without --safe-update if you want to update anyway.'
                                .format(cur_version, new_version))
            self.server_stop()
            try:
                self.backup_world_file()
                self.update_server(new_version)
            except Exception:
                raise
            finally:
                self.server_start()

            # if no exceptions so far
            if not no_discord:
                self.notify_about_update(new_version)


# Click commands
@click.group()
def cli():
    """This is utility for updating your linux Vintage Story server.

    IMPORTANT: vsupdater needs to be configured before using!

    \b
    You may do this by typing:
        vsupdater.py configure /path/to/your/server/
    Also you can modify config file directly if you want.

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
@click.option('--no-discord', is_flag=True, help='Do not notify about update via Discord WebHook')
def update(force: bool, no_discord: bool):
    """Performing update for your server (if needed).

    What exactly is happening by running this command:

    Checking if your VS server is outdated (you can override this checking by using "--force" flag);
    backing up current server folder (to be able to revert changes if update will fail for some reason);
    downloading newest stable server build;
    unpacking server files;
    replacing default server.sh with previous one (from previous server folder).
    notifies via Discord WebHook (if webhook is configured)

    If something went wrong during update procedure, vsupdater restores your old server folder

    If you don't want to send a notification about update to your discord, you may use "--no-discord" flag."""
    try:
        u.perform_update(force, no_discord)
    except Exception as e:
        u.display_exception(e)


@cli.command()
@click.option('--safe-update', is_flag=True, help='Cancel update if major or minor version is differs')
@click.option('--no-discord', is_flag=True, help='Do not notify about update via Discord WebHook')
def autoupdate(safe_update: bool, no_discord: bool):
    """Performing full update procedure for your server (if needed).

    This command meant to use in cron, but you can also use it manually.

    What exactly is happening by running this command:

    Stopping your VS server;
    backing up your current world file (in case in new version it will be corrupted);
    running update procedure (read "vsupdate.py update --help" for more info);
    starting VS server;
    notifies via Discord WebHook (if webhook is configured)

    If something went wrong during update procedure,
    vsupdater restores your old server folder and makes attempt to start it.

    If you want only patches to be installed automatically, use "--safe-update" flag with this command.

    If you don't want to send a notification about update to your discord, you may use "--no-discord" flag.

    As result, you will always get safely updated server, running on the latest version of VS!"""
    try:
        u.perform_auto_update(safe_update, no_discord)
    except Exception as e:
        u.display_exception(e)


if __name__ == '__main__':
    u = Updater()
    cli()
