#!/bin/bash
set -e

DO="root@68.183.130.60"
SSH="ssh -i $HOME/.ssh/id_ed25519"
DEST="$DO:/home/simonhans/coding/datacenter_siting"

echo "Syncing to DO..."
rsync -av --checksum \
  -e "ssh -i $HOME/.ssh/id_ed25519" \
  --exclude='.git/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='venv/' \
  --exclude='data/' \
  --exclude='*.ipynb' \
  --exclude='make_nb3.py' \
  --exclude='export_grid.py' \
  --exclude='rebuild_datacenters.py' \
  ./ "$DEST"

echo "Setting up venv and dependencies..."
$SSH $DO "cd /home/simonhans/coding/datacenter_siting && python3 -m venv venv && venv/bin/pip install -q flask"

echo "Installing service and nginx config..."
$SSH $DO "cp /home/simonhans/coding/datacenter_siting/datacenter_siting.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable datacenter_siting"

$SSH $DO "cp /home/simonhans/coding/datacenter_siting/nginx.conf /etc/nginx/sites-available/datacenter_siting && ln -sf /etc/nginx/sites-available/datacenter_siting /etc/nginx/sites-enabled/datacenter_siting && nginx -t && systemctl reload nginx"

echo "Starting service..."
$SSH $DO "systemctl restart datacenter_siting && systemctl is-active datacenter_siting"

echo "Done. Live at https://datacenters.simonhansedasi.com"
