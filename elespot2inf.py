#!python3
"""
This module keeps feeding electricity spot prices into influxdb.  It is
recommended to run this periodicly e.g. from systemd timer or cronjob.

Program needs config file describing the influxdb and entsoe auth info.

Get the Entsoe API token and library info from here:
https://github.com/EnergieID/entsoe-py

To get going with influxdb and entsoe API:
    python3 -m venv virtualenv
    source virtualenv/bin/activate
    pip install influxdb-client entsoe-py
https://docs.influxdata.com/influxdb/cloud/api-guide/client-libraries/python/

Author: Ilkka Tengvall <ilkka.tengvall@iki.fi>
License: GPLv3 or later
"""

from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime, timedelta
import pytz
import json
import configparser
import logging
import pandas as pd
import sys

from entsoe import EntsoePandasClient

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

def check_start_date(client, bucket, location):
    """
    Find the previous last date of spotprices from influxdb if any.
    """
    query_api = client.query_api()
    time = ""

    query = 'from(bucket:"' + bucket + '")\
             |> range(start: -4w)\
             |> filter(fn:(r) => r._measurement == "spotprice")\
             |> last()'

    tables = query_api.query(query=query)

    for table in tables:
        logging.info(table)
        for record in table.records:
            time = record["_time"]
            logging.info(str(time) + ' - ' + record["_measurement"] + ': ' + str(record["_value"]))
    return time

def get_prices(start_date, location, key):
    """ query prices since date give with given api key."""

    start = pd.Timestamp(start_date, tz='Europe/Helsinki')
    end = pd.Timestamp(datetime.now()+timedelta(hours=48),
                       tz='Europe/Helsinki')
    logging.info(f"start[%s] - end[%s]", start, end)

    client = EntsoePandasClient(api_key=key)
    prices = client.query_day_ahead_prices(location, start=start, end=end)
    return prices

def send_prices(prices, influxdb_client, bucket):
    """
    We send data to influxdb. Datapoints are in prices panda table, and we
    connect to influxdb using prepared client.
    """
    write_api = influxdb_client.write_api(write_options=SYNCHRONOUS)
    success = 0

    for time, price in prices.iteritems():
        point = Point("spotprice") \
            .field('hourly', price) \
            .time(time)
        logging.info(f"Writing: {point.to_line_protocol()}")
        client_response = write_api.write( bucket=bucket, record=point)
        # write() returns None on success
        if client_response is None:
            success += 1
    return success


if __name__ == "__main__":

	# pylint: disable=C0103
    error = False
    config = configparser.ConfigParser()
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = 'elespot2inf.ini'
    config.read(config_path)

    verbosity = config.get('debug', 'verbosity', fallback='NOTSET')
    logging.basicConfig(level=verbosity, format='%(levelname)s:%(message)s')
    logging.debug('loglevel %s', verbosity)
    logging.debug('using config %s', config_path)

    influxdb_client = InfluxDBClient(url=config.get('influx2', 'url'),
                                     token=config.get('influx2', 'token'),
                                     org=config.get('influx2', 'org'))
    bucket = config.get('influx2', 'bucket')
    location = config.get('entsoe', 'location')
    start = check_start_date(influxdb_client, bucket, location)
    if start == "":
        # time = datetime.datetime.now() + datetime.timedelta(weeks=2)
        start = datetime.now() - timedelta(weeks=2)
        logging.debug('No previous price data found, let\'s get it since: %s',
                      start)
    else:
        # start after one hour from previous end time
        start = start + timedelta(hours=1)
        logging.debug('start: %s', start)
        #  logging.debug('start type: %s', type(start))
        #  eka = start.astimezone(pytz.timezone('Europe/Helsinki'))
        #  logging.debug('start converted: %s', eka)
        #  toka = start.astimezone(pytz.utc)
        #  logging.debug('start converted: %s', toka)
        start = str(start.astimezone(pytz.utc))
        logging.debug('start: %s', start)

    prices = get_prices(
        start,
        config.get('entsoe', 'location'),
        config.get('entsoe', 'entsoe_api_key'))

    logging.debug('Received data for %d hours.', prices.size/2)

    if prices.size == 0:
        logging.debug('No data received, exiting')
        exit()

    result = send_prices(prices, influxdb_client, bucket)
    logging.debug('Succeeded to send %d hours.', result)

    influxdb_client.close()

    exit()
