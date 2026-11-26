=================================
AI Engine - Your Own AI Providers
=================================

One AI engine for Odoo 20 Community. You connect your own AI provider with
your own key, or a model server on your own machine. Nothing goes through
Odoo Mates and no key of ours is used. Other modules build their AI features
on this engine.

Providers
=========

* **OpenAI compatible APIs** (one adapter): OpenAI, Mistral, Groq, DeepSeek,
  xAI, OpenRouter, Together, Perplexity, or any other compatible endpoint.
* **Native adapters**: Anthropic Messages API, Google Gemini API, Azure OpenAI
  (the v1 API with a base URL ending in ``/openai/v1``, or the deployment
  routes with an API version).
* **Local model servers** (OpenAI compatible, no key): Ollama, LM Studio,
  vLLM, LocalAI, with their usual local addresses filled in.

Each provider has a base URL, an API key, extra headers, a timeout and a
number of retries. **Test Connection** asks the provider for its model list,
and **Fetch Models** adds the models it returns.

The API key is kept on the server. It is never sent to the browser: the
stored key cannot be read through any RPC call, administrators included. The
form only has a field to type in a new key.

Models and defaults
===================

* Models have capabilities (chat, vision, tools, JSON output, embeddings), a
  context size and prices per million tokens (editable) for cost estimates.
* For each company you set a default model per purpose: Chat, Fast, Vision,
  Embeddings. Features ask for a purpose, not a model. Fast and Vision fall
  back to the Chat model.

Python API
==========

.. code-block:: python

    result = self.env['om.ai']._ai_chat(
        [{'role': 'system', 'content': 'You write short replies.'},
         {'role': 'user', 'content': 'Thank the customer for the order.'}],
        purpose='fast', feature='my_feature')
    result['text']   # also: tool_calls, json, usage, model, provider

* ``_ai_chat(messages, purpose='chat', model=None, tools=None, json_schema=None,
  images=None, stream=False, feature=None, max_tokens=None, temperature=None,
  on_delta=None)``: the same message, tool call and usage format for every
  provider. ``json_schema`` returns the parsed answer in ``result['json']``.
  ``images`` adds pictures to the last user message. With ``stream=True``,
  ``on_delta(text)`` gets each piece as it arrives.
* ``_ai_embed(texts)``: one vector per text.
* ``_ai_run_agent(messages, tools=None, user=None, max_steps=6)``: lets the AI
  call tools until it answers. Tools run as the user, never as superuser,
  so access rights, record rules and field groups apply. Tools that are not
  read-only are not run: they come back in ``pending_actions``, and
  ``_ai_confirm_action`` runs one once the user confirms it.
* Busy (429) and failing (5xx) providers are retried with a growing pause.
  Errors are raised as a ``UserError`` with the provider's message.

Tools
=====

A registry of functions the AI may call (*AI > Configuration > Tools*). Each
tool has a code, a description, a JSON schema for its parameters, a read-only
flag, and optionally the models and groups it is limited to. The built-in
tools are read-only:

* find models, list the fields of a model
* search records with simple filters, read a record
* count records, grouped by a field if needed

To add a tool, a module adds an ``om.ai.tool`` record and a method
``_ai_tool_<name>(self, tool, **arguments)`` on ``om.ai.tool``.

Usage log and limits
====================

* Every call is logged: user, company, feature, provider, model, prompt and
  completion tokens, estimated cost, duration, status and error. Users see
  only their own usage; AI administrators see everyone's (graph, pivot and
  list).
* Daily limits per user and per company, in tokens or estimated cost, are
  checked before each call. A call over the limit is refused with a clear
  message and logged as blocked.
* Logging the text sent and the answers is a setting and is off by default.
* A daily cron removes logs older than the number of days you set.

Prompt templates
================

Reusable prompts per feature: a system prompt and a user message with
``{{ placeholders }}``. Placeholders are filled in as plain text and nothing
in a template is evaluated.

Built-in features
=================

* **Editor**: with *Use my provider for Odoo's built-in AI text features*
  on, the editor's text generation route uses your default chat model instead
  of Odoo's service. The contract does not change, so the callers of that
  route (the AI translation of the editor in debug mode, and the website
  configurator's text generation) use your provider too. The editor gets a
  **Write with AI** command (type ``/``): describe the text, refine it, then
  insert it.
* **AI Assistant in Discuss**: every AI user gets a chat with the AI
  Assistant (also under *AI > AI Assistant*). It answers with the read-only
  tools, so it only finds records the user is allowed to see. Answers are
  computed in the background with a typing indicator, so sending a message
  never waits for the AI. Limits apply, and errors are shown in the chat.

Security
========

* **AI / User**: uses the AI features and sees their own usage.
* **AI / Administrator**: providers, keys, models, tools, prompts, limits and
  the usage of all users. Settings administrators are AI administrators.

Configuration
=============

#. *AI > Configuration > Providers*: create a provider, pick the provider
   type, type the key (none for a local server), then click **Test
   Connection** and **Fetch Models**.
#. Check the capabilities and prices of the models.
#. *Settings > General Settings > AI*: set the default models, the limits and
   the privacy option.
#. Give users the *AI / User* access.

What was verified
=================

The adapters follow the providers' public API documentation:

* OpenAI Chat Completions: https://developers.openai.com/api/reference/resources/chat
* Anthropic Messages: https://platform.claude.com/docs/en/api/messages
* Google Gemini generateContent: https://aistudio.google.com/api-reference/generate-content
* Azure OpenAI v1 API: https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle

No real provider was called during development. Every flow was tested
against local mock servers that follow these formats:

* chat, streaming, tool calls, JSON output, images and embeddings for
  OpenAI compatible, Anthropic, Gemini and Azure OpenAI (both route styles)
* retries on 429, and errors from the provider
* the daily limits

Check the connection with your own provider and key before you rely on it.

Limits
======

* Website features that call Odoo's text service directly (theme
  suggestions, placeholder texts of the configurator) still use Odoo's
  service.
* Anthropic has no embeddings API: set an embeddings model of another
  provider.
* Costs are estimates from the prices you enter, in USD.

Provider names are trademarks of their owners and are used only to say which
APIs the module can connect to.

Credits
=======

Author: Odoo Mates
