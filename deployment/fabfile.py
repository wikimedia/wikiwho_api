import os

from fabric.api import cd, env, prefix, run, sudo, task, local, settings, abort, lcd
from fabric.contrib.console import confirm


PROJECT_NAME = 'wikiwho_api'


@task
def staging():
    env.hosts = ['wikiwho@staging.wikiwho.net']
    env.environment = 'staging'


@task
def production():
    env.hosts = ['wikiwho@www.wikiwho.net']
    env.environment = 'production'


def test(n, lines):
    local_project_root = '{}'.format(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tests = '{}/wikiwho/tests'.format(local_project_root)
    with lcd(tests), settings(warn_only=True):
        result = local('py.test {}/test_wikiwho_simple.py::TestWikiwho::test_json_output -n {} --lines={}'.
                       format(tests, n, lines))
        # result = local('py.test {}/test_wikiwho_simple.py::TestWikiwho::test_json_output -n 6'.format(tests))
        # result = local('./manage.py test my_app', capture=True)
        if result.failed and not confirm("Tests failed. Continue anyway?"):
            abort("Aborting at user request.")


@task
def prepare_deploy(n=6, lines='all'):
    # fab prepare_deploy:n=2,lines='2\,32'
    test(n, lines)


@task
def deploy(branch='master', mode='base'):
    # TODO pip install yok!
    # fab production deploy
    # fab production deploy:branch=dev,mode=full
    remote_project_root = '/home/wikiwho/wikiwho_api'
    with cd(remote_project_root):
        # with prefix('workon iwwa'):  # FIXME
        # with prefix('conda activate twwa'):
        with prefix('source /home/wikiwho/venvs/iwwa/bin/activate'):
            # run('which python')
            run('git checkout {}'.format(branch))
            run('git pull')
            # lib/WikiWho and lib/WhoColor are git submodules installed as local
            # packages (see requirements.txt); check out the pinned commits before
            # pip installs from them.
            run('git submodule update --init --recursive')

            if mode == 'full':
                run('pip install -U -r requirements.txt')
                run('pip install -U -r requirements_live.txt')
                run('python manage.py migrate')
                run('python manage.py collectstatic -c --noinput')
                run('python manage.py clean_pyc')
                # run('python manage.py clear_cache')
                run('python manage.py clearsessions')

            sudo('systemctl restart ww_gunicorn.service')
            if mode == 'full':
                sudo('systemctl restart nginx')
                # sudo('systemctl restart postgresql@9.6-main.service')
                # sudo('systemctl restart memcached.service')


@task
def setup():
    """Setup a new project"""
    # TODO mkdir project, mkvirtualenv, pip install ..... + deploy
