=========================================
MCP Client - Outside Tools for AI Agents
=========================================

Connect Odoo 20 Community to MCP servers outside Odoo (Model Context
Protocol). Their tools are imported as tools of the AI engine (``om_ai``): the
AI Assistant in Discuss and the agents of other modules call them like the
built-in tools.

Servers
=======

*AI > Configuration > Outside MCP Servers*:

* **URL** of the MCP endpoint (Streamable HTTP), a **tool prefix** put before
  the name of each tool, a timeout and extra headers.
* **Authentication**: none, a **bearer token**, or an **OAuth sign-in**. With
  OAuth, *Sign In* finds the authorization server from the 401 of the MCP
  server (protected resource metadata), registers Odoo on it when the server
  allows it (or uses the client ID and secret you enter), and sends you
  through the authorization code flow with PKCE (S256), ``state`` and the
  resource indicator. Access tokens are refreshed on their own, with rotation
  respected even with several workers. *Sign Out* revokes the token.
* Tokens and secrets are kept on the server: the form only has fields to type
  new ones, and they cannot be read through RPC.
* **Allowed groups**: only users of these groups may use the tools of the
  server (empty: every AI user).

*Connect* opens a session (``initialize``), shows the server name, version,
protocol version and instructions, and imports the tools (``tools/list``,
with pagination).

Tools
=====

* Each outside tool becomes an AI tool named ``<prefix>_<tool name>`` with the
  description and JSON schema of the server. *Refresh Tools* updates them and
  removes the ones the server no longer has.
* **Enabled** and **Read Only** are set per tool by the administrator and kept
  when the tools are refreshed. Tools are imported as not read only: the
  agents ask the user to confirm before calling them. The server's own
  read-only and destructive hints are shown, not trusted.
* The AI Assistant in Discuss uses the enabled outside tools that are read
  only (with *AI Assistant Looks Up Records* on in the settings).
* Imported tools are not offered again to the AI apps connected to Odoo's own
  MCP server (*Available to MCP Clients* off) unless an administrator turns it
  on.

Calls
=====

* ``tools/call`` over Streamable HTTP; answers as JSON or as server-sent
  events. Event streams closed before the answer are resumed with GET and
  ``Last-Event-ID``; ping requests of the server are answered, other server
  requests are refused politely.
* An ended session (404) is opened again once; a 401 refreshes the OAuth token
  once.
* Text, embedded resources and links are given to the AI; images and audio are
  noted, not sent. Structured content is passed along.
* Every call is in the AI usage log (feature ``mcp_client``) with the user,
  server, tool, duration and result; the arguments and answer too when the
  company logs AI content.

Limits
======

* One set of credentials per server: the tools use the account that signed in
  (or the token), for every allowed user.
* Streamable HTTP only (the older HTTP+SSE transport and stdio servers are not
  supported). Resources and prompts of outside servers are not imported.
* Server notifications (list changed, progress) are read but not acted upon:
  use *Refresh Tools* after the server changes its tools.

Credits
=======

Odoo Mates, https://github.com/odoomates/odooapps
