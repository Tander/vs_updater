import click
import os
import plistlib
import re
import requests
import tarfile
import toml
from shutil import copy2
from shutil import rmtree


class Updater:

    def __init__(self):
        with open('config.toml', 'r') as fp:
            config = toml.load(fp)
        try:
            self.fileserver_url = config['fileserver']['url']
            self.cdn_url = config['fileserver']['cdn_url']
            self.server_fullpath = os.path.abspath(config['local_server']['server_fullpath'])
            self.backup_fullpath = os.path.abspath(config['local_server']['backup_fullpath'])
        except Exception:
            raise Exception('Configuration file "config.toml" doesn\'t contain required parameters! '
                            'Fix it and try again.')

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
        try:
            with open(os.path.join(self.server_fullpath, 'Info.plist'), 'rb') as fp:
                info = plistlib.load(fp)
        except FileNotFoundError:
            raise Exception('Version file "Info.plist" not found. Probably VS server is not installed.')
        else:
            return info['CFBundleShortVersionString']

    def download_server(self, version):
        click.echo('Downloading server files for version {}...'.format(version))
        new_server_url = '{}vs_server_{}.tar.gz'.format(self.cdn_url, version)
        file = requests.get(new_server_url, stream=True)
        if file.status_code != 200:
            raise Exception('VS file server doesn\'t respond properly. Response code: {}'.format(file.status_code))
        with open(os.path.join(self.server_fullpath, 'vs_server.tar.gz'), 'wb') as f:
            for chunk in file:
                f.write(chunk)
        return

    def rotate_server_folder(self):
        click.echo('Preparing folders for update...')
        if not os.path.exists(self.server_fullpath):
            raise Exception('Server folder "{}" not found'.format(self.server_fullpath))

        # rename old folder
        if os.path.exists(self.backup_fullpath):
            rmtree(self.backup_fullpath)
        os.rename(self.server_fullpath, self.backup_fullpath)

        # create new one
        os.mkdir(self.server_fullpath)

    def unpack_server(self):
        click.echo('Unpacking server...')
        tar = tarfile.open(os.path.join(self.server_fullpath, 'vs_server.tar.gz'))
        tar.extractall(self.server_fullpath)

    def patch_server(self):
        click.echo('Copying server.sh from previous server instance...')
        sh_file = os.path.join(self.backup_fullpath, 'server.sh')
        if os.path.exists(sh_file):
            copy2(sh_file, self.server_fullpath)
        else:
            click.echo(
                'Warning! There is no server.sh in previous server folder, you should adjust settings in default '
                'server.sh manually!')

    def update_server(self, version):
        click.echo('Server update started...')
        self.rotate_server_folder()
        try:
            self.download_server(version)
            self.unpack_server()
            self.patch_server()
        except Exception as e:
            click.echo('Error during update detected, restoring old version of server...')
            if os.path.exists(self.server_fullpath):
                rmtree(self.server_fullpath)
            os.rename(self.backup_fullpath, self.server_fullpath)
            raise Exception('Update was failed. Error message: {}'.format(e))
        else:
            click.echo('Server was successfully updated to version {}!'.format(version))

    def check_for_update(self):
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

    @staticmethod
    def set_server_path(server_path):
        click.echo('Changing server path...')
        config = toml.load('config.toml')
        fullpath = os.path.abspath(server_path)
        backup_fullpath = os.path.join(os.path.split(fullpath)[0], 'server_backup')
        config['local_server']['server_fullpath'] = fullpath
        config['local_server']['backup_fullpath'] = backup_fullpath
        with open('config.toml', 'w') as fp:
            toml.dump(config, fp)
        click.echo('Done!')


# Click commands
@click.group()
def cli():
    """This is utility for updating your linux Vintage Story server.

    IMPORTANT: Before updating please set correct ABSOLUTE path to your server instance.

    \b
    You may do this by typing:
        vsupdater.py setpath /absolute/path/to/your/server/
    Or you may modify config.toml FOR BOTH PATHS.

    \b
    Then you may run update:
        vsupdater.py update

    Also you can use "upate" command with "--force" parameter if you need to update server regardless its version.
    """
    pass


@cli.command()
@click.argument('server_fullpath')
def setpath(server_fullpath):
    """Setting full path to your VS server in config for vsupdater"""
    u = Updater()
    u.set_server_path(server_fullpath)


@cli.command()
@click.option('--force', is_flag=True, help='Update the server regardless the need')
def update(force: bool):
    """Performing update for your server"""
    u = Updater()
    check_result = u.check_for_update()
    if check_result[0] or force:
        if force:
            click.echo('"--force" option received, updating the server anyway!')
        u.update_server(check_result[1])


@cli.command()
def check():
    """Checking if there is need to update your VS server"""
    u = Updater()
    u.check_for_update()


if __name__ == '__main__':
    cli()
