# Tennessee Eastman process container: tep2py (the MATLAB-free Fortran TEP) built from
# source with f2py + gfortran. The paper's pyTEP needs a licensed MATLAB, so the testbed
# substitutes tep2py.
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git gfortran gcc curl \
    && rm -rf /var/lib/apt/lists/*

# tep2py calls the removed np.int / np.integer aliases, so pin numpy < 1.24 (which also
# keeps the classic numpy.distutils f2py backend, avoiding the meson/ninja toolchain).
RUN pip install --no-cache-dir "numpy==1.23.5" "pandas==1.5.3"

WORKDIR /opt
RUN git clone --depth 1 https://github.com/camaramm/tep2py.git
WORKDIR /opt/tep2py
# numpy.distutils (the classic f2py backend) imports the old distutils.msvccompiler, which
# the setuptools-shimmed distutils lacks; force the stdlib distutils (present on 3.11).
ENV SETUPTOOLS_USE_DISTUTILS=stdlib
# Rebuild the Fortran extension for this Python (the committed .so is cpython-36) and
# smoke-test a base-case simulation so a broken build fails at image-build time.
RUN rm -f temain_mod.cpython-*.so \
    && python -m numpy.f2py -c temain_mod-smart.pyf src/tep/temain_mod.f src/tep/teprob.f \
    && python -c "import numpy as np; from tep2py import tep2py; \
s=tep2py(np.zeros((2,20),dtype=int)); s.simulate(); \
print('tep2py XMEAS(7)=', float(s.process_data['XMEAS(7)'].iloc[-1]))"
ENV PYTHONPATH=/opt/tep2py

WORKDIR /app
COPY process_app.py ./
EXPOSE 8080
CMD ["python", "process_app.py"]
