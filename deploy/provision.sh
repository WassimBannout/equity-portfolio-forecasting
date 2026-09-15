#!/bin/bash
# Run on a NEW authorised Ubuntu 24.04 x86-64 VPS, from a reviewed checkout.
set -euo pipefail
umask 022
[[ $EUID -eq 0 && $# -eq 3 ]]
domain=$1
uv_binary=$2
deploy_public_key=$3
[[ "$domain" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}$ ]]
[[ $(uname -m) = x86_64 ]]
test ! -e /srv/portfolio/current
# Digest of the independently tested uv 0.12.13 Linux x86-64 binary.
printf '%s  %s\n' b59310db262709ee92baf7954ef30820f1442ffa48b263f7001a236fe9004047 "$uv_binary" | sha256sum --check --status
ssh-keygen -l -f "$deploy_public_key" > /dev/null
test "$(wc -l < "$deploy_public_key")" -eq 1
apt-get update
apt-get install -y ca-certificates python3 openssh-server sudo util-linux caddy
getent group pf-ops > /dev/null || groupadd --system pf-ops
id pf-deploy > /dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/pf-deploy --shell /bin/sh --gid pf-ops pf-deploy
usermod --password '*' pf-deploy
id pf-web > /dev/null 2>&1 || useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin pf-web
id pf-batch > /dev/null 2>&1 || useradd --system --home-dir /var/lib/pf-batch --shell /usr/sbin/nologin --gid pf-ops pf-batch
install -d -m 0755 /opt/pf-tools /usr/local/libexec /srv/portfolio
install -d -o pf-deploy -g pf-ops -m 0755 /opt/pf-python /srv/portfolio/releases
chown pf-deploy:pf-ops /srv/portfolio
install -m 0755 "$uv_binary" /opt/pf-tools/uv
runuser -u pf-deploy -- env UV_PYTHON_INSTALL_DIR=/opt/pf-python /opt/pf-tools/uv python install 3.12.14
chown -R root:root /opt/pf-python
install -d -o root -g pf-ops -m 0750 /var/lib/pf-control
install -o pf-deploy -g pf-ops -m 0660 /dev/null /var/lib/pf-control/operation.lock
install -d -m 0700 /etc/portfolio
install -m 0755 deploy/gateway.py /usr/local/libexec/pf-gateway
install -m 0755 deploy/pf-ready /usr/local/libexec/pf-ready
install -m 0644 deploy/pf-*.service deploy/pf-freshness.timer /etc/systemd/system/
install -m 0440 deploy/sudoers /etc/sudoers.d/portfolio
visudo -cf /etc/sudoers.d/portfolio
install -d -o root -g root -m 0755 /var/lib/pf-deploy/.ssh
{ printf 'restrict,command="/usr/bin/timeout --kill-after=10s 1700s /usr/bin/python3 -I /usr/local/libexec/pf-gateway" '; cat "$deploy_public_key"; } > /var/lib/pf-deploy/.ssh/authorized_keys
chmod 0644 /var/lib/pf-deploy/.ssh/authorized_keys
# pf-deploy cannot change its own SSH restrictions, even through a released build.
chown root:root /var/lib/pf-deploy /var/lib/pf-deploy/.ssh/authorized_keys
install -d -o pf-deploy -g pf-ops -m 0700 /var/lib/pf-deploy/.cache
sshd -t
systemctl reload ssh.service
install -d -m 0755 /etc/systemd/system/caddy.service.d
printf '[Service]\nEnvironment=PF_DOMAIN=%s\n' "$domain" > /etc/systemd/system/caddy.service.d/portfolio.conf
install -m 0644 deploy/Caddyfile /etc/caddy/Caddyfile
PF_DOMAIN="$domain" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl daemon-reload
systemctl enable pf-dashboard.service pf-freshness.timer caddy.service
printf '%s\n' 'Provisioned configuration only. Inject reader/writer environment files, verify DNS/firewall and data-use rights, then release. See docs/OPERATIONS.md.'
