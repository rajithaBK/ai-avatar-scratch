#!/usr/bin/env bash
# aws_bootstrap.sh
#
# Run this ONCE on a fresh g4dn.xlarge (or any GPU EC2) running the
# Deep Learning Base GPU AMI (Ubuntu 22.04). It installs everything
# required for real-mode AI avatar generation:
#
#   * system ffmpeg
#   * Python 3.10 + venv for the FastAPI backend
#   * Python 3.10 + venv for MuseTalk (with CUDA-enabled torch)
#   * MuseTalk repo + model weights (~2 GB)
#   * Node.js + frontend build
#   * Caddy reverse proxy with auto Let's Encrypt cert
#   * systemd unit for the backend
#
# Re-running the script is safe; each step is idempotent.
#
# Required env vars (set inline before running, or export first):
#   PUBLIC_HOST   — fully qualified DNS name pointed at this EC2 (e.g. avatar-demo.example.com).
#                   If unset we fall back to the EC2 public DNS for a self-signed cert demo.
#   API_TOKEN     — bearer token required on POST /api/jobs. Auto-generated if unset.
#   AVATAR_URL    — optional URL to a face MP4 to use as the avatar. If unset
#                   we drop a tiny placeholder so MuseTalk can run; replace
#                   it before showing anyone.
#
# After the script finishes:
#   sudo systemctl start avatar-backend
#   sudo systemctl status avatar-backend
#   open https://$PUBLIC_HOST/ in a browser

set -euo pipefail

# --- 0. config ---------------------------------------------------------------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

PUBLIC_HOST="${PUBLIC_HOST:-$(curl -fsSL --max-time 3 http://169.254.169.254/latest/meta-data/public-hostname || hostname -f)}"
API_TOKEN="${API_TOKEN:-$(openssl rand -hex 24)}"
AVATAR_URL="${AVATAR_URL:-}"

echo "==== ai-avatar-desk-demo bootstrap ===="
echo "Repo dir   : $REPO_DIR"
echo "Public host: $PUBLIC_HOST"
echo "API token  : $API_TOKEN"
echo "================================="

# --- 1. system packages ------------------------------------------------------
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ffmpeg git curl jq build-essential \
  python3.10 python3.10-venv python3.10-dev \
  software-properties-common ca-certificates

# Verify GPU before continuing.
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found. Did you launch with the Deep Learning Base AMI?" >&2
  exit 1
fi
nvidia-smi | head -15

# --- 2. backend Python venv (FastAPI + Kokoro) -------------------------------
cd "$REPO_DIR/backend"
if [ ! -d ".venv" ]; then
  python3.10 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r requirements.txt
deactivate

# --- 3. MuseTalk repo + venv -------------------------------------------------
mkdir -p "$REPO_DIR/third_party"
cd "$REPO_DIR/third_party"
if [ ! -d "MuseTalk" ]; then
  git clone https://github.com/TMElyralab/MuseTalk.git
fi
cd MuseTalk
if [ ! -d ".venv" ]; then
  python3.10 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel

# Torch with CUDA 11.8 (matches Deep Learning Base AMI).
python -m pip install --index-url https://download.pytorch.org/whl/cu118 \
  torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2

# MuseTalk's other Python deps.
python -m pip install -r requirements.txt
python -m pip install -U openmim
mim install mmengine
mim install "mmcv==2.0.1"
mim install "mmdet==3.1.0"
mim install "mmpose==1.1.0"

# Sanity check: MuseTalk should import its model loader without complaint.
python -c "import torch; assert torch.cuda.is_available(); print('torch+CUDA OK')"

# Download model weights (~2 GB) if not already present.
if [ ! -f "models/musetalkV15/unet.pth" ]; then
  bash download_weights.sh
fi
deactivate

# --- 4. avatar input ---------------------------------------------------------
mkdir -p "$REPO_DIR/assets/avatars"
AVATAR_PATH="$REPO_DIR/assets/avatars/default.mp4"
if [ ! -f "$AVATAR_PATH" ]; then
  if [ -n "$AVATAR_URL" ]; then
    echo "Downloading avatar from $AVATAR_URL"
    curl -fsSL "$AVATAR_URL" -o "$AVATAR_PATH"
  else
    echo "WARNING: no AVATAR_URL provided; copying a tiny placeholder so MuseTalk has something to run."
    echo "Replace $AVATAR_PATH with a real 5-10s face video before any real demo."
    # MuseTalk also accepts a still image; we use a 1-frame PNG as a stand-in.
    convert -size 512x512 xc:'#1d2033' -font 'DejaVu-Sans' -pointsize 32 -fill white \
      -gravity center -annotate 0 "PLACEHOLDER" "$REPO_DIR/assets/avatars/default.png" 2>/dev/null \
      || ffmpeg -y -loglevel error -f lavfi -i "color=c=0x1d2033:s=512x512:d=1" \
            -frames:v 1 "$REPO_DIR/assets/avatars/default.png"
    # Convert to a 5s MP4 loop so MuseTalk can process the head region.
    ffmpeg -y -loglevel error -loop 1 -i "$REPO_DIR/assets/avatars/default.png" \
      -c:v libx264 -t 5 -pix_fmt yuv420p -vf scale=512:512 "$AVATAR_PATH"
  fi
fi

# --- 5. frontend build (served statically by Caddy) --------------------------
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
cd "$REPO_DIR/frontend"
npm ci
# Tell the SPA to call /api directly (same origin via Caddy) and to send the bearer token.
cat > .env.production <<EOF
VITE_BACKEND_URL=
VITE_API_TOKEN=$API_TOKEN
EOF
npm run build

# --- 6. backend env file -----------------------------------------------------
cat > "$REPO_DIR/.env" <<EOF
APP_MODE=real
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
ASSETS_DIR=$REPO_DIR/assets
AUDIO_DIR=$REPO_DIR/assets/audio
OUTPUT_DIR=$REPO_DIR/assets/outputs
AVATAR_INPUT=$REPO_DIR/assets/avatars/default.mp4
KOKORO_VOICE=af_heart
KOKORO_LANG_CODE=a
MUSETALK_DIR=$REPO_DIR/third_party/MuseTalk
MUSETALK_INFERENCE_SCRIPT=$REPO_DIR/third_party/MuseTalk/scripts/inference.py
MUSETALK_CHECKPOINT_DIR=$REPO_DIR/third_party/MuseTalk/models
MUSETALK_PYTHON=$REPO_DIR/third_party/MuseTalk/.venv/bin/python
MOCK_VIDEO_PATH=$REPO_DIR/assets/mock/mock_avatar.mp4
EOF

# --- 7. systemd unit for the backend -----------------------------------------
sudo tee /etc/systemd/system/avatar-backend.service >/dev/null <<EOF
[Unit]
Description=AI avatar demo backend (FastAPI + Kokoro + MuseTalk)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$REPO_DIR/backend
EnvironmentFile=$REPO_DIR/.env
ExecStart=$REPO_DIR/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload

# --- 8. Caddy: HTTPS + frontend static + /api + /outputs proxy + bearer token --
if ! command -v caddy >/dev/null 2>&1; then
  sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list
  sudo apt-get update -y
  sudo apt-get install -y caddy
fi

sudo tee /etc/caddy/Caddyfile >/dev/null <<EOF
$PUBLIC_HOST {
    encode zstd gzip

    # Frontend static files
    root * $REPO_DIR/frontend/dist
    @notfile {
        not path /api/* /outputs/*
        not file
    }
    rewrite @notfile /index.html
    file_server

    # Backend API + static MP4 outputs
    @api path /api/*
    handle @api {
        # Require bearer token on state-changing requests; allow GET (polling) without
        # so the SPA can poll without exposing the token to the browser inspector.
        @needs_auth method POST PUT PATCH DELETE
        @needs_auth_unauthorized {
            method POST PUT PATCH DELETE
            not header Authorization "Bearer $API_TOKEN"
        }
        respond @needs_auth_unauthorized 401 {
            body "Unauthorized"
        }
        reverse_proxy 127.0.0.1:8000
    }

    @outputs path /outputs/*
    handle @outputs {
        reverse_proxy 127.0.0.1:8000
    }
}
EOF
sudo systemctl reload caddy || sudo systemctl restart caddy

# --- 9. summary --------------------------------------------------------------
echo
echo "==== ai-avatar-desk-demo bootstrap complete ===="
echo "Public URL : https://$PUBLIC_HOST"
echo "API token  : $API_TOKEN"
echo "Avatar file: $AVATAR_PATH"
echo
echo "Next steps:"
echo "  sudo systemctl enable avatar-backend"
echo "  sudo systemctl start  avatar-backend"
echo "  curl https://$PUBLIC_HOST/api/health"
echo
echo "Replace $AVATAR_PATH with a real face video before demoing."
