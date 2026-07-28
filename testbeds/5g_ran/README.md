# 5G cloud-RAN testbed

A dockerized 5G network. It conists of  four srsRAN Project gNBs (release_25_10) split into DU and CU over F1, four srsUE
terminals, an Open5GS core, a data-network sink, and Xn/RIC stub containers; radio links  are ZeroMQ.

## Images

```bash
cd testbeds/5g_ran
docker build -t ccd-5g-gnb   -f docker/gnb/Dockerfile   docker/gnb
docker build -t ccd-5g-srsue -f docker/srsue/Dockerfile docker/srsue
docker build -t ccd-5g-sink  -f docker/sink/Dockerfile docker/sink
```

## Example Usage

```bash
cd testbeds/5g_ran/scripts
python testbed.py up                          
python testbed.py status                      
python testbed.py down
```
