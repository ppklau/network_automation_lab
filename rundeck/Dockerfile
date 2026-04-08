# ACME Investments — Rundeck container with Ansible
# ─────────────────────────────────────────────────────────────────────────────
# Extends the official Rundeck image with Python 3, pip, Ansible, NAPALM and
# Netmiko so that job steps can call ansible-playbook directly inside the
# container without an external control node.
#
# Build context: rundeck/
# Used by: monitoring/docker-compose.yml (service: rundeck)
# ─────────────────────────────────────────────────────────────────────────────

FROM rundeck/rundeck:5.8.0

# ── Install Python + Ansible as root ─────────────────────────────────────────
USER root

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        openssh-client \
        sshpass && \
    # Use a venv to avoid the "externally managed environment" restriction
    # introduced in Debian Bookworm / Ubuntu 23.04+
    python3 -m venv /opt/ansible-venv && \
    /opt/ansible-venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/ansible-venv/bin/pip install --no-cache-dir \
        ansible \
        napalm \
        netmiko \
        "napalm-ansible>=5.0.0" && \
    # Symlink into PATH so rundeck job steps can call ansible-playbook directly
    ln -s /opt/ansible-venv/bin/ansible          /usr/local/bin/ansible && \
    ln -s /opt/ansible-venv/bin/ansible-playbook /usr/local/bin/ansible-playbook && \
    ln -s /opt/ansible-venv/bin/ansible-galaxy   /usr/local/bin/ansible-galaxy && \
    # Clean up apt cache to keep the image small
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ── Switch back to the rundeck service account ───────────────────────────────
USER rundeck
