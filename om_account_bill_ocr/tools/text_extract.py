""" The text of a bill: the text layer of a PDF when it has one, else the text read by Tesseract.

Everything runs on the server, with no external service: pdftotext (poppler-utils) keeps the layout of the
columns, pypdf is the fallback when it is not installed, and the scans and the photos are read by the
tesseract-ocr package, the pages of a scanned PDF turned into images by pdftoppm. """
import io
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader

_logger = logging.getLogger(__name__)

# a page with less text than this is a scan: its text layer, if any, is only a few stray characters
MIN_TEXT_PER_PAGE = 40
# the pages read: a bill is on the first ones, and reading a long scan takes time
MAX_PAGES = 5
TIMEOUT = 120
IMAGE_MIMETYPES = ('image/png', 'image/jpeg', 'image/jpg', 'image/tiff', 'image/bmp', 'image/gif', 'image/webp')


class OcrUnavailable(Exception):
    """ The bill is a scan or a photo, and Tesseract is not installed. """


def tesseract_available():
    return bool(shutil.which('tesseract'))


def _run(args, **kwargs):
    return subprocess.run(args, capture_output=True, timeout=TIMEOUT, check=True, **kwargs)


def _pdf_text_layer(raw):
    """ The text layer of a PDF, the columns kept in place. """
    if shutil.which('pdftotext'):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bill.pdf'
            path.write_bytes(raw)
            try:
                result = _run(['pdftotext', '-layout', '-l', str(MAX_PAGES), '-enc', 'UTF-8', str(path), '-'])
                return result.stdout.decode('utf-8', 'replace')
            except (subprocess.SubprocessError, OSError):
                _logger.info("pdftotext could not read the bill, falling back on pypdf", exc_info=True)
    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = reader.pages[:MAX_PAGES]
        return '\n\f'.join(page.extract_text(extraction_mode='layout') or '' for page in pages)
    except Exception:  # noqa: BLE001 any broken PDF is a bill without text
        _logger.info("pypdf could not read the bill", exc_info=True)
        return ''


def _page_count(raw):
    try:
        return len(PdfReader(io.BytesIO(raw)).pages)
    except Exception:  # noqa: BLE001
        return 1


def _ocr_image(path, languages):
    result = _run(['tesseract', str(path), 'stdout', '-l', languages, '--psm', '6',
                   '-c', 'preserve_interword_spaces=1'])
    return result.stdout.decode('utf-8', 'replace')


def _ocr_pdf(raw, languages):
    if not shutil.which('pdftoppm'):
        raise OcrUnavailable("pdftoppm")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'bill.pdf'
        path.write_bytes(raw)
        _run(['pdftoppm', '-r', '300', '-gray', '-png', '-l', str(MAX_PAGES), str(path), str(Path(tmp) / 'page')])
        pages = sorted(Path(tmp).glob('page*.png'))
        return '\n\f'.join(_ocr_image(page, languages) for page in pages)


def _ocr_raw_image(raw, languages):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'bill.img'
        path.write_bytes(raw)
        return _ocr_image(path, languages)


def is_image(mimetype, name=''):
    name = (name or '').lower()
    return (mimetype or '') in IMAGE_MIMETYPES or name.endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.webp'))


def extract_text(raw, mimetype, name='', languages='eng'):
    """ Return (text, source), source being 'text' for a text layer and 'ocr' for a scan or a photo.

    :raise OcrUnavailable: the file is a scan or a photo and Tesseract is not installed.
    """
    if is_image(mimetype, name):
        if not tesseract_available():
            raise OcrUnavailable("tesseract")
        return _ocr_raw_image(raw, languages), 'ocr'
    text = _pdf_text_layer(raw)
    pages = min(_page_count(raw), MAX_PAGES)
    if len(''.join(text.split())) >= MIN_TEXT_PER_PAGE * max(pages, 1) // 2:
        return text, 'text'
    if not tesseract_available():
        raise OcrUnavailable("tesseract")
    return _ocr_pdf(raw, languages), 'ocr'
