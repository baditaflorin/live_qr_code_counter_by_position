# Deploying to your Proxmox VMs

Target setup:
- **Public IP:** `176.9.123.221`
- **Domain:** `live-qr.wemeshup.com` (TTL 300)
- **Nginx VM:** `10.10.10.10` — terminates TLS, reverse-proxies
- **App VM:** `10.10.10.20` — runs the dockerized backend
- **Image registry:** GHCR — auto-published on every push to `master` (see [docker.yml](../.github/workflows/docker.yml))

## 0. DNS + port forwarding (one-time, on you)

GitHub Actions can't manage your DNS or your gateway, so do these manually first:

1. **Create A record** at your DNS provider:
   ```
   live-qr.wemeshup.com  IN  A  176.9.123.221  TTL 300
   ```
   Verify: `dig +short live-qr.wemeshup.com` should return `176.9.123.221`.

2. **Forward ports** on your gateway / Proxmox host to the nginx VM:
   ```
   176.9.123.221:80   →  10.10.10.10:80
   176.9.123.221:443  →  10.10.10.10:443
   ```

## 1. Wait for the image to be published

Every push to `master` triggers the workflow at [.github/workflows/docker.yml](../.github/workflows/docker.yml). Watch it:

```bash
gh run watch          # from your laptop, in the repo directory
gh run list --limit 5 # last 5 runs
```

When it's green, the image is at:
```
ghcr.io/baditaflorin/live_qr_code_counter_by_position:latest
```

The package is **public** because the repo is public. No login needed to pull.

## 2. Set up the app VM (10.10.10.20)

SSH in, then:

```bash
# Install docker if it's not there yet
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# Drop the deploy compose file in place
sudo mkdir -p /opt/live-qr && cd /opt/live-qr
sudo curl -fsSL -o docker-compose.yml \
  https://raw.githubusercontent.com/baditaflorin/live_qr_code_counter_by_position/master/deploy/docker-compose.prod.yml

# Pull + run
sudo docker compose pull
sudo docker compose up -d

# Smoke-test: hit the app from the same VM
curl -s http://localhost:8000/api/system
# → {"dictionary":"DICT_4X4_250","dictionary_size":250,"data_dir":"/data"}
```

Persistent data lives in `/opt/live-qr/data/app.db`.

To update later:
```bash
cd /opt/live-qr
sudo docker compose pull && sudo docker compose up -d
```

If the app VM's firewall blocks 8000 from other LAN hosts, allow the nginx VM:
```bash
sudo ufw allow from 10.10.10.10 to any port 8000
```

## 3. Set up the nginx VM (10.10.10.10)

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx

# Drop the connection-upgrade map (needed for WebSocket)
sudo curl -fsSL -o /etc/nginx/conf.d/connection-upgrade.conf \
  https://raw.githubusercontent.com/baditaflorin/live_qr_code_counter_by_position/master/deploy/connection-upgrade.conf

# Drop the vhost
sudo curl -fsSL -o /etc/nginx/sites-available/live-qr.conf \
  https://raw.githubusercontent.com/baditaflorin/live_qr_code_counter_by_position/master/deploy/live-qr.conf

# IMPORTANT: the vhost references TLS files that don't exist yet — comment out
# the listen 443 server block before the first nginx reload, OR get the cert first
# with certbot's standalone mode. Easiest path: certbot --nginx will edit nginx
# for you, but for that the vhost must NOT yet have a 443 block.
#
# So first install a temporary HTTP-only vhost, get the cert, then swap in the full one.

cat <<'EOF' | sudo tee /etc/nginx/sites-available/live-qr-bootstrap.conf
server {
    listen 80;
    server_name live-qr.wemeshup.com;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'bootstrap'; add_header Content-Type text/plain; }
}
EOF

sudo mkdir -p /var/www/certbot
sudo ln -sf /etc/nginx/sites-available/live-qr-bootstrap.conf /etc/nginx/sites-enabled/live-qr.conf
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# Confirm DNS is reachable from the public internet:
# from another machine: curl http://live-qr.wemeshup.com  → "bootstrap"

# Get the cert (HTTP-01 via webroot)
sudo certbot certonly --webroot -w /var/www/certbot -d live-qr.wemeshup.com \
    --agree-tos -m baditaflorin@gmail.com --no-eff-email

# Swap in the production vhost
sudo ln -sf /etc/nginx/sites-available/live-qr.conf /etc/nginx/sites-enabled/live-qr.conf
sudo nginx -t && sudo systemctl reload nginx
```

Test from anywhere:
```bash
curl -I https://live-qr.wemeshup.com/
# → HTTP/2 200
```

Open in your browser: <https://live-qr.wemeshup.com/admin>

### Cert renewal

`certbot` adds a systemd timer automatically. Reload nginx after each renewal:
```bash
sudo systemctl edit certbot.service
# add:
# [Service]
# ExecStartPost=/bin/systemctl reload nginx
```

## 4. Point the live page at the right host

Once HTTPS is up, `location.host` inside the browser will already be `live-qr.wemeshup.com`, so:
- Phone-share QR codes auto-encode `https://live-qr.wemeshup.com/m/{id}` ✓
- WebSocket upgrades to `wss://live-qr.wemeshup.com/ws/detect` ✓
- Camera permission prompt works (HTTPS is required for `getUserMedia` from non-localhost) ✓

That last point is the reason TLS is non-optional: phones won't grant camera access over plain HTTP.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `502 Bad Gateway` on the domain | App VM down, or nginx can't reach `10.10.10.20:8000`. Check `curl http://10.10.10.20:8000/api/system` from the nginx VM. |
| Live page connects to `/ws/detect` then immediately disconnects | The `connection-upgrade.conf` map is missing or the `Connection`/`Upgrade` headers aren't being passed. `sudo nginx -T \| grep -A2 connection_upgrade`. |
| Cert renewal fails after success | Nginx isn't serving the ACME path through the proxy. Keep the `location /.well-known/acme-challenge/` block in the HTTP vhost. |
| Phones can't grant camera access | You're hitting an `http://` URL. `getUserMedia` requires HTTPS or `localhost`. |

## Quick reference

| Action | Command |
|---|---|
| Update the app | `cd /opt/live-qr && sudo docker compose pull && sudo docker compose up -d` |
| Rollback to a specific image tag | edit `docker-compose.yml`, set `:latest` to e.g. `:abc1234`, then `pull && up -d` |
| Tail app logs | `sudo docker compose -f /opt/live-qr/docker-compose.yml logs -f` |
| Reload nginx | `sudo nginx -t && sudo systemctl reload nginx` |
| Force cert renew | `sudo certbot renew --force-renewal && sudo systemctl reload nginx` |
