#!/usr/bin/env python3
"""Build the user guide PDF that ships in static/description.

    python3 doc/build_user_guide.py

Reads user_guide.html, points the @font-face rules at the Lato fonts of the Odoo
source tree, renders with wkhtmltopdf and writes the metadata with pypdf.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / 'user_guide.html'
TARGET = HERE.parent / 'static' / 'description' / 'user_guide.pdf'

TITLE = 'Odoo 19 Accounting for Community Edition - User Guide'
SUBJECT = 'User guide for the Odoo Mates accounting suite on Odoo 19'
AUTHOR = 'Odoo Mates'

# Lato is the font Odoo itself uses; it is not usually installed system-wide, so it
# is read from the Odoo source tree. Pass the path as the first argument when odoo
# does not sit next to this repository.
FONTS = {
    'LATO_REGULAR': 'Lato-Reg-webfont.ttf',
    'LATO_BOLD': 'Lato-Bol-webfont.ttf',
    'LATO_BLACK': 'Lato-Bla-webfont.ttf',
}

FOOTER = """<!DOCTYPE html>
<html><head><meta charset="utf-8"/><style>
  body { margin: 0; font-family: 'Lato', sans-serif; font-size: 8pt; color: #8A8A9E; }
  .bar { padding: 0 16mm; }
  .page { float: right; color: #5B34D6; font-weight: 700; }
</style></head>
<body>
  <div class="bar"><span class="page" id="page"></span>
  <span>Odoo 19 Accounting for Community Edition &nbsp;&middot;&nbsp; User Guide</span></div>
  <script>
    // old WebKit: no URLSearchParams
    var page = 0, parts = location.search.substring(1).split('&');
    for (var i = 0; i < parts.length; i++) {
        var pair = parts[i].split('=');
        if (pair[0] === 'page') { page = parseInt(pair[1], 10); }
    }
    document.getElementById('page').innerHTML = page;
  </script>
</body></html>
"""


def font_directory(argv):
    if len(argv) > 1:
        return pathlib.Path(argv[1])
    for candidate in (HERE.parents[3] / 'odoo', pathlib.Path.home() / 'odoo' / '19.0' / 'odoo' / 'odoo'):
        fonts = candidate / 'addons' / 'web' / 'static' / 'fonts' / 'lato'
        if fonts.is_dir():
            return fonts
    raise SystemExit('Lato fonts not found; pass the path to addons/web/static/fonts/lato')


def split(html):
    """The cover and the body are rendered apart: the cover has to bleed to the edge
    of the paper, which means a page with no margins at all."""
    head = html[:html.index('<div class="cover">')]
    cover_end = html.index('<!-- ==', html.index('<div class="cover">'))
    return (head + html[html.index('<div class="cover">'):cover_end] + '</body></html>',
            head + html[cover_end:])


def render(source, output, margins, footer=None, shrink=True):
    command = ['wkhtmltopdf', '--enable-local-file-access', '--page-size', 'A4',
               '--javascript-delay', '250']
    if not shrink:
        # the cover is sized in millimetres and has to land on the paper exactly
        command += ['--disable-smart-shrinking']
    for edge, value in margins.items():
        command += ['--margin-%s' % edge, value]
    if footer:
        command += ['--footer-html', str(footer), '--footer-spacing', '6']
    command += [str(source), str(output)]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)


def main(argv):
    fonts = font_directory(argv)
    html = SOURCE.read_text()
    for placeholder, name in FONTS.items():
        font = fonts / name
        if not font.is_file():
            raise SystemExit('missing font: %s' % font)
        html = html.replace(placeholder, 'file://%s' % font)

    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        shutil.copytree(HERE / 'img', work / 'img')
        cover_html, body_html = split(html)
        (work / 'cover.html').write_text(cover_html)
        (work / 'body.html').write_text(body_html)
        (work / 'footer.html').write_text(FOOTER)

        render(work / 'cover.html', work / 'cover.pdf',
               {'top': '0', 'bottom': '0', 'left': '0', 'right': '0'}, shrink=False)
        render(work / 'body.html', work / 'body.pdf',
               {'top': '16mm', 'bottom': '18mm', 'left': '16mm', 'right': '16mm'},
               footer=work / 'footer.html')

        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        for part in ('cover.pdf', 'body.pdf'):
            writer.append_pages_from_reader(PdfReader(str(work / part)))
        writer.add_metadata({'/Title': TITLE, '/Subject': SUBJECT, '/Author': AUTHOR})
        with open(TARGET, 'wb') as handle:
            writer.write(handle)
        print('%s written, %d pages' % (TARGET, len(writer.pages)))


if __name__ == '__main__':
    main(sys.argv)
