import logging
import math
import re

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

CHUNK_CHARS = 1200
MAX_PRODUCTS = 2000
EMBED_BATCH = 32
MAX_EMBEDDED_CHUNKS = 5000
WORD_RE = re.compile(r'\w{3,}', re.UNICODE)
# frequent words of questions that say nothing about the subject
STOP_WORDS = set('''
the and for are but not you your yours our ours can could would should will what when where which who whom why how
does did done doing have has had having this that these those there here from with about into onto over under
any all some much many more most very just also please want need like tell know thanks thank hello hi hey yes
les des une est que qui pour pas sur avec dans vous nous votre notre der die das und ist nicht mit sie wir ihr
los las una por con para que del como est
'''.split())


class OmAiLivechatSource(models.Model):
    """Knowledge the live chat agent answers from."""
    _name = 'om.ai.livechat.source'
    _description = 'AI Live Chat Knowledge Source'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company')
    source_type = fields.Selection(selection='_selection_source_type', string='Type', required=True, default='text')
    content = fields.Html(string='Text', sanitize_style=True)
    faq_ids = fields.One2many('om.ai.livechat.faq', 'source_id', string='Questions and Answers', copy=True)
    page_ids = fields.Many2many('website.page', string='Website Pages')
    product_domain = fields.Char(string='Products', default="[('sale_ok', '=', True)]",
                                 help='The products whose descriptions the agent reads. Prices and stock are '
                                      'always looked up live, never taken from this text.')
    chunk_ids = fields.One2many('om.ai.livechat.chunk', 'source_id', string='Indexed Parts')
    chunk_count = fields.Integer(string='Parts', compute='_compute_chunk_count')
    indexed_date = fields.Datetime(string='Indexed On', readonly=True, copy=False)
    agent_ids = fields.Many2many('om.ai.livechat.agent', 'om_ai_livechat_agent_source_rel', 'source_id', 'agent_id',
                                 string='Agents')

    @api.model
    def _selection_source_type(self):
        selection = [('text', 'Text'), ('faq', 'FAQ'), ('page', 'Website Pages')]
        if 'product.template' in self.env:
            selection.append(('product', 'Products'))
        return selection

    def _compute_chunk_count(self):
        data = dict(self.env['om.ai.livechat.chunk']._read_group(
            [('source_id', 'in', self.ids)], ['source_id'], ['__count']))
        for source in self:
            source.chunk_count = data.get(source, 0)

    @api.model_create_multi
    def create(self, vals_list):
        sources = super().create(vals_list)
        sources._index()
        return sources

    def write(self, vals):
        res = super().write(vals)
        if {'content', 'faq_ids', 'page_ids', 'product_domain', 'source_type', 'name'} & set(vals):
            self._index()
        return res

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    @staticmethod
    def _split(text, size=CHUNK_CHARS):
        """Cut a text into parts of about ``size`` characters, on paragraph limits when possible."""
        parts, current = [], ''
        for paragraph in re.split(r'\n\s*\n', text or ''):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            while len(paragraph) > size:
                cut = paragraph.rfind(' ', 0, size)
                cut = cut if cut > size // 2 else size
                parts.append(paragraph[:cut].strip())
                paragraph = paragraph[cut:].strip()
            if current and len(current) + len(paragraph) + 2 > size:
                parts.append(current)
                current = paragraph
            else:
                current = '%s\n\n%s' % (current, paragraph) if current else paragraph
        if current:
            parts.append(current)
        return parts

    def _get_chunks(self):
        """List of {'name', 'content', 'res_model', 'res_id'} of the source."""
        self.ensure_one()
        chunks = []
        if self.source_type == 'text':
            for part in self._split(html2plaintext(self.content or '')):
                chunks.append({'name': self.name, 'content': part})
        elif self.source_type == 'faq':
            for faq in self.faq_ids:
                chunks.append({'name': faq.question, 'content': 'Q: %s\nA: %s' % (faq.question, faq.answer)})
        elif self.source_type == 'page':
            for page in self.page_ids.sudo():
                text = html2plaintext(page.view_id.arch_db or '')
                text = re.sub(r'\n{3,}', '\n\n', text)
                for part in self._split(text):
                    chunks.append({'name': page.name, 'content': part, 'res_model': 'website.page',
                                   'res_id': page.id})
        elif self.source_type == 'product' and 'product.template' in self.env:
            domain = safe_eval(self.product_domain or '[]')
            Product = self.env['product.template'].sudo()
            if 'is_published' in Product._fields:
                domain = domain + [('is_published', '=', True)]
            for product in Product.search(domain, limit=MAX_PRODUCTS):
                lines = [product.display_name]
                if product.categ_id:
                    lines.append('Category: %s' % product.categ_id.display_name)
                if product.description_sale:
                    lines.append(product.description_sale)
                if 'description_ecommerce' in product._fields and product.description_ecommerce:
                    lines.append(html2plaintext(product.description_ecommerce))
                chunks.append({'name': product.display_name, 'content': '\n'.join(lines)[:CHUNK_CHARS * 2],
                               'res_model': 'product.template', 'res_id': product.id})
        return chunks

    def _index(self):
        Chunk = self.env['om.ai.livechat.chunk'].sudo()
        for source in self:
            source.chunk_ids.sudo().unlink()
            values = [dict(chunk, source_id=source.id) for chunk in source._get_chunks() if chunk['content']]
            Chunk.create(values)
            source.sudo().indexed_date = fields.Datetime.now()
        agents = self.agent_ids.filtered('use_embeddings')
        if agents:
            self.chunk_ids._embed()

    def action_index(self):
        self._index()
        return True

    @api.model
    def _cron_index(self):
        """Read the website pages and the products again: they change without the source knowing."""
        self.search([('source_type', 'in', ('page', 'product'))])._index()


class OmAiLivechatFaq(models.Model):
    _name = 'om.ai.livechat.faq'
    _description = 'AI Live Chat Question and Answer'
    _order = 'sequence, id'

    source_id = fields.Many2one('om.ai.livechat.source', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    question = fields.Char(required=True, translate=True)
    answer = fields.Text(required=True, translate=True)

    @api.model_create_multi
    def create(self, vals_list):
        faqs = super().create(vals_list)
        faqs.source_id._index()
        return faqs

    def write(self, vals):
        res = super().write(vals)
        self.source_id._index()
        return res

    def unlink(self):
        sources = self.source_id
        res = super().unlink()
        sources.exists()._index()
        return res


class OmAiLivechatChunk(models.Model):
    """A part of a knowledge source, found by full-text search or by embeddings."""
    _name = 'om.ai.livechat.chunk'
    _description = 'AI Live Chat Knowledge Part'
    _order = 'source_id, id'

    source_id = fields.Many2one('om.ai.livechat.source', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Title')
    content = fields.Text(required=True)
    res_model = fields.Char(string='Model')
    res_id = fields.Integer(string='Record ID')
    embedding = fields.Json()

    _content_fts = models.Index("USING gin (to_tsvector('simple', coalesce(name, '') || ' ' || content))")

    def _embed(self):
        chunks = self.filtered(lambda c: not c.embedding)[:MAX_EMBEDDED_CHUNKS]
        engine = self.env['om.ai'].sudo()
        for start in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[start:start + EMBED_BATCH]
            try:
                vectors = engine._ai_embed(['%s\n%s' % (c.name or '', c.content) for c in batch],
                                           feature='livechat')
            except UserError as error:
                _logger.info('Live chat knowledge not embedded: %s', error)
                return
            for chunk, vector in zip(batch, vectors):
                chunk.embedding = vector

    @api.model
    def _fts_query(self, text):
        words = list(dict.fromkeys(word.lower() for word in WORD_RE.findall(text or '')
                                   if word.lower() not in STOP_WORDS))[:20]
        return ' | '.join('%s:*' % word.replace("'", '') for word in words)

    @api.model
    def _search_text(self, sources, text, limit=5):
        """The parts of ``sources`` matching ``text`` best, by Postgres full-text search."""
        query = self._fts_query(text)
        if not query or not sources:
            return self.browse()
        self.env['om.ai.livechat.chunk'].flush_model()
        self.env.cr.execute("""
            SELECT id, ts_rank_cd(to_tsvector('simple', coalesce(name, '') || ' ' || content),
                                  to_tsquery('simple', %s)) AS rank
              FROM om_ai_livechat_chunk
             WHERE source_id IN %s
               AND to_tsvector('simple', coalesce(name, '') || ' ' || content) @@ to_tsquery('simple', %s)
          ORDER BY rank DESC, id
             LIMIT %s
        """, [query, tuple(sources.ids), query, limit])
        return self.browse([row[0] for row in self.env.cr.fetchall()])

    @api.model
    def _search_embedding(self, sources, text, limit=5):
        """The parts of ``sources`` closest to ``text`` by cosine similarity of embeddings."""
        chunks = self.sudo().search([('source_id', 'in', sources.ids), ('embedding', '!=', False)],
                                    limit=MAX_EMBEDDED_CHUNKS)
        if not chunks:
            return self.browse()
        vector = self.env['om.ai'].sudo()._ai_embed(text, feature='livechat')

        def cosine(other):
            if not other or len(other) != len(vector):
                return -1
            dot = sum(a * b for a, b in zip(vector, other))
            norm = math.sqrt(sum(a * a for a in vector)) * math.sqrt(sum(b * b for b in other))
            return dot / norm if norm else -1
        scored = sorted(((cosine(chunk.embedding), chunk.id) for chunk in chunks), reverse=True)[:limit]
        return self.browse([chunk_id for score, chunk_id in scored if score > 0])
