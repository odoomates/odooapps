# WhatsApp Bridge

The WhatsApp Bridge of the Odoo module **WhatsApp Connector QR** (`om_whatsapp_device`). It keeps
the WhatsApp of each account linked, as a linked device (as WhatsApp Web is), and talks to Odoo:

- Odoo → bridge: an HTTP API on `127.0.0.1`, with the secret of the bridge (shown on the WhatsApp
  account in Odoo) in `Authorization: Bearer <secret>`.
- Bridge → Odoo: what comes from WhatsApp (messages, statuses, reactions, the state of a session),
  posted to `/om_whatsapp_device/webhook`, signed with the secret (`X-Signature-256`), with the database in
  `X-Odoo-Database`.

It runs on Node.js 20 or later, with [Baileys](https://github.com/WhiskeySockets/Baileys) (MIT).

## Install, once

On the server of Odoo:

```
sudo apt install nodejs npm        # Node.js 20 or later: node --version
cd /path/to/om_whatsapp_device/bridge
npm ci
```

## Run it

Pick one.

**From Odoo:** on the WhatsApp account, click **Start the Bridge** (administrators). Odoo starts it, and
starts it again when it finds it stopped (every 5 minutes). Its log and the keys of the linked devices
are in the data folder of Odoo, `om_whatsapp_bridge/`. Fine to try; a service of the server is sturdier.

**As a systemd service** (recommended): copy `om-whatsapp-bridge.service` to `/etc/systemd/system/`,
set its paths and user, put the secret shown on the account in a file only root reads, then start it:

```
echo 'OM_WA_SECRET=<the secret shown on the account>' | sudo tee /etc/om-whatsapp-bridge.env >/dev/null
sudo chmod 600 /etc/om-whatsapp-bridge.env
sudo systemctl daemon-reload
sudo systemctl enable --now om-whatsapp-bridge
journalctl -u om-whatsapp-bridge -f      # its log
```

**With Docker:**

```
docker build -t om-whatsapp-bridge .
docker run -d --name om-whatsapp-bridge --restart unless-stopped --network host \
    -e OM_WA_SECRET=<the secret shown on the account> -v om-whatsapp-bridge:/data om-whatsapp-bridge
```

`--network host`: the bridge listens on 127.0.0.1 and calls Odoo on 127.0.0.1.

## Configuration

| Variable | Default | |
|---|---|---|
| `OM_WA_SECRET` | (required) | the secret shown on the WhatsApp account in Odoo |
| `OM_WA_PORT` | `8077` | its port; the account says where the bridge is |
| `OM_WA_HOST` | `127.0.0.1` | keep it on this machine |
| `OM_WA_DATA` | `./data` | the keys of the linked devices: whoever has them uses the WhatsApp; keep them as passwords |

When Odoo listens on another address than `http://127.0.0.1:<http_port>`, set it in the system
parameter `om_whatsapp_device.odoo_url` of Odoo.

## Keep it working

WhatsApp changes its protocol a few times a year. When linking or sending stops working, update
Baileys (the version is pinned in `package.json`), test, and restart the bridge:

```
npm install @whiskeysockets/baileys@<version> --save-exact && npm test
```

## Tests

```
npm test
```

They run the bridge against a fake WhatsApp: no phone, no network.
