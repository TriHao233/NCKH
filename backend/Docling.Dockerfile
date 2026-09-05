FROM quay.io/docling-project/docling-serve@sha256:70ea35b4a94a27babd83d0ec8fc3ed8b0cd3ff3651595070edd15cea2ad9babf

USER 0
RUN dnf install -y tesseract-langpack-vie \
    && dnf clean all \
    && rm -rf /var/cache/dnf
USER 1001
