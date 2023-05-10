# rdma-demo

### `lo_rc_send.py`
运行示例：
```shell
$ chmod +x lo_rc_send.py
$ PYTHONPATH=<python_path> ./lo_rc_send.py
```

本地post_send和post_recv操作时，为什么用Wireshark抓包抓不到RRoCE协议包？


### `rdma_rc_test.py`

运行示例：
```shell
# 服务端
$ chmod +x rdma_rc_test.py
$ PYTHONPATH=<python_path> ./rdma_rc_test.py --device r0
# 客户端
$ chmod +x rdma_rc_test.py
$ PYTHONPATH=<python_path> ./rdma_rc_test.py --device r0 --server_ip 192.168.56.102
```

通过socket建链交换GID、QPN、MR的RKEY、MR的ADDDR，完成rdma操作。

单机测试效果类似`lo_rc_send.py`