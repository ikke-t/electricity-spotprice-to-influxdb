FROM registry.fedoraproject.org/fedora-minimal:latest
MAINTAINER "Ilkka Tengvall"

RUN mkdir /srv/app && \
   microdnf install -y \
      python3-pandas python3-pytz python3-pip python3-influxdb-client && \
    pip3 install entsoe-py

WORKDIR /srv/app

COPY elespot2inf.py .

VOLUME /data

ENV CONF=${CONF:-/data/elespot2inf.ini}

ENTRYPOINT /usr/bin/python3 elespot2inf.py $CONF
