"""M8 bounded CSV/XLSX text snapshots. No policy, delivery, or framework state."""
import csv
import hashlib
import io
import zipfile
from dataclasses import replace
from datetime import datetime
from xml.etree.ElementTree import ParseError

import magic
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import IllegalCharacterError

from data_security.contracts import (BoundedPayload, ContractViolation, Coverage, FrozenJSON, Limits,
    MediaType, PayloadKind, ProtectionError, ReasonCode, TableCell, TableColumn, TableSnapshot, Unit)
from data_security.contracts.schema import reference, require

FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r', '\n', '＝', '＋', '－', '＠')
MAX_COMPRESSION_RATIO = 200
CODEC_VERSION = 'm8-table-text.v1'


def neutralize_formula(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def preflight_xlsx(content, limits):
    """Inspect bounded OOXML before openpyxl can expand or omit any channels."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = archive.infolist()
        require(len(members) <= limits.max_zip_members and
                sum(m.file_size for m in members) <= limits.max_expanded_bytes,
                ReasonCode.LIMIT_EXCEEDED)
        names = [m.filename for m in members]
        require(len(set(names)) == len(names), ReasonCode.UNSUPPORTED_FORMAT)
        require({'[Content_Types].xml', 'xl/workbook.xml'} <= set(names), ReasonCode.UNSUPPORTED_FORMAT)
        declared, relationships, raw_values = [], {}, {}
        sheets = total_cells = 0
        for member in members:
            name = member.filename
            require(not member.flag_bits & 1 and not name.startswith('/') and
                    '\\' not in name and '..' not in name.split('/'), ReasonCode.UNSUPPORTED_FORMAT)
            require(member.file_size <= MAX_COMPRESSION_RATIO * max(1, member.compress_size),
                    ReasonCode.LIMIT_EXCEEDED)
            # Only the simple text-grid subset is represented by TableSnapshot.
            supported = (name in ('[Content_Types].xml', '_rels/.rels', 'xl/workbook.xml',
                                  'xl/_rels/workbook.xml.rels', 'xl/styles.xml', 'xl/sharedStrings.xml') or
                         name.startswith(('docProps/', 'xl/theme/', 'xl/worksheets/')))
            require(supported and name.endswith(('.xml', '.rels')), ReasonCode.UNSUPPORTED_FORMAT)
            sheet = name.startswith('xl/worksheets/') and name.endswith('.xml')
            if sheet:
                sheets += 1
                raw_values[name] = {}
                require(sheets <= limits.max_sheets, ReasonCode.LIMIT_EXCEEDED)
            max_row = max_column = row_number = string_count = 0
            cell_type = None
            columns = set()
            with archive.open(member) as stream:
                for event, element in ElementTree.iterparse(stream, events=('start', 'end'),
                        forbid_dtd=True, forbid_entities=True, forbid_external=True):
                    tag = element.tag.rsplit('}', 1)[-1]
                    if event == 'start':
                        if tag == 'si':
                            string_count += 1
                            require(string_count <= limits.max_cells, ReasonCode.LIMIT_EXCEEDED)
                        require(tag not in ('f', 'mergeCell', 'hyperlink', 'drawing', 'legacyDrawing',
                            'oleObject', 'externalReference', 'definedName', 'tablePart', 'pivotTable',
                            'conditionalFormatting', 'dataValidation', 'headerFooter', 'extLst'),
                            ReasonCode.UNSUPPORTED_FORMAT)
                        require(element.get('TargetMode') != 'External', ReasonCode.UNSUPPORTED_FORMAT)
                        if name == 'xl/workbook.xml' and tag == 'sheet':
                            require(element.get('state', 'visible') == 'visible', ReasonCode.UNSUPPORTED_SCOPE)
                            declared.append((element.get('name'), element.get(
                                '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')))
                        if name == 'xl/_rels/workbook.xml.rels' and tag == 'Relationship':
                            key = element.get('Id')
                            require(key and key not in relationships, ReasonCode.UNSUPPORTED_FORMAT)
                            target = element.get('Target', '')
                            relationships[key] = (target.lstrip('/') if target.startswith('/') else 'xl/' + target,
                                                  element.get('Type', ''))
                        if tag in ('row', 'col'):
                            require(element.get('hidden', '0') not in ('1', 'true') and
                                    float(element.get('ht' if tag == 'row' else 'width', '1')) > 0,
                                    ReasonCode.UNSUPPORTED_SCOPE)
                        if tag == 'sheetFormatPr':
                            require(element.get('zeroHeight', '0') not in ('1', 'true'), ReasonCode.UNSUPPORTED_SCOPE)
                        if sheet and tag == 'row':
                            number = int(element.get('r', '0'))
                            require(row_number < number <= limits.max_rows, ReasonCode.LIMIT_EXCEEDED)
                            row_number = number
                            max_row = number
                            columns = set()
                        if sheet and tag == 'c':
                            cell_type = element.get('t', 'n')
                            coordinate = element.get('r', '')
                            letters = coordinate.rstrip('0123456789')
                            digits = coordinate[len(letters):]
                            require(letters and digits and all('A' <= c <= 'Z' for c in letters),
                                    ReasonCode.INVALID_COORDINATE)
                            column = 0
                            for char in letters:
                                column = column * 26 + ord(char) - 64
                            require(int(digits) == row_number and column not in columns,
                                    ReasonCode.INVALID_COORDINATE)
                            require(0 < column <= limits.max_columns, ReasonCode.LIMIT_EXCEEDED)
                            columns.add(column)
                            max_column = max(max_column, column)
                            total_cells += 1
                            require(total_cells <= limits.max_cells and
                                    max_row * max_column <= limits.max_cells, ReasonCode.LIMIT_EXCEEDED)
                    else:
                        if element.text:
                            require(len(element.text) <= limits.max_text_chars, ReasonCode.LIMIT_EXCEEDED)
                        if sheet and tag == 'v':
                            require(cell_type is not None, ReasonCode.UNSUPPORTED_FORMAT)
                        if sheet and tag == 'v' and cell_type in ('n', 'b'):
                            value = element.text or ''
                            if cell_type == 'b':
                                require(value in ('0', '1'), ReasonCode.UNSUPPORTED_FORMAT)
                                value = 'true' if value == '1' else 'false'
                            raw_values[name][(row_number, column)] = value
                        if sheet and tag == 'c':
                            cell_type = None
                        element.clear()
        targets = []
        require(declared and len({title for title, _ in declared}) == len(declared), ReasonCode.UNSUPPORTED_SCOPE)
        for title, key in declared:
            require(key in relationships, ReasonCode.UNSUPPORTED_FORMAT)
            target, kind = relationships[key]
            require(target in raw_values and kind.endswith('/worksheet'), ReasonCode.UNSUPPORTED_FORMAT)
            targets.append((title, target))
        require(len({target for _, target in targets}) == len(targets) and
                {target for _, target in targets} == set(raw_values), ReasonCode.UNSUPPORTED_FORMAT)
        return targets, raw_values


class TableCodec:
    """An owner supplies asset identity; XLSX titles stay bound to the parsed hash.

    Values are source text, not formatted numeric displays. Serialization writes
    inert strings and requires a complete rectangular grid, including row 1.
    """
    def __init__(self, *, asset_version):
        reference(asset_version)
        self.asset_version = asset_version
        self.sheet_names = ()
        self.input_hash = None

    def parse(self, payload: BoundedPayload, limits: Limits):
        try:
            require(type(payload) is BoundedPayload and type(limits) is Limits, ReasonCode.INVALID_TYPE)
            require(payload.kind is PayloadKind.BINARY and payload.media_type in (MediaType.CSV, MediaType.XLSX),
                    ReasonCode.UNSUPPORTED_FORMAT)
            require(all(getattr(limits, k) <= getattr(payload.limits, k)
                        for k in limits.__dataclass_fields__ if k.startswith('max_')), ReasonCode.LIMIT_EXCEEDED)
            content = payload.binary
            require(0 < len(content) <= limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
            mime = magic.from_buffer(content, mime=True)
            if payload.media_type is MediaType.CSV:
                require(mime in ('text/plain', 'text/csv', 'application/csv'), ReasonCode.UNSUPPORTED_FORMAT)
                text = content.decode('utf-8-sig')
                require('\0' not in text, ReasonCode.UNSUPPORTED_FORMAT)
                tables = [('csv:0', 'CSV', csv.reader(io.StringIO(text, newline=''), strict=True), {})]
                workbook = None
            else:
                require(mime in ('application/zip', MediaType.XLSX.value), ReasonCode.UNSUPPORTED_FORMAT)
                targets, raw_values = preflight_xlsx(content, limits)
                workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
                tables = []
                for index, sheet in enumerate(workbook):
                    # Do not trust the dimension hint; the bounded XML scan checked actual coordinates.
                    sheet.reset_dimensions()
                    tables.append((f'xlsx:{index}', sheet.title, sheet.iter_rows(), raw_values[targets[index][1]]))
            columns, cells, names = [], [], []
            size = 0
            try:
                if workbook is not None:
                    require(workbook.sheetnames == [title for title, _ in targets], ReasonCode.UNSUPPORTED_SCOPE)
                require(0 < len(tables) <= limits.max_sheets, ReasonCode.LIMIT_EXCEEDED)
                for sheet_id, title, rows, original_values in tables:
                    names.append((sheet_id, title))
                    width = None
                    for row_number, row in enumerate(rows, 1):
                        require(row_number <= limits.max_rows, ReasonCode.LIMIT_EXCEEDED)
                        if workbook is None:
                            values = row
                        else:
                            require(all(c.data_type not in ('f', 'e', 'd') for c in row),
                                    ReasonCode.UNSUPPORTED_FORMAT)
                            values = [original_values.get((row_number, i), '' if c.value is None else str(c.value))
                                      for i, c in enumerate(row, 1)]
                        if width is None:
                            width = len(values)
                            require(0 < width <= limits.max_columns, ReasonCode.LIMIT_EXCEEDED)
                            require(all(values), ReasonCode.UNSUPPORTED_SCOPE)
                            columns.extend(TableColumn(schema_version=TableColumn.SCHEMA, sheet_id=sheet_id,
                                column_id=f'c{i}', source_index=i, label=value) for i, value in enumerate(values, 1))
                            size += sum(len(v.encode('utf-8')) for v in values)
                        if workbook is not None and len(values) < width:
                            values.extend([''] * (width - len(values)))
                        require(len(values) == width, ReasonCode.UNSUPPORTED_SCOPE)
                        require(len(cells) + width <= limits.max_cells, ReasonCode.LIMIT_EXCEEDED)
                        for index, value in enumerate(values, 1):
                            require(len(value) <= limits.max_text_chars, ReasonCode.LIMIT_EXCEEDED)
                            size += 2 * len(value.encode('utf-8'))
                            require(size <= limits.max_bytes, ReasonCode.LIMIT_EXCEEDED)
                            cells.append(TableCell(schema_version=TableCell.SCHEMA, sheet_id=sheet_id,
                                column_id=f'c{index}', source_row=row_number, logical_record=row_number,
                                original_text=value, normalized_text=value, mapping_proven=True,
                                source_spans=tuple((i, i + 1) for i in range(len(value)))))
                    require(width is not None, ReasonCode.UNSUPPORTED_SCOPE)
            finally:
                if workbook is not None:
                    workbook.close()
            input_hash = hashlib.sha256(content).hexdigest()
            result = TableSnapshot(schema_version=TableSnapshot.SCHEMA, asset_version=self.asset_version,
                input_hash=input_hash, media_type=payload.media_type, sheet_ids=tuple(s for s, _ in names),
                columns=tuple(columns), cells=tuple(cells), limits=limits,
                coordinate_version='source-codepoint-half-open.v1',
                coverage=Coverage(schema_version=Coverage.SCHEMA, unit=Unit.CELL, total=len(cells),
                    eligible=len(cells), processed=len(cells), excluded=0, failed=0, unknown=0, unscanned=0,
                    version=CODEC_VERSION))
            self.input_hash, self.sheet_names = input_hash, tuple(names)
            return result
        except ContractViolation as exc:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=exc.code,
                                   retryable=False, trace_id='tabular/parse')
        except (UnicodeError, csv.Error, zipfile.BadZipFile, DefusedXmlException, ParseError, ValueError,
                KeyError, IndexError, OSError, magic.MagicException):
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.UNSUPPORTED_FORMAT,
                                   retryable=False, trace_id='tabular/parse')

    def delivery_metadata(self, snapshot: TableSnapshot, limits: Limits):
        """Read the non-grid values retained by serialize; never certify arbitrary OOXML.

        The frozen serializer rebuilds properties/styles and copies only sheet
        titles outside the grid. No parser or serializer semantics change here.
        """
        try:
            require(snapshot.asset_version == self.asset_version and snapshot.input_hash == self.input_hash,
                    ReasonCode.HASH_MISMATCH)
            names = dict(self.sheet_names)
            require(all(s in names for s in snapshot.sheet_ids), ReasonCode.UNSUPPORTED_SCOPE)
            titles = [names[s] for s in snapshot.sheet_ids] if snapshot.media_type is MediaType.XLSX else []
            return BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.JSON,
                media_type=MediaType.JSON, text=None, binary=None, tree=FrozenJSON(titles), limits=limits)
        except ContractViolation as exc:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=exc.code,
                                   retryable=False, trace_id='tabular/delivery-metadata')

    def serialize(self, snapshot: TableSnapshot, limits: Limits):
        try:
            require(type(snapshot) is TableSnapshot and type(limits) is Limits, ReasonCode.INVALID_TYPE)
            require(all(getattr(limits, k) <= getattr(snapshot.limits, k)
                        for k in limits.__dataclass_fields__ if k.startswith('max_')), ReasonCode.LIMIT_EXCEEDED)
            snapshot = replace(snapshot, limits=limits)
            require(snapshot.asset_version == self.asset_version, ReasonCode.HASH_MISMATCH)
            coverage = snapshot.coverage
            require(coverage.failed == coverage.unknown == coverage.unscanned == coverage.excluded == 0 and
                    coverage.processed == len(snapshot.cells), ReasonCode.SCOPE_INCOMPLETE)
            csv_output = io.StringIO(newline='')
            writer = csv.writer(csv_output, lineterminator='\n')
            workbook = None
            if snapshot.media_type is MediaType.XLSX:
                require(snapshot.input_hash == self.input_hash, ReasonCode.HASH_MISMATCH)
                workbook = Workbook()
                workbook.remove(workbook.active)
            else:
                require(len(snapshot.sheet_ids) == 1, ReasonCode.UNSUPPORTED_SCOPE)
            for sheet_id in snapshot.sheet_ids:
                columns = [c for c in snapshot.columns if c.sheet_id == sheet_id]
                require(columns, ReasonCode.UNSUPPORTED_SCOPE)
                rows = {}
                for cell in snapshot.cells:
                    if cell.sheet_id == sheet_id:
                        rows.setdefault(cell.source_row, {})[cell.column_id] = cell.original_text
                require(rows and set(rows) == set(range(1, max(rows) + 1)), ReasonCode.UNSUPPORTED_SCOPE)
                target = workbook.create_sheet(dict(self.sheet_names)[sheet_id]) if workbook else None
                for number, values in sorted(rows.items()):
                    require(set(values) == {c.column_id for c in columns}, ReasonCode.SCOPE_INCOMPLETE)
                    output = [neutralize_formula(values[c.column_id]) for c in columns]
                    if number == 1:
                        require(len(set(output)) == len(output) and all(output), ReasonCode.UNSUPPORTED_SCOPE)
                    if target is not None:
                        require(all(len(v) <= 32767 for v in output), ReasonCode.LIMIT_EXCEEDED)
                        # Never let openpyxl's automatic formula inference execute text.
                        target.append(output)
                        for cell in target[target.max_row]:
                            cell.data_type = 's'
                    else:
                        writer.writerow(output)
            if workbook is not None:
                workbook.properties.created = workbook.properties.modified = datetime(2000, 1, 1)
                output = io.BytesIO()
                workbook.save(output)
                # Freeze ZIP metadata as well as workbook properties for byte-level goldens.
                fixed = io.BytesIO()
                with zipfile.ZipFile(output) as source, zipfile.ZipFile(fixed, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for name in sorted(source.namelist()):
                        info = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
                        # The canonical Linux baseline must also be stable on Windows.
                        info.create_system = 3
                        info.compress_type = zipfile.ZIP_DEFLATED
                        data = source.read(name)
                        if name == 'docProps/core.xml':
                            # openpyxl overwrites modified during save, after our assignment.
                            data = data.replace(workbook.properties.modified.isoformat(timespec='seconds').encode(),
                                                b'2000-01-01T00:00:00')
                        archive.writestr(info, data)
                binary = fixed.getvalue()
                preflight_xlsx(binary, limits)
            else:
                binary = csv_output.getvalue().encode('utf-8')
            return BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.BINARY,
                media_type=snapshot.media_type, text=None, tree=None, binary=binary, limits=limits)
        except ContractViolation as exc:
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=exc.code,
                                   retryable=False, trace_id='tabular/serialize')
        except (IllegalCharacterError, ValueError):
            return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.UNSUPPORTED_FORMAT,
                                   retryable=False, trace_id='tabular/serialize')
