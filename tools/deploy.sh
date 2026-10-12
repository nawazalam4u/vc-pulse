#!/bin/zsh
# Commit is already made. Push to GitHub (auto-deploys); if Vercel doesn't pick it up in 3 minutes, deploy directly.
GH=$(ls -d $HOME/.local-tools/gh_*/bin/gh | head -1)
for i in 1 2 3; do git -c "credential.https://github.com.helper=" -c "credential.https://github.com.helper=!$GH auth git-credential" push -q && break; sleep 8; done
SHA=$(git rev-parse --short=7 HEAD)
for i in $(seq 1 30); do curl -s https://vc-pulse-lime.vercel.app/api/health | grep -q "\"$SHA\"" && { echo "live $SHA (auto-deploy)"; exit 0; }; sleep 6; done
export PATH=$HOME/.local-node22/bin:$HOME/.local-node/bin:$PATH
npx --yes vercel@latest deploy --prod --yes >/dev/null 2>&1
curl -s https://vc-pulse-lime.vercel.app/api/health | grep -o '"version": "[a-z0-9]*"'
