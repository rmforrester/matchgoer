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
COPY restore_check.py /app/restore_check.py
USER backupjob
ENTRYPOINT []
CMD ["python", "/app/backup.py"]
