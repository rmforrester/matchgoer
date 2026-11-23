FROM postgres:18-bookworm@sha256:f1ea2a1a4fb7b68d4836be1fdcb8a6466a89b072158bf9d97663600538c294c5
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv age ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/backup-venv
COPY requirements.txt /tmp/backup-requirements.txt
RUN /opt/backup-venv/bin/pip install --no-cache-dir -r /tmp/backup-requirements.txt \
    && groupadd --system backupjob && useradd --system --gid backupjob --home-dir /tmp backupjob
ENV PATH="/opt/backup-venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backup.py /app/backup.py
COPY email_presentation.py /app/email_presentation.py
COPY restore_check.py /app/restore_check.py
COPY supabase_recovery.py deletion_suppression.py run_all.py recovery_policy.py /app/
COPY identity_monitor.py identity-continuity-baseline.json /app/
COPY mandatory_restore.py /app/
USER backupjob
ENTRYPOINT []
CMD ["python", "/app/backup.py"]
