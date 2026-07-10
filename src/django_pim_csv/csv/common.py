# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import csv
import decimal
import json
import logging
import os
from datetime import datetime
from decimal import InvalidOperation

from django.utils import timezone

from django_pim_csv.settings import DATETIME_FORMAT_IMPORT

logger = logging.getLogger("django")

BOOL_TRUE_VALUES = ("yes", "true", "1", "prawda")


class CommonCsv:
    # in how many rows header is analyzed
    ROWS_ANALYZED = 10

    def __init__(self):
        self._data_id_loaded = False
        self.file_path = None
        self.pre_header = []  # data found before header
        self.sheet = []  # csv data loaded to ram without header
        self.name = "Common CSV"
        self.cols = []
        self.cols_required = []
        self.max_columns = None
        self.max_rows = None
        self.cols_index = None
        self.load_all_cols = False
        self.header_row_nr = None  # header is on row nr starting from 0
        self.header = None
        self.current_index = 0  # iterator vars

    def __iter__(self):
        self.current_index = 0  # iterator vars
        if not self._data_id_loaded:
            raise Exception("Data is not loaded from csv file")
        return self

    def __next__(self):
        if self.current_index < self.max_rows:
            row = self.sheet[self.current_index]
            self.current_index += 1
            return row
        raise StopIteration

    def init_sheet(self):
        self.info('Validating data, cols required: "{}"'.format('", "'.join(self.cols_required)))
        self.remove_empty_columns()
        self.init_max_columns()
        self.header_discovery()
        self.reindex_columns()
        self.raport_columns_indexes()
        self.remove_header_from_sheet()
        self.max_rows = len(self.sheet)
        self.info(f"Sheet has {self.max_rows} rows of data")

    def remove_header_from_sheet(self):
        self.pre_header = []
        for nr in reversed(range(0, self.header_row_nr + 1)):
            self.pre_header.append(self.sheet[nr])
            del self.sheet[nr]

    def load_file(self, file_path):
        file_path_abs = os.path.abspath(file_path)
        if not os.path.isfile(file_path_abs):
            raise Exception("File does not exist: %s" % file_path_abs)
        self.file_path = file_path
        logger.info('Loading file: "%s", checking format' % self.file_path)
        csv.register_dialect("volkanoscsv", delimiter=",", quoting=csv.QUOTE_MINIMAL)
        with open(self.file_path, newline="") as fh:
            reader = csv.reader(fh, "volkanoscsv")
            for row in reader:
                self.sheet.append(row)
        self.init_sheet()
        self._data_id_loaded = True

    def set_header_row_nr(self, header_row_nr):
        logger.info(f"Setting header row nr={header_row_nr}")
        self.header_row_nr = header_row_nr

    def init_header(self, header_row_nr):
        self.header = []
        self.set_header_row_nr(header_row_nr)
        for col_nr in range(0, self.max_columns):
            try:
                value = self.sheet[header_row_nr][col_nr]
                if value is None:
                    self.header.append(None)
                else:
                    value = value.strip()
                    self.header.append(value)
            except IndexError:
                self.header.append(None)
        for col in self.cols_required:
            if col not in self.header:
                raise Exception(f"Niepoprawny format, brak kolumny: {col}, header: {self.header}")

    def header_discovery(self):
        """przegladam pierwsze 10 wierszy i jesli mam "cols_required" to uwazam, ze znalazlem header start"""
        if len(self.cols_required) == 0:
            raise Exception("Required cols must be set, define 'cols_required'")
        rows_for_debug = []
        features_found = []
        row_nr = -1
        for row in self.sheet:
            rows_for_debug.append(row)
            row_nr += 1
            found_required = 0
            found = 0
            for col_req in self.cols_required:
                if col_req in row:
                    features_found.append(col_req)
                    found_required += 1
            for col in self.cols:
                if col in row:
                    found += 1
            if found_required == len(self.cols_required):
                return self.init_header(row_nr)
        raise Exception(
            f"Can not discover header row, cols_required={self.cols_required}, features found = {features_found}"
        )

    def reindex_columns(self):
        self.cols_index = {}
        for col in self.header:
            self.cols_index[col] = self.header.index(col)

        if not self.load_all_cols:
            for col in self.cols:
                if col not in self.header:
                    self.cols_index[col] = None

    def info(self, msg):
        print(msg)
        logger.info(msg)

    def raport_columns_indexes(self):
        row_header = "+====================================+===========+=============+===========+"
        tpl = "| {:<34} | {:>9} | {:>11} | {:>9} |"
        self.info("Columns discovered:")
        self.info(row_header)
        self.info(tpl.format("Column Name", "Column Nr", "Is required", "Ignored"))
        self.info(row_header)
        other_cols = self.header[:]  # copy values, not reference
        for col in self.cols:
            if col in self.cols_index and self.cols_index[col] is not None:
                is_required = "required" if col in self.cols_required else ""
                msg = tpl.format(col, self.cols_index[col] + 1, is_required, "")
                other_cols.remove(col)
                self.info(msg)
        for col in other_cols:
            try:
                msg = tpl.format(col, self.cols_index[col] + 1, "", "ignored")
            except TypeError:
                msg = tpl.format(f"{col}", "", "", "ignored")
            self.info(msg)
        self.info(row_header)

    def remove_empty_columns(self):
        # analyzing values in first 10 rows which should include header
        # remove all cols without values
        msg = "Analyzing and removing empty columns"
        logger.info(msg)
        print(msg)
        values_found = []
        row_cnt = 0
        for row in self.sheet:
            row_cnt += 1
            if row_cnt > self.ROWS_ANALYZED:
                break
            col_nr = 0
            for val in row:
                col_nr += 1
                if len(values_found) < col_nr:
                    values_found.append(False)
                if values_found[col_nr - 1]:
                    continue
                if val is not None and str(val) != "":
                    values_found[col_nr - 1] = True
        cols_removed = []
        for col_nr in reversed(range(1, len(values_found) + 1)):
            if not values_found[col_nr - 1]:
                cols_removed.append(str(col_nr))
                self.delete_col(col_nr)
        if cols_removed:
            m = "Removed columns nr={}".format(", ".join(reversed(cols_removed)))
            logger.info(m)
            print(m)
        else:
            print("No columns has beed removed")

    def init_max_columns(self):
        # analyzing values in first 10 rows which should include header
        max_columns = 0
        row_cnt = 0
        for row in self.sheet:
            row_cnt += 1
            if row_cnt > self.ROWS_ANALYZED:
                break
            if len(row) > max_columns:
                max_columns = len(row)
        msg = f'MAX Columns Discovery: sheet has: max_columns="{max_columns}"'
        logger.info(msg)
        print(msg)
        self.max_columns = max_columns

    def exists_col(self, col_id):
        return False if self.get_col_index(col_id) is None else True

    def get_col_index(self, col_id):
        try:
            return self.cols_index[col_id]
        except:
            return None

    def get_col_nr(self, col_id):
        idx = self.get_col_index(col_id)
        if idx is None:
            return None
        return idx + 1

    def get_value(self, row_nr, col_id):
        col_nr = self.get_col_nr(col_id)
        if col_nr is None:
            return None
        cell_obj = self.sheet[row_nr][col_nr]
        return cell_obj.value

    def get_row_value(self, row, col_id):
        idx = self.get_col_index(col_id)
        if idx is None:
            return None
        try:
            val = row[idx]
        except IndexError:
            return None
        if val == "" or val is None:
            return None
        return val

    # zwraca '' zamiast None
    def get_row_value_txt(self, row, col_id):
        idx = self.get_col_index(col_id)
        if idx is None:
            return ""
        try:
            val = row[idx]
        except IndexError:
            return ""
        if val is None or val == "":
            return ""
        return val

    def get_row_value_int(self, row, col_id):
        idx = self.get_col_index(col_id)
        if idx is None:
            return None
        try:
            val = row[idx]
        except IndexError:
            return None
        if val == "" or val is None:
            return None
        return int(val)

    def get_row_value_datetime(self, row, col_id):
        idx = self.get_col_index(col_id)
        if idx is None:
            return None
        try:
            val = row[idx]
        except IndexError:
            return None
        if val == "" or val is None:
            return None
        try:
            # Parse the string to a datetime object
            date_object = datetime.strptime(val, DATETIME_FORMAT_IMPORT)
            # Localize the datetime object to the specified timezone
            date_object = timezone.make_aware(date_object, timezone.get_current_timezone())
        except (ValueError, Exception) as e:
            logger.exception(e)
            return None
        return date_object

    def get_row_value_decimal(self, row, col_id):
        idx = self.get_col_index(col_id)
        if idx is None:
            return None
        try:
            val = row[idx]
            val = val.strip(" ")
        except IndexError:
            return None
        if val is None or val == "":
            return None
        try:
            val = decimal.Decimal(val)
        except InvalidOperation:
            return None
        return val

    def get_row_value_bool(self, row, col_id, default=None):
        idx = self.get_col_index(col_id)
        if idx is None:
            return default
        try:
            val = row[idx]
        except IndexError:
            return default
        if val is None or val == "":
            return default
        val = val.strip().lower()
        if val in BOOL_TRUE_VALUES:
            return True
        return False

    def get_row_value_json(self, row, col_id):
        idx = self.get_col_index(col_id)
        if idx is None:
            return None
        try:
            val = row[idx]
        except IndexError:
            return None
        if val is None or val == "":
            return None
        val = val.strip()
        return json.loads(val)

    def get_row_value_t9n(self, row, col_id, langs: dict):
        value_t9n = {}
        for lang in langs:
            col_id_lang = self.generate_col_idx_with_lang(col_id, lang)
            value_t9n[lang] = self.get_row_value_txt(row, col_id_lang)
        return value_t9n

    def generate_col_idx_with_lang(self, col_id, lang):
        return f"{col_id} {lang}"

    def column_exists(self, col_idx):
        if self.header is None:
            return False
        return col_idx in self.header

    def append_column(self, col_idx):
        if col_idx in self.header:
            raise Exception(f"Can not add column idx={col_idx}, column already exists")
        logger.info(f'Appending column: "{col_idx}"')
        self.max_columns += 1
        self.header.append(col_idx)
        self.reindex_columns()

    def ensure_column_exists(self, col_idx):
        if self.column_exists(col_idx):
            return
        self.append_column(col_idx)

    def add_col_config(self, col_idx, is_required=False):
        if col_idx in self.cols:
            raise Exception(f"Can not add column idx={col_idx}, column already exists")
        self.cols.append(col_idx)
        if is_required:
            self.cols_required.append(col_idx)

    def get_header_row_nr(self):
        return self.header_row_nr

    def get_header_row(self):
        return self.sheet[self.header_row_nr]

    def get_max_rows(self):
        return self.max_rows

    def get_max_columns(self):
        return self.max_columns

    def get_row(self, row_nr):
        return self.sheet[row_nr]

    def append_row(self, row):
        return self.sheet.append(row)

    def delete_cols_after(self, delete_col_nr):
        for row in self.sheet:
            row_len = len(row)
            if delete_col_nr >= row_len:
                continue
            del row[delete_col_nr - 1 :]

    def delete_col(self, delete_col_nr):
        for row in self.sheet:
            try:
                del row[delete_col_nr - 1]
            except:
                pass
