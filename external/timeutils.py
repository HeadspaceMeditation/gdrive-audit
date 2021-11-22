from datetime import datetime
import time
import dateutil
import dateutil.parser


def datetime_with_utc_tz(dt=None):
    """
    Convert datetime object to a UTC datetime object.
    :param dt:
    :return:
    """
    dt = dt or datetime.utcnow()
    if not isinstance(dt, datetime):
        return dt
    elif dt.tzinfo:
        dt = dt.astimezone(dateutil.tz.UTC)
    else:
        dt.replace(tzinfo=dateutil.tz.UTC)
    return dt


def iso_utcz_strftime(dt):
    """
    Get iso formatted utc date time string formatted with 'Z' notation.
    :param dt:
    :return:
    """
    if not isinstance(dt, datetime):
        raise ValueError("Datetime object expected.")
    dt = datetime_with_utc_tz(dt)
    return datetime.strftime(dt, "%Y-%m-%dT%H:%M:%SZ")


def iso_strptime(dt_string):
    """
    Parse an iso8601 date string.
    :param dt_string:
    :return:
    """
    dt = dateutil.parser.parse(dt_string)
    if not dt.tzinfo:
        dt.replace(tzinfo=dateutil.tz.UTC)
    return dt


def to_unix_ts(a_datetime=None):
    """ Get a unix timestamp for datetime instance. """
    if not a_datetime:
        a_datetime = datetime.utcnow()
    return time.mktime(a_datetime.timetuple())


def datetime_from_epoch(timestamp):
    """
    Get datetime from epoch.
    :param int timestamp: seconds or milliseconds since epoch
    :returns: datetime
    :raises: ValueError, TypeError
    """
    if timestamp > 9999999999:
        timestamp = timestamp / 1000
    return datetime.utcfromtimestamp(timestamp)
