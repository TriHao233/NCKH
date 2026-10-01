FROM quay.io/docling-project/docling-serve@sha256:70ea35b4a94a27babd83d0ec8fc3ed8b0cd3ff3651595070edd15cea2ad9babf

USER 0
RUN dnf install -y tesseract-langpack-vie \
    && dnf clean all \
    && rm -rf /var/cache/dnf \
    && mkdir -p /var/cache/docling/tmp /var/cache/docling/scratch /var/cache/docling/huggingface \
    && chown -R 1001:0 /var/cache/docling
USER 1001
