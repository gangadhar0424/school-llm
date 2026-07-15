# School LLM — Hostinger Deployment Runbook

Target topology:

```
┌──────────────────────────┐         ┌──────────────────────────┐
│   KVM 2 (8 GB · 2 vCPU)  │         │   KVM 4 (16 GB · 4 vCPU) │
│  ─────────────────────── │ private │  ─────────────────────── │
│   Nginx  443/80          │  net    │   Ollama  11434          │
│   Next.js  3000          │ ◄─────► │                          │
│   FastAPI  8000          │         │                          │
│   MongoDB  27017 (or     │         │                          │
│   Atlas)                 │         │                          │
└──────────────────────────┘         └──────────────────────────┘
            │
            │  https://llm.your-school.com
            ▼
        End users
```

Both boxes run **Ubuntu 22.04 LTS** in this guide. Adapt apt commands
if you picked Debian / Alma.

---

## 0. Before you start

- Domain pointed at KVM 2's public IP (A record for `llm.your-school.com`).
- SSH access to both KVM 2 and KVM 4 as a non-root user with sudo.
- Hostinger private network enabled between KVM 2 ↔ KVM 4 (both boxes
  should see each other on `10.x.x.x` or similar). If not available,
  use the public IPs + firewall the Ollama port to KVM 2 only.

---

## 1. KVM 4 — install Ollama (do this first)

SSH into KVM 4.

```bash
# 1.1 Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 1.2 Pre-pull the chat model. ~2 GB download.
ollama pull qwen2.5:3b
# Optional: also pull a slightly bigger model for testing quality
# ollama pull llama3.1:8b   # ~5 GB — only run if KVM 4 isn't already busy

# 1.3 Configure Ollama to listen on the private network
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null <<'EOF'
[Service]
Environment=OLLAMA_HOST=0.0.0.0:11434
Environment=OLLAMA_MAX_LOADED_MODELS=1
Environment=OLLAMA_KEEP_ALIVE=2h
Environment=OLLAMA_NUM_PARALLEL=1
Environment=OLLAMA_MAX_QUEUE=4
Environment=OLLAMA_ORIGINS=http://KVM2_PRIVATE_IP
EOF

# 1.4 Restart
sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo systemctl enable ollama

# 1.5 Firewall — only allow KVM 2's private IP to reach 11434
sudo ufw allow from KVM2_PRIVATE_IP to any port 11434
sudo ufw allow OpenSSH
sudo ufw enable

# 1.6 Smoke test
curl http://localhost:11434/api/tags
# Should return JSON listing the models you pulled.
```

From **KVM 2**, verify reachability:

```bash
curl http://KVM4_PRIVATE_IP:11434/api/tags
# Should return the same JSON.
```

---

## 2. KVM 2 — system setup

SSH into KVM 2.

```bash
# 2.1 Update + base packages
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
  nginx git python3.11 python3.11-venv python3-pip \
  espeak ffmpeg \
  curl ca-certificates

# 2.2 Install Node 20 LTS for Next.js
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# 2.3 Install MongoDB (skip this section if using Atlas)
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
  sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | \
  sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt update
sudo apt install -y mongodb-org
sudo systemctl enable --now mongod
# Optional: enable auth — see Mongo docs. For a single-box deployment
# bound to 127.0.0.1, the local-only default is acceptable for pilot.
```

---

## 3. KVM 2 — deploy the application

```bash
# 3.1 Clone
sudo mkdir -p /opt/school-llm
sudo chown $USER:$USER /opt/school-llm
cd /opt/school-llm
git clone https://github.com/YOUR/school-llm.git .
git checkout eskoolia-LLM   # or whatever the production branch is

# 3.2 Backend — Python venv + deps
cd /opt/school-llm/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
cd ..

# 3.3 Backend env
cp deploy/.env.kvm2.example .env
nano .env
# Fill in:
#   JWT_SECRET_KEY   (generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`)
#   MONGODB_URI      (Atlas connection string or mongodb://localhost:27017/school_llm)
#   OLLAMA_BASE_URL  (http://<KVM4 private IP>:11434)
#   CORS_ORIGINS     (https://llm.your-school.com)

# 3.4 Frontend — install + build
cd /opt/school-llm/frontend_next
cp ../deploy/.env.frontend.example .env.production
nano .env.production   # set BACKEND_URL=http://127.0.0.1:8000 + COOKIE_SECURE=1
npm ci
npm run build
cd ..
```

---

## 4. KVM 2 — systemd units

### 4.1 Backend (FastAPI)

```bash
sudo tee /etc/systemd/system/school-llm-api.service > /dev/null <<'EOF'
[Unit]
Description=School LLM FastAPI
After=network.target mongod.service
Wants=mongod.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/school-llm/backend
EnvironmentFile=/opt/school-llm/.env
ExecStart=/opt/school-llm/backend/.venv/bin/python main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

### 4.2 Frontend (Next.js)

```bash
sudo tee /etc/systemd/system/school-llm-web.service > /dev/null <<'EOF'
[Unit]
Description=School LLM Next.js
After=network.target school-llm-api.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/school-llm/frontend_next
Environment=NODE_ENV=production
EnvironmentFile=/opt/school-llm/frontend_next/.env.production
ExecStart=/usr/bin/npm run start
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

### 4.3 Enable + start

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now school-llm-api school-llm-web

# Check both are running
sudo systemctl status school-llm-api school-llm-web
sudo journalctl -u school-llm-api -n 50    # tail recent logs
```

If the API fails to start, the journal will show *exactly* which env
var is missing — that's the `validate_config()` hook doing its job.

---

## 5. KVM 2 — Nginx + HTTPS

```bash
sudo tee /etc/nginx/sites-available/school-llm > /dev/null <<'EOF'
server {
    listen 80;
    server_name llm.your-school.com;

    # Allow large PDF uploads (matches MAX_PDF_UPLOAD_MB).
    client_max_body_size 60M;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # WebSocket upgrade for /api/notifications/ws and /api/chat/ws.
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/school-llm /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# Get a Let's Encrypt cert
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d llm.your-school.com
# Auto-renew is installed as a systemd timer by default.
```

---

## 6. Smoke test

From your laptop:

```bash
# 1. DNS + HTTPS up
curl -I https://llm.your-school.com
# 2. FastAPI reachable (via nginx)
curl https://llm.your-school.com/api/health
# 3. Login should redirect to the eSkoolia flow (if AUTH_PROVIDER=eskoolia)
#    or show the login page (AUTH_PROVIDER=local).
open https://llm.your-school.com
```

A real-user smoke test:

1. Log in as a teacher.
2. Upload a small PDF (< 5 MB).
3. Generate one short-answer question (uses Ollama → KVM 4).
4. Watch logs while it runs:
   ```bash
   sudo journalctl -u school-llm-api -f       # KVM 2
   sudo journalctl -u ollama -f               # KVM 4
   ```
   You should see the FastAPI log a request, then Ollama on KVM 4
   stream a response back.

---

## 7. Day-2 ops — common commands

```bash
# Restart after a code update
cd /opt/school-llm
git pull
sudo systemctl restart school-llm-api
# Rebuild frontend only if frontend_next/ changed
cd frontend_next && npm run build && cd ..
sudo systemctl restart school-llm-web

# View logs
sudo journalctl -u school-llm-api -n 200 --no-pager
sudo journalctl -u school-llm-web -n 200 --no-pager
sudo journalctl -u ollama -n 200 --no-pager     # on KVM 4

# Quick memory check
free -h

# Mongo backup (if self-hosted on KVM 2)
mongodump --uri="mongodb://localhost:27017/school_llm" --out=/var/backups/mongo-$(date +%F)
```

---

## 8. Known limits

These are constraints of the architecture, not bugs:

| | Limit | Why |
|---|---|---|
| Concurrent PDF uploads | ~2 at a time | Single FastAPI box, sync PDF parse — wrapped in to_thread so other endpoints stay responsive, but PDF throughput is capped by 2 vCPU. |
| Ollama call latency | 5–15 s for short answers (CPU 3B model) | CPU inference. To speed up, get a GPU host for Ollama. |
| Total RAM headroom | ~1 GB on KVM 2 | Nginx + Next.js + FastAPI + Mongo eat the rest. Monitor with `free -h`; add swap if you start seeing OOM kills. |
| Active users (steady) | 5–10 | Tested target. Beyond that, queue times start to feel slow. |

When you outgrow this, the next step is:
- Move MongoDB to Atlas (frees ~1.5 GB on KVM 2)
- Move Next.js to Vercel free tier (frees ~1 GB on KVM 2)
- Upgrade KVM 4 to a GPU host (10–50× faster inference)
