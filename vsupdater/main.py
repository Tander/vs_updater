import requests
import re
import plistlib
import os
from shutil import rmtree, copy2
import tarfile

# CONFIG

# VS file server URL. Should be Apache page with enabled DirectoryIndex
vs_server_url = 'https://account.vintagestory.at/files/stable/'

# VS server folder
vs_folder = os.path.abspath(r'D:/sept/vintagestory/server/')
# Folder for storing previous version of server
previous_vs_folder = os.path.abspath(r'D:/sept/vintagestory/server_old/')


# SCRIPT

def get_last_version():
    re_filename = re.compile(r'href="(vs_server_([\d\.]+)\.tar\.gz)"')  # https://regex101.com/r/WSNbFw/2

    vspage = requests.get(vs_server_url, {'C': 'M', 'O': 'D'})
    if vspage.status_code != 200:
        raise Exception('VS file server doesn\'t respond properly. Response code: {}'.format(vspage.status_code))

    for line in vspage.iter_lines():
        match = re_filename.search(str(line))
        if match is not None:
            # return {'url': vs_server_url + match.group(1), 'version': match.group(2)}
            return match.group(2)


def get_current_version():
    try:
        with open(os.path.join(vs_folder, 'Info.plist'), 'rb') as fp:
            info = plistlib.load(fp)
    except FileNotFoundError as e:
        raise Exception('Version file "Info.plist" not found. Probably VS server is not installed.')
    else:
        return info['CFBundleShortVersionString']


def download_server(new_server_url):
    print('Downloading server files...')
    file = requests.get(new_server_url, stream=True)
    if file.status_code != 200:
        raise Exception('VS file server doesn\'t respond properly. Response code: {}'.format(file.status_code))
    with open(os.path.join(vs_folder, 'vs_server.tar.gz'), 'wb' ) as f:
        for chunk in file:
            f.write(chunk)
    return


def rotate_server_folder():
    print('Preparing folders for update...')
    if not os.path.exists(vs_folder):
        raise Exception('Server folder "{}" not found'.format(vs_folder))

    # rename old folder
    if os.path.exists(previous_vs_folder):
        rmtree(previous_vs_folder)
    os.rename(vs_folder, previous_vs_folder)

    # create new one
    os.mkdir(vs_folder)


def prepare_server():
    print('Unpacking server and moving server.sh...')
    tar = tarfile.open(os.path.join(vs_folder, 'vs_server.tar.gz'))
    tar.extractall(vs_folder)

    # copy server.sh from previous server folder
    sh_file = os.path.join(previous_vs_folder, 'server.sh')
    if os.path.exists(sh_file):
        copy2(sh_file, vs_folder)
    else:
        print('There is no server.sh in old server folder, you should adjust settings in default server.sh manually!')


def update_server(new_server_url):
    print('Server update started...')
    rotate_server_folder()
    try:
        download_server(new_server_url)
        prepare_server()
    except Exception as e:
        print('Error during update detected, restoring old version of server...')
        if os.path.exists(vs_folder):
            rmtree(vs_folder)
        os.rename(previous_vs_folder, vs_folder)
        raise Exception('Update was failed. Error message: {}'.format(e))


def check_for_update():
    last_version = get_last_version()
    cur_version = get_current_version()

    if cur_version == last_version:  # assuming if your version isn't the latest on official server - it's outdated
        print('Current VS server version {} is latest. No need to update.'.format(cur_version))
        return False
    else:
        print('Current VS server version {} is outdated. The latest is {}'.format(cur_version, last_version))
        return last_version


def do_update():
    check_result = check_for_update()
    if check_result:
        update_server('{}vs_server_{}.tar.gz'.format(vs_server_url, check_result))


if __name__ == '__main__':
    do_update()
