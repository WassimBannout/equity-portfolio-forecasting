#!/bin/bash
set -euo pipefail
umask 077
[[ "${SSH_HOST:?}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]]
case "${1:-}" in
    release) [[ "${2:-}" =~ ^[0-9a-f]{40}$ ]] ;;
    batch|freshness|status|rollback) test "$#" -eq 1 ;;
    *) exit 2 ;;
esac
private_dir=$(mktemp -d)
trap 'rm -rf -- "$private_dir"' EXIT
printf '%s\n' "${SSH_PRIVATE_KEY:?}" > "$private_dir/key"
printf '%s\n' "${SSH_KNOWN_HOSTS:?}" > "$private_dir/known_hosts"
unset SSH_PRIVATE_KEY SSH_KNOWN_HOSTS
# Obtain host keys independently from the VPS console, never trust-on-first-use.
timeout --kill-after=10s 1650s ssh -F /dev/null -T \
    -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$private_dir/known_hosts" -o GlobalKnownHostsFile=/dev/null \
    -o ConnectTimeout=10 -o ConnectionAttempts=1 \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    -o ClearAllForwardings=yes -o ForwardAgent=no \
    -i "$private_dir/key" "pf-deploy@$SSH_HOST" "$*"
