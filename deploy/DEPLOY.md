# Deploying to your Proxmox VMs

Target setup:
- **Bastion (public):** `0docker.com` → `176.9.123.221`
- **Domain:** `live-qr.wemeshup.com` (TTL 300)
- **Nginx VM (internal):** `10.10.10.10` — terminates TLS, reverse-proxies (reach via `ssh -J root@0docker.com root@10.10.10.10`)
- **App VM (internal):** `10.10.10.20` — runs the dockerized backend (reach via `ssh -J root@0docker.com root@10.10.10.20`)

No registry, no GitHub Actions. The app VM clones the repo and `docker compose up --build -d`.

## 0. DNS + port forwarding (one-time)

1. **A record:**
   ```
   live-qr.wemeshup.com  IN  A  176.9.123.221  TTL 300
   ```
   Verify from anywhere: `dig +short live-qr.wemeshup.com` → `176.9.123.221`.

2. **Forward ports** on `0docker.com` / Proxmox host to the nginx VM:
   ```
   176.9.123.221:80   →  10.10.10.10:80
   176.9.123.221:443  →  10.10.10.10:443
   ```

## 1. App VM (10.10.10.20)

```bash
ssh -J root@0docker.com root@10.10.10.20

# Docker (skip if already there)
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh

# Clone + run
mkdir -p /opt && cd /opt
git clone https://github.com/baditaflorin/live_qr_code_counter_by_position.git live-qr
cd live-qr
docker compose up --build -d

# Smoke-test
curl -s http://localhost:8000/api/system
# → {"dictionary":"DICT_4X4_100","dictionary_size":100,"data_dir":"/data"}
```

Persistent data lives in `/opt/live-qr/data/app.db`.

To switch to a larger marker dictionary later (more IDs, slightly harder detection at distance):
```bash
sed -i 's/DICT_4X4_100/DICT_4X4_250/' docker-compose.yml
docker compose up --build -d
```
(Existing marker IDs <100 keep working — dictionary IDs nest.)

To update after a `git push` from your laptop:
```bash
cd /opt/live-qr
git pull
docker compose up --build -d
```

If the app VM has a host firewall, allow nginx VM through:
```bash
ufw allow from 10.10.10.10 to any port 8000 || true
```

## 2. Nginx VM (10.10.10.10)

```bash
ssh -J root@0docker.com root@10.10.10.10

apt update
apt install -y nginx certbot python3-certbot-nginx git

# Pull just the nginx files (no need for the full repo here)
cd /tmp
curl -fsSL -o connection-upgrade.conf \
  https://raw.githubusercontent.com/baditaflorin/live_qr_code_counter_by_position/master/deploy/connection-upgrade.conf
curl -fsSL -o live-qr.conf \
  https://raw.githubusercontent.com/baditaflorin/live_qr_code_counter_by_position/master/deploy/live-qr.conf

mv connection-upgrade.conf /etc/nginx/conf.d/
mv live-qr.conf /etc/nginx/sites-available/

# Bootstrap vhost — HTTP only, lets certbot get the cert before we enable 443
cat > /etc/nginx/sites-available/live-qr-bootstrap.conf <<'EOF'
server {
    listen 80;
    server_name live-qr.wemeshup.com;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'bootstrap'; add_header Content-Type text/plain; }
}
EOF

mkdir -p /var/www/certbot
ln -sf /etc/nginx/sites-available/live-qr-bootstrap.conf /etc/nginx/sites-enabled/live-qr.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Confirm reachability from the public internet before asking certbot to challenge
# (from your laptop):  curl http://live-qr.wemeshup.com/   → "bootstrap"

# Get the cert
certbot certonly --webroot -w /var/www/certbot -d live-qr.wemeshup.com \
    --agree-tos -m baditaflorin@gmail.com --no-eff-email

# Swap in the production vhost
ln -sf /etc/nginx/sites-available/live-qr.conf /etc/nginx/sites-enabled/live-qr.conf
nginx -t && systemctl reload nginx
```

Verify from your laptop:
```bash
curl -I https://live-qr.wemeshup.com/        # → HTTP/2 200
```

Open: https://live-qr.wemeshup.com/admin

## 3. Why TLS isn't optional

Phones won't grant `getUserMedia` (camera) permission over plain HTTP from non-localhost origins. The whole live-counter flow only works on HTTPS.

Once HTTPS is up, the in-browser `location.host` is `live-qr.wemeshup.com`, so:
- Phone-share QR codes auto-encode `https://live-qr.wemeshup.com/m/{id}` ✓
- WebSockets upgrade to `wss://live-qr.wemeshup.com/ws/detect` ✓

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `502 Bad Gateway` on the domain | App VM down, or nginx can't reach `10.10.10.20:8000`. From the nginx VM: `curl http://10.10.10.20:8000/api/system`. |
| Live page connects to `/ws/detect` then disconnects | The `connection-upgrade.conf` map is missing or headers aren't being passed. `nginx -T \| grep -A2 connection_upgrade`. |
| Cert renewal fails | The `location /.well-known/acme-challenge/` block must stay reachable over plain HTTP. The vhost in this repo keeps it. |
| Camera permission denied on phones | Hitting `http://` instead of `https://`. |

## Quick reference

| Action | On VM | Command |
|---|---|---|
| Update app from latest master | app | `cd /opt/live-qr && git pull && docker compose up --build -d` |
| Tail app logs | app | `docker compose -f /opt/live-qr/docker-compose.yml logs -f` |
| Reload nginx | nginx | `nginx -t && systemctl reload nginx` |
| Force cert renew | nginx | `certbot renew --force-renewal && systemctl reload nginx` |
