import base64
import io
import logging
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from markupsafe import Markup, escape
from PIL import Image
from pypdf import PdfReader

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MAX_PAGES = 5
MAX_IMAGE_PAGES = 3
MAX_TEXT_CHARS = 30000
MIN_TEXT_CHARS = 40
MAX_IMAGE_SIDE = 2000
MAX_IMAGE_PIXELS = 60_000_000
TIMEOUT = 120
IMAGE_MIMETYPES = ('image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif', 'image/tiff', 'image/bmp')
SYSTEM_PROMPT = """You read business documents for Odoo and return their data as one JSON object that follows the
schema. Copy names, numbers and references exactly as printed. Write dates as YYYY-MM-DD and amounts as plain numbers
with a dot for decimals. Use null for a value that is not on the document: never guess or invent one.
Set "confidence" between 0 and 1 for how sure you are of the whole reading, and list in "flags" short notes on
anything unclear, unreadable or inconsistent."""
CONFIDENCE_SCHEMA = {
    'confidence': {'type': 'number', 'description': 'How sure you are of the reading, 0 to 1'},
    'flags': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Unclear or inconsistent points'},
}


class OmAiExtract(models.AbstractModel):
    """Reads a document with the AI and returns the data checked against a JSON schema.

        data, problems = self.env['om.ai.extract']._extract(raw, 'application/pdf', 'bill.pdf', schema,
                                                             instructions='Read this vendor bill.')
    """
    _name = 'om.ai.extract'
    _description = 'AI Document Reading'

    # ------------------------------------------------------------------
    # The document
    # ------------------------------------------------------------------
    @staticmethod
    def _is_image(mimetype, name=''):
        name = (name or '').lower()
        return (mimetype or '') in IMAGE_MIMETYPES or name.endswith(
            ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.tif', '.tiff', '.bmp'))

    @staticmethod
    def _is_pdf(mimetype, name='', raw=b''):
        return mimetype == 'application/pdf' or (name or '').lower().endswith('.pdf') or raw[:5] == b'%PDF-'

    @api.model
    def _image_payload(self, raw):
        """The image as PNG or JPEG base64, at most MAX_IMAGE_SIDE pixels on its longer side."""
        raw = bytes(raw)
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise UserError(self.env._('This image is too large to be read.'))
                fmt = (image.format or '').upper()
                if fmt in ('PNG', 'JPEG') and max(image.size) <= MAX_IMAGE_SIDE:
                    return {'mime_type': 'image/%s' % fmt.lower(), 'data': base64.b64encode(raw).decode()}
                image = image.convert('RGB')
                image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
                buffer = io.BytesIO()
                image.save(buffer, format='JPEG', quality=88)
                return {'mime_type': 'image/jpeg', 'data': base64.b64encode(buffer.getvalue()).decode()}
        except (OSError, Image.DecompressionBombError) as error:
            raise UserError(self.env._('The image could not be opened: %s', error)) from None

    @api.model
    def _pdf_text(self, raw):
        if shutil.which('pdftotext'):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'document.pdf'
                path.write_bytes(raw)
                try:
                    result = subprocess.run(
                        ['pdftotext', '-layout', '-l', str(MAX_PAGES), '-enc', 'UTF-8', str(path), '-'],
                        capture_output=True, timeout=TIMEOUT, check=True)
                    return result.stdout.decode('utf-8', 'replace')
                except (subprocess.SubprocessError, OSError):
                    _logger.info('pdftotext could not read the document, using pypdf', exc_info=True)
        try:
            reader = PdfReader(io.BytesIO(raw))
            return '\n\f'.join(page.extract_text(extraction_mode='layout') or '' for page in reader.pages[:MAX_PAGES])
        except Exception:  # noqa: BLE001 - a broken PDF is a PDF without text
            _logger.info('pypdf could not read the document', exc_info=True)
            return ''

    @api.model
    def _pdf_images(self, raw):
        """The first pages of a scanned PDF as images, with pdftoppm (poppler-utils)."""
        if not shutil.which('pdftoppm'):
            raise UserError(self.env._(
                'This PDF is a scan without text. Install poppler-utils on the server to send its pages to a '
                'vision model, or upload a photo of the document.'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'document.pdf'
            path.write_bytes(raw)
            subprocess.run(['pdftoppm', '-scale-to', str(MAX_IMAGE_SIDE), '-jpeg', '-l', str(MAX_IMAGE_PAGES),
                            str(path), str(Path(tmp) / 'page')], capture_output=True, timeout=TIMEOUT, check=True)
            return [self._image_payload(page.read_bytes()) for page in sorted(Path(tmp).glob('page*.jpg'))]

    @api.model
    def _document_payload(self, raw, mimetype=None, name=''):
        """{'text': ..., 'images': [...], 'source': 'text' | 'image' | 'scan'} of a file."""
        raw = bytes(raw) if raw else b''
        if not raw:
            raise UserError(self.env._('The document is empty.'))
        if self._is_image(mimetype, name):
            return {'text': '', 'images': [self._image_payload(raw)], 'source': 'image'}
        if self._is_pdf(mimetype, name, raw):
            text = self._pdf_text(raw)
            if len(''.join(text.split())) >= MIN_TEXT_CHARS:
                return {'text': text[:MAX_TEXT_CHARS], 'images': [], 'source': 'text'}
            return {'text': '', 'images': self._pdf_images(raw), 'source': 'scan'}
        if (mimetype or '').startswith('text/') or (name or '').lower().endswith(('.txt', '.csv')):
            return {'text': raw.decode('utf-8', 'replace')[:MAX_TEXT_CHARS], 'images': [], 'source': 'text'}
        raise UserError(self.env._('Only PDFs, images and text files can be read.'))

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    @api.model
    def _schema(self, properties, required=None):
        """An object schema with the confidence and the flags added."""
        properties = dict(properties, **CONFIDENCE_SCHEMA)
        return {
            'type': 'object',
            'properties': properties,
            'required': list(dict.fromkeys((required or []) + ['confidence', 'flags'])),
            'additionalProperties': False,
        }

    @staticmethod
    def _number(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, str):
            return None
        text = re.sub(r'[^\d,.\-]', '', value.replace('−', '-'))
        if not re.search(r'\d', text):
            return None
        negative = text.startswith('-') or value.strip().startswith('(')
        text = text.lstrip('-')
        if ',' in text and '.' in text:
            text = text.replace(',', '') if text.rfind('.') > text.rfind(',') else text.replace('.', '').replace(',', '.')
        elif ',' in text:
            whole, _sep, decimals = text.rpartition(',')
            text = '%s.%s' % (whole.replace(',', ''), decimals) if len(decimals) in (1, 2) else text.replace(',', '')
        try:
            number = float(text)
        except ValueError:
            return None
        return -number if negative else number

    @staticmethod
    def _date(value):
        if not isinstance(value, str):
            return None
        match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', value)
        if not match:
            return None
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
        except ValueError:
            return None

    @api.model
    def _validate(self, schema, value, path='', problems=None):
        """Check ``value`` against the schema subset used here (object, array, string, number, integer,
        boolean, enum, format date) and return the cleaned value. Problems are appended to ``problems``."""
        problems = [] if problems is None else problems
        types = schema.get('type') or 'string'
        types = types if isinstance(types, list) else [types]
        if value is None:
            return None
        if 'object' in types:
            if not isinstance(value, dict):
                problems.append(self.env._('%s is not an object', path or 'answer'))
                return {}
            result = {}
            for key, sub in (schema.get('properties') or {}).items():
                sub_path = '%s.%s' % (path, key) if path else key
                if key not in value:
                    if key in (schema.get('required') or []) and 'null' not in (
                            sub.get('type') if isinstance(sub.get('type'), list) else [sub.get('type')]):
                        problems.append(self.env._('%s is missing', sub_path))
                    result[key] = None
                    continue
                result[key] = self._validate(sub, value[key], sub_path, problems)
            return result
        if 'array' in types:
            if not isinstance(value, list):
                problems.append(self.env._('%s is not a list', path))
                return []
            item_schema = schema.get('items') or {}
            return [self._validate(item_schema, item, '%s[%s]' % (path, index), problems)
                    for index, item in enumerate(value[:500])]
        if 'number' in types or 'integer' in types:
            number = self._number(value)
            if number is None:
                problems.append(self.env._('%(path)s is not a number: %(value)s', path=path, value=value))
                return None
            return int(round(number)) if 'integer' in types and 'number' not in types else number
        if 'boolean' in types:
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in ('true', 'yes', '1'):
                return True
            if text in ('false', 'no', '0'):
                return False
            problems.append(self.env._('%s is not true or false', path))
            return None
        text = str(value).strip() if not isinstance(value, (dict, list)) else ''
        if schema.get('format') == 'date':
            parsed = self._date(text)
            if text and not parsed:
                problems.append(self.env._('%(path)s is not a date: %(value)s', path=path, value=text))
            return parsed
        if schema.get('enum'):
            allowed = [item for item in schema['enum'] if item is not None]
            for item in allowed:
                if text.lower() == str(item).lower():
                    return item
            if text:
                problems.append(self.env._('%(path)s is not an allowed value: %(value)s', path=path, value=text))
            return None
        return text or None

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    @api.model
    def _extract(self, raw, mimetype, name, schema, instructions='', payload=None):
        """Read a document with the AI.

        :return: (data, problems, payload): the data checked against ``schema`` (with confidence and
                 flags), the problems found in the answer, and the document payload sent
        """
        payload = payload or self._document_payload(raw, mimetype, name)
        user_text = (instructions or '').strip()
        if payload['text']:
            user_text += '\n\nTEXT OF THE DOCUMENT:\n%s' % payload['text']
        else:
            user_text += '\n\nThe document is in the image(s).'
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': user_text}]
        purpose = 'vision' if payload['images'] else 'chat'
        # the document belongs to the user who reads it; the call is logged under that user and within the
        # limits of the AI settings
        answer = self.env['om.ai'].sudo()._ai_chat(
            messages, purpose=purpose, json_schema=schema, images=payload['images'] or None, feature='extract')
        if not isinstance(answer.get('json'), dict):
            raise UserError(self.env._('The AI did not answer with the expected data. Try again or check the '
                                       'model: it must support JSON output%s.',
                                       self.env._(' and images') if payload['images'] else ''))
        problems = []
        data = self._validate(schema, answer['json'], problems=problems)
        confidence = data.get('confidence')
        data['confidence'] = max(0.0, min(1.0, confidence)) if isinstance(confidence, float) else None
        data['flags'] = [flag for flag in (data.get('flags') or []) if flag]
        data['_model'] = answer.get('model')
        return data, problems, payload

    @api.model
    def _attachment_raw(self, attachment):
        attachment.ensure_one()
        return attachment.raw, attachment.mimetype, attachment.name

    @api.model
    def _summary_html(self, data, problems, extra_checks=None):
        """Chatter text with the confidence, the flags and the checks of a reading."""
        parts = [escape(self.env._('Read by the AI (%(model)s).', model=data.get('_model') or 'AI'))]
        if data.get('confidence') is not None:
            parts.append(escape(self.env._('Confidence: %s%%', round(data['confidence'] * 100))))
        notes = list(data.get('flags') or []) + list(problems or []) + list(extra_checks or [])
        if notes:
            parts.append(escape(self.env._('To check:')) + Markup('<ul>%s</ul>') % Markup('').join(
                Markup('<li>%s</li>') % note for note in notes))
        return Markup('<br/>').join(parts)
