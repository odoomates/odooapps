""" Stamping the values of the fields on the pages of a PDF.

The place of a field is given as fractions of its page as the browser shows it (pdf.js): the visible box of the page
(its crop box within its media box), turned by its rotation, from the top left corner. Each value is drawn upright as
the page is shown, whatever the rotation and the origin of the page.
"""
import io
import logging

from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from odoo.tools.misc import file_open
from odoo.tools.pdf import PdfFileReader, PdfFileWriter, RectangleObject

_logger = logging.getLogger(__name__)

FONT_FILE = 'web/static/fonts/sign/NotoSans-Reg.ttf'
FONT_NAME = 'SignNotoSans'
FALLBACK_FONT = 'Helvetica'
INK = (0.08, 0.12, 0.35)  # the colour of the values, a dark blue ink
PADDING = 0.08  # of the height of a box, around a text


def _font():
    """ :return: the font of the stamped texts, one covering most alphabets when Odoo has it """
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return FONT_NAME
    try:
        with file_open(FONT_FILE, 'rb') as font_file:
            pdfmetrics.registerFont(TTFont(FONT_NAME, io.BytesIO(font_file.read())))
        return FONT_NAME
    except (OSError, ValueError) as error:
        _logger.warning('Font %s not found, the signed texts use %s: %s', FONT_FILE, FALLBACK_FONT, error)
        return FALLBACK_FONT


def visible_box(page):
    """ :return: (left, bottom, right, top) of the part of `page` a viewer shows, as pdf.js does: the crop box
                 within the media box """
    media = [float(value) for value in page.mediabox]
    crop = [float(value) for value in page.cropbox]
    media = (min(media[0], media[2]), min(media[1], media[3]), max(media[0], media[2]), max(media[1], media[3]))
    crop = (min(crop[0], crop[2]), min(crop[1], crop[3]), max(crop[0], crop[2]), max(crop[1], crop[3]))
    box = (max(media[0], crop[0]), max(media[1], crop[1]), min(media[2], crop[2]), min(media[3], crop[3]))
    if box[2] <= box[0] or box[3] <= box[1]:
        return media
    return box


def page_rotation(page):
    return int(page.get('/Rotate', 0) or 0) % 360


def display_size(page):
    """ :return: (width, height) of `page` as shown, in points """
    left, bottom, right, top = visible_box(page)
    width, height = right - left, top - bottom
    return (height, width) if page_rotation(page) in (90, 270) else (width, height)


def display_matrix(page):
    """ :return: the matrix (a, b, c, d, e, f) from the coordinates of the page as shown (points from the top left
                 corner, y going down) to those of the PDF """
    left, bottom, right, top = visible_box(page)
    rotation = page_rotation(page)
    if rotation == 90:
        return (0, 1, 1, 0, left, bottom)
    if rotation == 180:
        return (-1, 0, 0, 1, right, bottom)
    if rotation == 270:
        return (0, -1, -1, 0, right, top)
    return (1, 0, 0, -1, left, top)


def _fit_text(text, font, width, height):
    """ :return: the font size showing `text` on one line in a box of `width` x `height` points """
    size = height * (1 - 2 * PADDING) / 1.2
    text_width = pdfmetrics.stringWidth(text, font, size)
    if text_width > width * 0.98 and text_width:
        size *= width * 0.98 / text_width
    return max(size, 1)


def _draw(pdf, item, width, height):
    """ Draw the value of `item` in its box of `width` x `height` points, its origin at the bottom left. """
    kind, value = item['kind'], item['value']
    if kind == 'image':
        pdf.drawImage(ImageReader(io.BytesIO(value)), 0, 0, width, height, mask='auto',
                      preserveAspectRatio=True, anchor='c')
    elif kind == 'check':
        if value:
            pdf.setLineWidth(max(min(width, height) / 9, 0.5))
            pdf.setLineCap(1)
            pdf.setLineJoin(1)
            path = pdf.beginPath()
            path.moveTo(width * 0.18, height * 0.52)
            path.lineTo(width * 0.42, height * 0.24)
            path.lineTo(width * 0.84, height * 0.80)
            pdf.drawPath(path, stroke=1, fill=0)
    else:
        text = ' '.join(str(value).split())
        font = _font()
        size = _fit_text(text, font, width, height)
        pdf.setFont(font, size)
        # the text sits on the middle of the box
        pdf.drawString(0, (height - size) / 2 + size * 0.22, text)


def _overlay(page, items):
    """ :return: a one-page PDF drawing `items` at their place on `page` """
    shown_width, shown_height = display_size(page)
    stream = io.BytesIO()
    left, bottom, right, top = visible_box(page)
    pdf = canvas.Canvas(stream, pagesize=(max(right, 1), max(top, 1)))
    pdf.setFillColorRGB(*INK)
    pdf.setStrokeColorRGB(*INK)
    for item in items:
        box_x, box_y = item['pos_x'] * shown_width, item['pos_y'] * shown_height
        box_width, box_height = item['width'] * shown_width, item['height'] * shown_height
        pdf.saveState()
        pdf.transform(*display_matrix(page))
        # from the shown page to the box, its origin at its bottom left and y going up
        pdf.transform(1, 0, 0, -1, box_x, box_y + box_height)
        _draw(pdf, item, box_width, box_height)
        pdf.restoreState()
    pdf.showPage()
    pdf.save()
    overlay = PdfFileReader(io.BytesIO(stream.getvalue()), strict=False).pages[0]
    # the merged content is clipped to the box of the overlay: the one of the page, wherever its origin is
    overlay.mediabox = RectangleObject([left, bottom, right, top])
    return overlay


def stamp_pdf(data, items):
    """ :param data: the bytes of a PDF
        :param items: what to draw, dicts of page (from 1), pos_x, pos_y, width, height (fractions of the page as
                      shown), kind (image, text or check) and value (bytes of an image, a text or a boolean)
        :return: the bytes of the PDF with the items drawn on its pages, its pages and their content kept """
    reader = PdfFileReader(io.BytesIO(data), strict=False)
    writer = PdfFileWriter()
    writer.append(reader)
    by_page = {}
    for item in items:
        by_page.setdefault(item['page'], []).append(item)
    for number, page_items in by_page.items():
        if not 1 <= number <= len(writer.pages):
            continue
        page = writer.pages[number - 1]
        page.merge_page(_overlay(page, page_items))
    with io.BytesIO() as stream:
        writer.write(stream)
        return stream.getvalue()
