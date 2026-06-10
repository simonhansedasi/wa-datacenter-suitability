#!/usr/bin/env bash
set -e

ENV_NAME="datacenter_siting"

echo "==> Creating conda environment: $ENV_NAME"
conda env create -f environment.yml

echo "==> Registering Jupyter kernel: $ENV_NAME"
conda run -n "$ENV_NAME" python -m ipykernel install --user --name "$ENV_NAME" --display-name "Python ($ENV_NAME)"

echo ""
echo "Done. Select kernel 'Python ($ENV_NAME)' in Jupyter."
