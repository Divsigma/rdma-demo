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
# socket建链+send：服务端
$ chmod +x rdma_rc_test.py
$ PYTHONPATH=<python_path> ./rdma_rc_test.py --device r0 --mode=send
# socket建链+send：客户端
$ chmod +x rdma_rc_test.py
$ PYTHONPATH=<python_path> ./rdma_rc_test.py --device r0 --mode=send --server_ip 192.168.56.102

# CM建链+rdma_write：服务端
$ chmod +x rdma_rc_test.py
$ PYTHONPATH=<python_path> ./rdma_rc_test.py --device r0 --cm 1 --mode=write
# CM建链+rdma_write：客户端
$ chmod +x rdma_rc_test.py
$ PYTHONPATH=<python_path> ./rdma_rc_test.py --device r0 --cm 1 --mode=write --server_ip 192.168.56.102
```

通过socket或CM建链交换GID、QPN、MR的RKEY、MR的ADDDR，完成send或rdma_write操作。对于send操作，需要两端的post_recv和post_send做好同步；对于rdma_write操作，接收方就不用post_recv了（此时是内核旁路！），但仍需要通过链路（比如conn.handshake()）告知对方操作已完成。

注：操作过程中产生的错误会形成一个WC，通过查询WC的状态说明可以帮助定位问题

预期效果是服务端能看到类似日志（即服务端的mr_recv数据被修改），且在send模式和write模式下分别抓包可以看到携带客户端信息（代码中为字符串`>>> client saying hello .......... `）的报文的BTH中OpCode分别是`Send Only (4)`和`RDMA Write Only (10)`：

注：抓包中有对应的Send Only或RDMA Write Only报文，不代表服务端已正确修改。例如当对端QP的qp_access_flag或qp_attr未正确设置时，RDMA Write Only的响应报文为NAK-Invalid Request（如果用CM建链，同时会在建链的QP上发送一个RNR NAK报文）。依据这些NAK信息，结合IB协议第9章的9.9节（错误处理），可以作更详细分析

```shell
# send模式
[INFO] [handshake] got recv_msg_str={"syn": 1} (type=<class 'str'>, len=10) - connection.py:124
[INFO] [handshake] got recv_msg: {'syn': 1} - connection.py:135
[INFO] [wait_until_one_wc] npolled = 1 cqe_status=success - rdma_rc_test.py:22
[WARNING] [<module>] mr_recv content after: [>>> client saying hello .......... |] - rdma_rc_test.py:188

# write模式
[handshake] got recv_msg_str={"done_write": 1} (type=<class 'str'>, len=17) - connection.py:124
[INFO] [handshake] got recv_msg: {'done_write': 1} - connection.py:135
[INFO] [<module>] be notified that RDMA write is done - rdma_rc_test.py:181
[WARNING] [<module>] mr_recv content after: [>>> client saying hello .......... |] - rdma_rc_test.py:188
```

事实上，CM建链后（accpet后）cmid的QP已经可以用于完成交换ADDR+RKEY以及数据交互的操作（参考rdma_server.c）。

单机测试效果：类似`lo_rc_send.py`
双虚拟机测试效果：可以抓包看到建链通信的TCP包、rdma读写的RRoCE包

### `rdma_server.c`、`rdma_client.c`和`udaddy.c`

取自rdma-core/librdmacm/examples/，备注了个人对CM的RC/UD建链及RDMA通信过程中各系统调用的理解。

在rdma-core/目录下./build.sh编译后，可用gdb跟踪调试（后续考虑配置vscode来跟踪）
