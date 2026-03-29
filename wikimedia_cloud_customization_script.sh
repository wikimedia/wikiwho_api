#!/bin/bash

# This is used as the Customization Script to automate some of the setup on Wikimedia Cloud
# when creating a new instance via Horizon.

# Create a wikiwho user
useradd -m wikiwho
# Set default shell
usermod --shell /bin/bash wikiwho

# Set up the directory structure (except for the pickles, which live on a Cinder volume)
mkdir /home/wikiwho/dumps
chown -R wikiwho /home/wikiwho

mkdir /var/log/django
chown wikiwho /var/log/django

# Install Python prerequisites
apt-get install -y python3.9-dev build-essential graphviz libgraphviz-dev pkg-config python3-venv postgresql libpq-dev libxml2-dev libxslt-dev virtualenvwrapper
# Install production webservice prerequisites
apt-get install -y nginx memcached libcache-memcached-perl libanyevent-perl rabbitmq-server p7zip-full apache2-utils

# Per wiki: Change the swappiness to a lower value to better use of RAM memory and not swap
sysctl -w vm.swappiness=5
echo "vm.swappiness=5" >> /etc/sysctl.conf

# Add gunicorn service
cp /home/wikiwho/wikiwho_api/deployment/ww_gunicorn.service /etc/systemd/system/ww_gunicorn.service

# Add nginx config and enable it
# Based on XFF headers, we rate limit each IP (60/min).
# Requests from XTools are not rate limited.
# Rate limit allowlist strategy from https://serverfault.com/questions/177461/how-to-rate-limit-in-nginx-but-including-excluding-certain-ip-addresses
cp /home/wikiwho/wikiwho_api/deployment/nginx.conf /etc/nginx/sites-available/wikiwho
rm /etc/nginx/sites-enabled/default
ln -s /etc/nginx/sites-available/wikiwho /etc/nginx/sites-enabled/wikiwho

# Set up rabbitmq
rabbitmqctl add_user ww_worker ww_worker_password
rabbitmqctl add_vhost ww_vhost
rabbitmqctl set_user_tags ww_worker ww_tag
rabbitmqctl set_permissions -p ww_vhost ww_worker ".*" ".*" ".*"
rabbitmq-plugins enable rabbitmq_management
rabbitmq-server -detached

# Register creation of the /var/run/celery directory on reboot
echo """
d /var/run/celery 0755 wikiwho wikiwho -
""" > /etc/tmpfiles.d/celery.conf

# Add Celery config
cat /home/wikiwho/wikiwho_api/deployment/ww_celery.service > /etc/systemd/system/ww_celery.service

mkdir /etc/conf.d
echo """
# CELERY Conf for systemd service /etc/systemd/system/ww_celery.service
CELERYD_NODES="worker_default worker_user worker_long"
CELERY_BIN="/home/wikiwho/wikiwho_api/env/bin/celery"
CELERY_APP="wikiwho_api"
CELERYD_CHDIR="/home/wikiwho/wikiwho_api"
CELERYD_OPTS="--hostname=ww_host -Ofair:worker_default -Q:worker_default default -c:worker_default 8 -Q:worker_user user -c:worker_user 4 -Q:worker_long long -c:worker_long 4"
CELERYD_LOG_LEVEL="WARNING"
CELERYD_LOG_FILE="/var/log/celery/%n%I.log"
CELERYD_PID_FILE="/var/run/celery/%n.pid"
CELERYD_USER="wikiwho"
CELERYD_GROUP="wikiwho"
CELERY_CREATE_DIRS=1
BROKER_HEARTBEAT=0
""" > /etc/conf.d/celery

mkdir /var/log/celery
chown wikiwho /var/log/celery
mkdir /var/run/celery
chown wikiwho /var/run/celery

# Add Flower config for monitoring Celery
# You must manually protect it with a password with the following command:
#   sudo htpasswd -c /etc/apache2/.htpasswd wikiwho
# (typing in the password when prompted)
cp /home/wikiwho/wikiwho_api/deployment/ww_flower.service /etc/systemd/system/ww_flower.service

# Add event-stream listening service
cp /home/wikiwho/wikiwho_api/deployment/ww_events_stream.service /etc/systemd/system/ww_events_stream.service

# Add deletion stream listening service
cp /home/wikiwho/wikiwho_api/deployment/ww_events_stream_deletion.service /etc/systemd/system/ww_events_stream_deletion.service

mkdir /var/log/django/events_streamer
chown wikiwho:www-data /var/log/django/events_streamer
