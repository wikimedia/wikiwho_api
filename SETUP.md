## Development setup

* Use python3.9 or earlier.
* Use pip 23.1.0 or earlier.
  
* `sudo apt-get install -y python3-dev graphviz libgraphviz-dev pkg-config python3-venv postgresql libpq-dev libxml2-dev libxslt-dev virtualenvwrapper`
* clone the project and enter the project directory
* `python -m venv env`
* `. env/bin/activate`
* `pip install --upgrade setuptools==81.0.0`
* `pip install -r requirements.txt -r requirements_local.txt -r requirements_test.txt`
* create `wikiwho_api/settings.py`
* set up the database
* run a server with `python manage.py runserver`


## Notes from trying to stand up app

### Requirements

* I had to edit the line `-e git+git@github.com:gesiscss/wikiwho_chobj.git#egg=wikiwho_chobj`. It's public, so the equivalent is `-e git://github.com/gesiscss/wikiwho_chobj.git#egg=wikiwho_chobj` (this has now been changed to `wikiwho_chobj @ git+https://github.com/gesiscss/wikiwho_chobj@master` which should work).
* I had to relax the pytest version requirement (in both requirements.txt and requirements_test.txt).
* I'm using a virtualenv, so I added `env` to the .gitignore
* Installation didn't work until I had an up-to-date version of `pip3`.
* I had to install some build dependencies (`sudo apt-get install python3-dev graphviz libgraphviz-dev pkg-config`) to be able to install the `requirements_local.txt`.
* To get versions of all the dependencies that are compatible with each other, I had to do all requirements files in one command: `pip3 install -r requirements.txt -r requirements_local.txt -r requirements_test.txt`
* This runs the latest release of the Django 1.x series (1.11), which was an LTS release but is out of its support window. We'll probably want to try to upgrade to Django 2.0 first and then 3.0.

### Running the server
* Can't start the server initially (`python3 manage.py runserver localhost:8000`) because there is no wikiwho_api/settings.py 
  * Copied settings_local.py to settings.py, then added `SECRET_KEY = 'secret'`

* I had to add DATABASES to settings.py, and create the matching user+password and database in postgres:

```
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2', 
        'NAME': 'wikiwho',                     
        'USER': 'wikiwho',
        'PASSWORD': 'wikiwho',
        'HOST': 'localhost'
    }
}
```

* changing the MIDDLEWARE variable name in the settings just silences a warning.

### Registering an OAuth consumer

The app requires OAuth consumer credentials to make API requests. Register an 'owner-only' consumer with only basic permissions here: https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose

Put the 4 values into settings.py as WP_CONSUMER_TOKEN, WP_CONSUMER_SECRET, WP_ACCESS_TOKEN, and WP_ACCESS_SECRET. (You don't need to set WP_USER or WP_PASSWORD.)

### Running Celery in development

Instead of the complex instructions for running Celery from the wiki, you can run a worker directly from a terminal (once rabbitmq is set up).

1. [Install RabbitMQ](https://www.rabbitmq.com/download.html). Linux users should be okay to install with just `sudo apt-get install rabbitmq-server`.
2. Within the virtual env, start celery with `celery -A wikiwho_api worker --loglevel=INFO`
3. If you need to test with EventStreams, start that worker with `python manage.py celery_changed_articles`,
   and another worker for the revision deletion events with `python manage.py celery_deletion_events`.
