=============================
MCP Server - Odoo for AI Apps
=============================

A Model Context Protocol (MCP) server inside Odoo 20 Community. AI apps that
speak MCP (Claude.ai, Claude Desktop, Claude Code, Cursor, VS Code, the MCP
Inspector and others) connect to Odoo with an OAuth sign-in or an MCP key of a
user and use the tools, resources and prompts of the AI engine (``om_ai``). The tools always run as the user who owns the key, with
the user's access rights and record rules, never as superuser.

Tools
=====

The MCP server offers the tool registry of the AI engine (*AI > Configuration >
Tools*), so a tool written once serves the AI Assistant in Discuss and the MCP
clients:

* find models, list fields, search, read, count and aggregate records
* current user, company and allowed companies
* list and read attachments (text as text, images as image content)
* create, update and delete records (several per call, up to a limit)
* post a note or a message in the chatter, attach a file
* server actions given to the AI as tools by an administrator

Each tool comes with its JSON schema and the MCP annotations (read only,
destructive). A tool can be hidden from MCP clients with *Available to MCP
Clients* on the tool.

Resources and prompts
=====================

* **Resources** (``resources/list``, ``resources/read``, resource templates):
  ``odoo://context`` (user, companies, time zone, today), ``odoo://models``
  (models open to MCP and what is allowed on each), ``odoo://model/{model}``
  (fields), ``odoo://record/{model}/{id}`` (the fields of a record, with its
  last change date), ``odoo://reports/{model}`` (printable reports),
  ``odoo://report/{report}/{ids}`` (the report as PDF) and
  ``odoo://attachment/{id}`` (a file of a record). Only models listed in the
  model permissions are offered, and the user's access rights, record rules
  and report groups apply.
* **Prompts** (``prompts/list``, ``prompts/get``): prompt templates of the AI
  engine with *Available to MCP* checked. Their ``{{ placeholders }}`` become
  the arguments the AI app asks for; AI apps often show them as slash
  commands. Two demo prompts are included.

Browser AI apps (OAuth 2.1)
===========================

Apps such as Claude.ai only need the endpoint URL. When they call it without
credentials, Odoo answers 401 with a pointer to its metadata, and the app signs
in with OAuth:

* Metadata: ``/.well-known/oauth-protected-resource`` (also ``/mcp`` after it)
  and ``/.well-known/oauth-authorization-server``.
* Dynamic client registration (``/mcp/oauth/register``), on by default; an
  option makes registered apps wait for an administrator's approval, and
  registration can be turned off (administrators then add the apps in
  *AI > MCP Server > OAuth Apps*). Public apps (PKCE only) and apps with a
  client secret (Basic or in the body) are supported.
* Authorization code flow with PKCE (S256 required) on ``/mcp/oauth/authorize``:
  the user signs in to Odoo and sees a consent page with the app, where the
  answer is sent, and a **Create and modify data** switch. Off (the default),
  the app gets a read-only token: write tools are hidden and refused.
* Redirect URIs are compared exactly (only the port of 127.0.0.1 may change),
  ``state`` is sent back with the issuer (``iss``), codes are single use and
  live two minutes; a code used twice ends what it gave.
* Tokens (``/mcp/oauth/token``) are bound to the user, the app and this MCP
  endpoint (resource indicators); access tokens expire after 60 minutes and
  refresh tokens rotate on each use (an old refresh token coming back ends the
  connection). Revocation on ``/mcp/oauth/revoke``. Only hashes of codes and
  tokens are stored.
* Users see and disconnect their apps in *AI > MCP Server > Connected Apps*;
  administrators see all of them. A cron removes expired tokens and
  connections.

Access
======

* **MCP User group**: only users in *MCP Server / MCP User* may connect.
* **MCP keys**: a user creates a key in *AI > MCP Server > Connect* (or in the
  preferences, scope *MCP*). The key only works on the MCP endpoint, not for
  the other APIs, and the usual key expiry rules apply. Keys of scope
  *MCP (read only)* only see the tools that do not change data; write tools
  are hidden and refused.
* **Model permissions** (*AI > MCP Server > Model Permissions*): the models MCP
  clients may use, each with Read, Create, Write (also chatter and
  attachments), Delete and Server Actions. Models that are not listed are not
  available. Tools that no permission allows are not offered.
* **Rate limit**: requests per key in a sliding window (120 per 60 seconds by
  default). Over the limit the server answers HTTP 429 with Retry-After.
* **Log**: every request is logged with the user, key, client, tool, model,
  duration, status and error, in its own transaction so failures are kept.
  Old logs and sessions are removed after the number of days you set.

Settings
========

*Settings > General Settings > AI > MCP Server*: turn the server on or off,
OAuth sign-in, app registration and approval, token and connection lifetimes,
rate limit and window, records per call, log retention, the browser origins
allowed to call the endpoint, and extra instructions sent to the AI apps.

Connect an app
==============

*AI > MCP Server > Connect* shows the endpoint (``https://<your Odoo>/mcp``)
and ready-to-paste settings. Apps with OAuth (Claude.ai custom connectors,
Claude Code with ``/mcp``) need only the URL. For the others (Claude Desktop
through the ``mcp-remote`` bridge, Cursor, VS Code, the MCP Inspector) the key
goes in an ``Authorization: Bearer <key>`` header. When the server hosts
several databases, add an ``X-Odoo-Database: <database>`` header (shown on the
page when needed).

Protocol
========

* Streamable HTTP transport on ``/mcp``: POST for JSON-RPC 2.0 messages, the
  answer as JSON, or as a server-sent event when the client accepts only
  ``text/event-stream``. Notifications get 202 Accepted. GET answers 405 (no
  server-initiated stream), DELETE ends the session.
* Lifecycle: ``initialize`` (version negotiation), ``notifications/initialized``,
  ``ping``, ``tools/list``, ``tools/call``, ``resources/list``,
  ``resources/templates/list``, ``resources/read``, ``prompts/list``,
  ``prompts/get``, with ``nextCursor`` pagination. Protocol versions 2025-11-25,
  2025-06-18, 2025-03-26 and 2024-11-05; JSON-RPC batches for 2025-03-26.
* ``Mcp-Session-Id`` is given at initialize and checked afterwards (unknown or
  ended sessions get 404). ``MCP-Protocol-Version`` is checked (400 when not
  supported). Requests from a browser origin that is not allowed get 403.
* Tool errors (access refused, validation) come back as tool results with
  ``isError``; protocol errors as JSON-RPC errors. Tracebacks are never sent.
* Results are text (JSON), with ``structuredContent`` for 2025-06-18 and later,
  and images for image attachments.

Limits
======

* The server answers requests only (GET answers 405): it cannot announce
  changes, so ``listChanged`` is false for tools, resources and prompts and
  resource subscriptions are not offered. Clients list again when needed.
* OAuth: client ID metadata documents are not supported (apps register or are
  added by an administrator). The OAuth pages need a database chosen by the
  host name or a database filter, as for the Odoo login page.
* Endpoints must be served over HTTPS in production, as OAuth requires.
* Tools added by other modules that change data without using the helpers of
  the tool registry are not covered by the model permissions; hide them from
  MCP clients if needed. The access rights of the user always apply.

Credits
=======

Odoo Mates, https://github.com/odoomates/odooapps
