# Setting up WikiWho from scratch

1. Create a VPS on horizon.wikimedia.org
   * 24 core, 122GB RAM machine
   * Debian 11
   * `webservice` security group
2. Configure a Cinder volume on horizon.wikimedia.org
   * 5000 GB
   * attach to the VPS
3. Add a Web Proxy on Horizon (`wikiwho.wmcloud.org` or something else from the `settings_wmcloud.py` hosts entry)
   1. Also do the same for `wikiwho-flower.wmcloud.org`
4. SSH into the VPS
5. Prepare the Cinder volume.
   1. `sudo wmcs-prepare-cinder-volume`
   2. mount it to `/pickles`
   3. `sudo mkdir -p /pickles/{en,eu,es,de,tr}`
   4. `sudo chown -R wikiwho /pickles`
6. Clone the repo and make `wikiwho` own it:
   1. `git clone https://github.com/wikimedia/wikiwho_api.git /home/wikiwho/wikiwho_api`
   2. `chown -R wikiwho:wikiwho /home/wikiwho/wikiwho_api`
7. Run the customization script:
   1. `sudo sh wikimedia_cloud_customization_script.sh`
8. Add the password for the Flower UI:
   1. `sudo htpasswd -c /etc/apache2/.htpasswd wikiwho`
9. Create the wikiwho postgres user and database:
   1. `sudo su postgres`
   2. `psql`
      1. `create user wikiwho with password 'wikiwho';`
      2. `create database wikiwho;`
      3. `grant all privileges on database wikiwho to wikiwho;`
      4. `exit;`
   3. `exit`
10. Become the wikiwho user: `sudo su wikiwho`
11. `cd /home/wikiwho/wikiwho_api`
12. Set up a virtualenv:
    1. `python3 -m venv env`
    2. `. env/bin/activate`
13. Install the Python dependencies: `pip install -r requirements.txt -r requirements_local.txt -r requirements_test.txt`
14. Create `wikiwho_api/settings.py` (in the wikiwho_api subdirectory, not the top git directory), with an import from `settings_wmcloud` plus SECRET_KEY, WP_CONSUMER_TOKEN, WP_CONSUMER_SECRET, WP_ACCESS_TOKEN, WP_ACCESS_SECRET, and DATABASES.
     1. Generate a secret key: `python manage.py generate_secret_key`
15. `python manage.py migrate`
16. `python manage.py collectstatic --noinput -c`
17. As a user with sudo, start the Gunicorn webserver:
    1.  `sudo systemctl enable ww_gunicorn`
    2.  `sudo systemctl start ww_gunicorn`
    3.  `sudo systemctl status ww_gunicorn` to check if it's running
    4.  API and homepage should be working now.
18. Start Celery:
    1.  `sudo systemctl enable ww_celery`
    2.  `sudo systemctl start ww_celery`
    3.  `sudo systemctl status ww_celery` to check if it's running
19. Import dumps (as user `wikiwho`)
    1.  `sudo su wikiwho`
    2.  `mkdir -p /pickles/{en,eu,es,de,tr}`
    3.  Download the latest dumps for each of the languages to import, eg:
        1.  `cd /pickles/dumps/en`
        2.  New format (bz2): `wget -r -np -nd -c -A bz2 https://dumps.wikimedia.org/other/mediawiki_content_history/enwiki/{datestamp}/xml/bzip2/`
        3.  Legacy format (7z, deprecated): `wget -r -np -nd -c -A 7z https://dumps.wikimedia.your.org/enwiki/20211201/`
    4.  For each language, generate pickles from the XML dumps, eg:
        1.  `cd ~/wikiwho_api`
        2.  `. env/bin/activate`
        3.  `nohup python manage.py generate_articles_from_wp_xmls -p '/pickles/dumps/en/' -t 30 -m 24 -lang en -c`
20. Start Flower and event_stream services
    1.  `sudo systemctl enable ww_flower.service`
    2.  `sudo systemctl start ww_flower.service`
    3.  `sudo systemctl status ww_flower.service` to check if it's running
    4.  `sudo systemctl enable ww_events_stream.service`
    5.  `sudo systemctl start ww_events_stream.service`
    6.  `sudo systemctl status ww_events_stream.service` to check if it's running
    7.  `sudo systemctl start ww_events_stream_deletion.service`
    8.  `sudo systemctl status ww_events_stream_deletion.service` to check if it's running
21. Add cronjob to restart services daily (see [T344936](https://phabricator.wikimedia.org/T344936)
    for more information).
    1.  `sudo su root`
    2.  `crontab -e`
    3.  Add the entry `0 0 * * * /home/wikiwho/wikiwho_api/cron/restart_services.sh`

# Adding new languages to WikiWho

## Prerequisites

Make sure the language is supported by Django. If it's not:

1. Add the language to `EXTRA_LANG_INFO` in `wikiwho_api/settings.py` with the appropriate `bidi` and `code` values.
2. Generate the `.po` file for the language with `python manage.py makemessages -l [langcode]`
3. Open the generated `locale/[langcode]/LC_MESSAGES/django.po` file and set the `Plural-Forms` to something like
  `nplurals=2; plural=(n != 1);` (or the appropriate plural form for the language). It may not actually be important
  that this is correct, since we only use Django i18n for the paths, and not for the WikiWho alogirthm itself. 
  Similarly, the translations (`msgstr`) in the `.po` file may be left blank.
4. Compile the messages with `python manage.py compilemessages -l [langcode]`
5. Follow the steps below and make sure things work locally before deploying to production.

## Steps

1. Download the dumps into a volume (new languages most likely should go in the new `pickle_storage03`, mounted to `/pickles-03`)
    1. `mkdir /pickles-03/{lang}`
    2. `mkdir /pickles-03/dumps/{lang}`
    3. `cd /pickles-03/dumps/{lang}`
    4. `screen`
    5. Download dumps (either format works):
        1. New format (bz2, preferred): `wget -r -np -nd -c -A bz2 https://dumps.wikimedia.org/other/mediawiki_content_history/{lang}wiki/{datestamp}/xml/bzip2/`
        2. Legacy format (7z, deprecated): `wget -r -np -nd -c -A 7z https://dumps.wikimedia.org/{lang}wiki/{datestamp}/`
            1. Use the latest complete dump. Newer versions may be available at https://dumps.wikimedia.your.org
            2. If you get an error or otherwise no files were downloaded, the dump may be incomplete. Try using an older dump.
    6. The hit Ctrl+A and the `d` key to detach from screen and keep the downloading of the dumps running in the background.
    7. When you thnk it may be finished, verify by reentering the screen session with `screen -r`, then type `exit` if it's finished or use Ctrl+A and `d` to detch again.
2. Create a pull request to add the new language to the app, except for EventStreams ([example PR](https://github.com/wikimedia/wikiwho_api/pull/24)).
    1. The migrations can be created with `python manage.py makemigrations rest_framework_tracking api --empty`, and then fill in the code accordingly, using previous migrations as a guide. These migrations may eventually not be necessary, pending the outcome of [T335322](https://phabricator.wikimedia.org/T335322).
3. Start the import process on the VPS instance:
    1. `sudo su wikiwho`
    2. `cd ~/wikiwho_api`
    3. `git pull origin main`
    4. `. env/bin/activate`
    5. `python manage.py migrate`
    6. `nohup python manage.py generate_articles_from_wp_xmls -p '/pickles/dumps/{lang}/' -t 30 -m 24 -lang {lang} -c` then Ctrl+Z and then enter `bg` to background the process.
    7. After typing `top`, you should see ~24 `python` processes running. You can monitor progress with `ls -al /pickles-02/{lang}/ | wc -l` and that number should eventually roughly equal the total number of articles on the wiki. Note this command will run very slow after there are hundreds of thousands or millions of pickle files.
4.  Once complete, create a PR to add the wiki to EventStreams ([example PR](https://github.com/wikimedia/wikiwho_api/pull/7)).
5.  Deploy and restart services (using your account and not `wikiwho`):
       1. Pull in latest changes
       2. Restart the Flower and EventStreams services with `sudo systemctl restart ww_flower.service` and `sudo systemctl restart ww_events_stream.service`
       3. Restart Celery with `sudo systemctl restart ww_celery.service`
6.  Update clients accordingly (XTools, Who Wrote That?, Programs & Events Dashboard, etc.)

# Troubleshooting

Some various tips to help troubleshoot issues in production:

* Check https://wikiwho-flower.wmcloud.org to monitor Celery tasks.
* Use `sudo journalctl -u ww_events_stream` to view the logs for the `ww_events_stream`
  service, or replace with another service name such as `nginx`.
* See also the Celery logs at `/var/log/celery/*.log`.
