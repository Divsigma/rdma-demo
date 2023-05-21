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
# socket建链：服务端
$ chmod +x rdma_rc_test.py
$ PYTHONPATH=<python_path> ./rdma_rc_test.py --device r0
# socket建链：客户端
$ chmod +x rdma_rc_test.py
$ PYTHONPATH=<python_path> ./rdma_rc_test.py --device r0 --server_ip 192.168.56.102

# CM建链：服务端
$ chmod +x rdma_rc_test.py
$ PYTHONPATH=<python_path> ./rdma_rc_test.py --device r0 --cm 1
# CM建链：客户端
$ chmod +x rdma_rc_test.py
$ PYTHONPATH=<python_path> ./rdma_rc_test.py --device r0 --cm 1 --server_ip 192.168.56.102
```

通过socket或CM建链交换GID、QPN、MR的RKEY、MR的ADDDR，完成rdma操作。

预期效果是服务端能看到类似日志（即服务端的mr_recv数据被修改）：

```shell
[WARNING] [<module>] mr_recv content before: [[Default Empty Recv Data]] - rdma_rc_test.py:114
[INFO] [handshake] kwargs to handshake: {'syn': 1} - connection.py:28
[INFO] [handshake] got recv_msg: {'syn': 1} - connection.py:39
[WARNING] [<module>] mr_recv content after: [>>> client saying hello .......... |] - rdma_rc_test.py:146
```

事实上，CM建链后（accpet后）cmid的QP已经可以用于完成交换ADDR+RKEY以及数据交互的操作（参考rdma_server.c）。

单机测试效果：类似`lo_rc_send.py`
双虚拟机测试效果：可以抓包看到建链通信的TCP包、rdma读写的RRoCE包

### `rdma_server.c`、`rdma_client.c`和`udaddy.c`

取自rdma-core/librdmacm/examples/，备注了个人对CM的RC/UD建链及RDMA通信过程中各系统调用的理解。

在rdma-core/目录下./build.sh编译后，可用gdb跟踪调试（后续考虑配置vscode来跟踪）
