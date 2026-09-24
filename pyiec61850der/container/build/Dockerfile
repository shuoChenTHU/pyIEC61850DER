FROM python:3.12-alpine

# ---------- ENV & ARGS ----------
ENV PYTHONPATH=/work
ARG OS_TYPE=linux
ARG OS_VERSION=linux_amd64
ARG NAME_WORKDIR=work
ARG PYTHON_VERSION_COMPILER=312

ENV LIB_VERSION=1.6.0
ARG LIB_NAME=libiec61850_${LIB_VERSION}
ARG LIB_SRC_NAME=libiec61850-1.6
ARG SF_NAME=/${NAME_WORKDIR}/pylibiec61850

# ---------- PYTHON BINDING FILEPATH ----------
# src and dst path of the source files of libiec61850 -> will copy the so and py files into this folder
ARG LIB_PATH=/${NAME_WORKDIR}/pylibiec61850/source/${OS_VERSION}/${LIB_VERSION}/python${PYTHON_VERSION_COMPILER}
ARG LIB_PATH_DST=/${NAME_WORKDIR}/${LIB_NAME}

# src and dst filepath of libiec61850.so.1.X.X (as RUNPATH defined in the so file) -> will copy this folder into LIB_PATH_DST
ARG LIB_PATH_SRC=/${NAME_WORKDIR}/pylibiec61850/source/${OS_VERSION}/${LIB_VERSION}/${LIB_SRC_NAME}
ARG LIB_PATH_SRC_DST=/${NAME_WORKDIR}/${LIB_SRC_NAME}

# Dynamic linker search path
ENV LD_LIBRARY_PATH=${LIB_PATH_SRC_DST}/build/src:$LD_LIBRARY_PATH

# ---------- WORKDIR ----------
WORKDIR /${NAME_WORKDIR}

# ---------- SYSTEM DEPS & BINARY TOOLS ----------
# Install binutils permanently so readelf/objdump are available inside running containers
RUN apk add --no-cache binutils

# ---------- COPY SOURCE ----------
# Ensure a .dockerignore file exists to avoid copying .git, .venv, etc.															   
COPY . /${NAME_WORKDIR}

# ---------- LIBIEC61850 SETUP ----------
RUN set -eux; \
    # 1. Install pip requirements without cache
    pip install --no-cache-dir -r container/build/requirements.txt; \
    \										   
	# 2. Determine python binding file name
    if [ "${LIB_VERSION}" = "1.6.0" ]; then \
        SO_FILE="_pyiec61850.so"; \
        PY_FILE="pyiec61850.py"; \
    else \
        SO_FILE="_iec61850.so"; \
        PY_FILE="iec61850.py"; \
    fi; \
    # 3. Create target binding & build/src directories (for consistency with the so file configuration)
    mkdir -p ${LIB_PATH_DST} \
             /${LIB_PATH_SRC_DST}; \
	# 4. Copy Python bindings
    cp -a ${LIB_PATH}/. ${LIB_PATH_DST}; \
	# 5. Copy the source so dependency file
	cp -a ${LIB_PATH_SRC}/. ${LIB_PATH_SRC_DST}; \
	# 6. Create a softlink so that the lib loader can use the same path as in windows without dot in path
	ln -sf ${LIB_PATH_DST} ${SF_NAME}; \
	\
	# 7. Set executable permissions
	chmod +x ${LIB_PATH_DST}/${SO_FILE} 2>/dev/null || true; \
    \
    # 8. Strip binaries to shrink .so size & run readelf debug check
    strip --strip-unneeded ${LIB_PATH_DST}/${SO_FILE} 2>/dev/null || true; \
    strip --strip-unneeded ${LIB_PATH_SRC_DST}/build/src/*.so* 2>/dev/null || true; \
    readelf -d ${LIB_PATH_DST}/${SO_FILE}; \
    \
    # 9. Clean up unused source trees & temp caches
    rm -rf /${NAME_WORKDIR}/pylibiec61850/source \
           /root/.cache \
           /tmp/* \
           /var/cache/apk/*
# ---------- ENTRYPOINT ----------
#CMD ["sleep", "infinity"]
CMD ["python", "./main.py"]