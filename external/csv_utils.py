
import unicodecsv as csv
import os
import re
import random
from io import BytesIO
from itertools import izip_longest


# Mime types relevant to spreadsheets.
mime_type_csv = "text/csv"
mime_type_xls = "application/vnd.ms-excel"
mime_type_xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
mime_type_gdrive_spreadsheet = "application/vnd.google-apps.spreadsheet"
mime_type_gdrive_document = "application/vnd.google-apps.document"
mime_type_pgp = "application/pgp-encrypted"
mime_type_binary = "application/octet-stream"


def get_line_ending(s):
    """ Determine the line endings in use in a string formatted as csv. """
    return "\r\n" if s.find("\r\n") != -1 else "\n" if s.find("\n") else "\r"


def isplitlines(s):
    """ Generator which yields individual lines of a string. """
    ln_end = get_line_ending(s)
    boundary_len = len(ln_end)
    next = 0
    while next < len(s):
        end = s.find(ln_end, next)
        end = len(s) if end == -1 else end
        yield s[next:end]
        next = end + boundary_len
    raise StopIteration()


def prepend_column_headings_row(header_row, csv_data):
    """ Prepend column header row to csv data without a column header. """
    ln_end = get_line_ending(csv_data)
    first_row = csv_data.split(ln_end, 1)[0]
    if len(header_row.split(",")) != len(first_row.split(",")):
        raise IndexError("Header row does not have the same number of columns as data.")
    return header_row + ln_end + csv_data


def generate_random_chars(length=6):
    upper_alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    random_code = "".join(random.choice(upper_alpha) for _ in xrange(length))
    return random_code


def clean_field_name(value):
    # Strip out non word chars except '|', remove duplicate '_' characters and lower case the string.
    return re.sub(r"_{2,}", r"_", re.sub(r"[^a-z0-9|_]", r"_", value.strip().lower())).strip("_")


def records_from_string(csv_content):
    """
    Get an array of dictionaries from a string containing csv formatted data.
    :param csv_content:
    :return:
    """
    if not isinstance(csv_content, unicode):
        # Force string input to unicode.
        csv_content = csv_content.decode("utf-8", errors="replace")
    # And then encode back to str
    csv_content = csv_content.encode("utf-8", errors="replace")
    string_reader = BytesIO()
    string_reader.write(drop_empty_rows(csv_content))
    string_reader.seek(0)
    records = records_from_csv_source(string_reader)
    string_reader.close()
    return records


def records_from_file(file_path):
    # Import from file at path.
    with open(file_path, 'r') as f:
        results = records_from_csv_source(f)
    return results


def get_header_row(csv_content):
    if not csv_content:
        return csv_content
    try:
        for line in isplitlines(csv_content):
            if not line.replace(',', '').strip():
                continue
            return line
    except StopIteration:
        return None


def drop_empty_rows(csv_content):
    """ Strip empty rows from a csv formatted string. """
    if not csv_content:
        return csv_content
    return "\r\n".join(line for line in isplitlines(csv_content)
                        if line.replace(',', '') != '')


def purge_fields(records, fields):
    """
    Remove the specified fields from the provided records.
    :param records:
    :param fields: Array of field names to drop.
    :return: Array of dicts with specified columns dropped.
    """
    to_purge = set(fields)
    return [{k: v for k, v in record.iteritems() if k not in to_purge} for record in records]


def randomize_fields(records, fields_to_randomize, length=6):
    """
    Randomize the values contained within fields specified in the given array of dictionaries.
    Used to redact sensitive data from columns in order to generate test data.
    :param records: array of dictionaries
    :param fields_to_randomize: field_names to be randomized
    :param length: number of random characters to generate per value
    :return: dict with redacted data.
    """
    to_randomize = set(fields_to_randomize)
    return [
        {field_name: generate_random_chars(length=length) if field_name in to_randomize else value
         for field_name, value in record.iteritems()}
        for record in records]


def records_from_csv_source(f):
    """
    Get an array of dictionaries by reading lines from an open file like source.
    The first line of data in the datasource is expected to be the .
    :param f:
    :return:
    """
    results = []
    reader = csv.reader(f)
    field_names = []
    for i, row in enumerate(reader):
        if i == 0:
            field_names = row
            field_names = [clean_field_name(x) for x in field_names]
            continue

        record = dict_from_row(field_names, row)
        if record:
            results.append(record)
    return results


def dict_from_row(column_names, row):
    # Return a None padded dictionary from the given row for the given header values.
    if not any(row):
        # Return None if row is empty.
        return None
    truncated_row = row[:len(column_names)]
    return dict(izip_longest(column_names, truncated_row))


class PasswordProtectionError(Exception):
    pass


def records_to_string(records):
    """
    Get a csv string representation of an array of dictionaries.
    :param records:
    :return:
    """
    if not records:
        return None
    string_writer = BytesIO()
    write_records(string_writer, records)
    string_writer.seek(0)
    content = string_writer.read().decode('utf-8')
    string_writer.close()
    return content


def records_to_file(writable, records):
    """
    Write an array of dictionaries to a csv formatted file.
    :param writable: file obj or file path.
    :param records:
    :return:
    """

    if not records:
        return

    if hasattr(writable, "write"):
        # This is a file object.
        write_records(writable, records)
        return

    with open(writable, 'w') as f:
        write_records(f, records)


def write_records(writable, records):
    """
    Write an array of records to open writable IO.
    :param writable:
    :param records:
    :return:
    """
    writer = csv.writer(writable)
    fields = records[0].keys()
    fields.sort()
    writer.writerow(fields)
    for record in records:
        row = [record.get(field) for field in fields]
        if any(row):
            writer.writerow(row)


def partition_csv(filehandler, delimiter=',', row_limit=10000,
                  prefix='out', output_path='.', keep_headers=True, dump_strings=False):
    """
    Partition a csv file into multiple files.

    `row_limit` may either be a single integer or an array of integers if a variable page size is required.

    If a single integer is provided, each generated sheet will contain up to `row_limit` rows.

    If an array of integers is supplied and the page sizes are exhausted before the source csv,
    the last specified page size will be used to paginate the remainder of the source csv.

    Example: if the source csv has 400 rows and row_limit is provided as [10,90,100]
             then 5 sheets would be generated sized 10, 90, 100, 100, 100.

    This will create as many partitions as needed, named  "`prefix`_%i.csv"
         where i is the 0 indexed page number.

    By default, the first row of each partition will contain the cleaned column names.

    If dump_strings is set to true, no files will be written,
        the sheets will be returned as an array of strings, where each
        string represents a single sheet.
    """
    splits = None
    if hasattr(row_limit, "__iter__"):
        splits = row_limit

    def get_page_size(page_number):
        if not splits:
            return row_limit
        if len(splits) > page_number:
            return splits[page_number]
        if splits:
            return splits[-1]
        return 10000

    output_name_template = prefix + "_%s.csv"
    reader = csv.reader(filehandler, delimiter=delimiter)
    current_piece = 0
    string_output = []
    out_handle = None
    if dump_strings:
        out_handle = BytesIO()
        current_out_writer = csv.writer(out_handle, delimiter=delimiter)
    else:
        current_out_path = os.path.join(
            output_path,
            output_name_template % current_piece
        )
        out_handle = open(current_out_path, 'w')
        current_out_writer = csv.writer(out_handle, delimiter=delimiter)

    current_limit = get_page_size(current_piece)
    if keep_headers:
        headers = reader.next()
        current_out_writer.writerow(headers)
    for i, row in enumerate(reader):
        if i + 1 > current_limit:
            current_piece += 1
            current_limit = current_limit + get_page_size(current_piece)
            if dump_strings:
                out_handle.seek(0)
                string_output.append(out_handle.read())
                out_handle.close()
                out_handle = BytesIO()
                current_out_writer = csv.writer(out_handle, delimiter=delimiter)
            else:
                current_out_path = os.path.join(
                    output_path,
                    output_name_template % current_piece
                )
                current_out_writer = csv.writer(open(current_out_path, 'w'), delimiter=delimiter)
            if keep_headers:
                current_out_writer.writerow(headers)
        current_out_writer.writerow(row)
    if dump_strings:
        string_output.append(out_handle.getvalue())
        out_handle.close()
        return string_output
