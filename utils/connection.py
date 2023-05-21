from utils.logging_utils import root_logger
import socket

from pyverbs import cmid
from pyverbs import mr
from pyverbs import qp
from pyverbs import cm_enums

class Connection:
    def __init__(self, ip='', port=12345):
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.is_serv = True if ip == '' else False

        if self.is_serv:
            self.sock.bind(("0.0.0.0", port))
            self.sock.listen(1)
            self.client_sock, self.client_addr = self.sock.accept()
            self.sock.close()
            self.sock = self.client_sock
            root_logger.info("accept client_addr: {}".format(self.client_addr))
        else:
            self.sock.connect((ip, port))
            root_logger.info("connect to : {}".format((ip, port)))

    def handshake(self, **kwargs):
        import json
        root_logger.info("kwargs to handshake: {}".format(kwargs))
        msg_str = json.dumps(kwargs)

        self.sock.send(msg_str.encode())
        
        recv_msg_str = self.sock.recv(100).decode()
        recv_msg = None
        if len(recv_msg_str) == 0:
            root_logger.error("handshake() recv 0 after sending msg: [{}]".format(msg_str))
        else:
            recv_msg = json.loads(recv_msg_str)
            root_logger.info("got recv_msg: {}".format(recv_msg))
        
        return recv_msg

class CM():
    def __init__(self, ip='', port=7777):
        self.cmid = None

        qp_init_attr = qp.QPInitAttr(cap=qp.QPCap(max_recv_wr=1))

        self.is_serv = True if ip == '' else False

        if self.is_serv:
            addr_info = cmid.AddrInfo(src='0.0.0.0',
                                      src_service=str(port),
                                      port_space=cm_enums.RDMA_PS_TCP,
                                      flags=cm_enums.RAI_PASSIVE)
            self.cmid = cmid.CMID(creator=addr_info,
                                  qp_init_attr=qp_init_attr)
            self.cmid.listen(1)
            root_logger.info("waiting for request")
            client_cmid = self.cmid.get_request()
            root_logger.info("got request")

            # 参照rdma_server.c写法，先注册MR等资源后，再accept
            # 但后续使用中可能需要注意将MR区域清空
            # self.mr_recv = client_cmid.reg_msgs(100)
            # self.mr_send = client_cmid.reg_msgs(100)
            root_logger.info("waiting for accept")
            client_cmid.accept()
            root_logger.info("accepted")

            # 在accept前close listen_cmid会导致程序卡死且无法ctrl+c
            # 猜测：根据udaddy.c，rdma_get_request后需要rdma_ack_cm_evnet
            self.cmid.close()
            root_logger.info("closed listen_cmid")

            self.cmid = client_cmid
        else:
            addr_info = cmid.AddrInfo(dst=ip,
                                      dst_service=str(port),
                                      port_space=cm_enums.RDMA_PS_TCP)
            self.cmid = cmid.CMID(creator=addr_info,
                                  qp_init_attr=qp_init_attr)
            
            # 可以参照rdma_client.c写法，先注册MR等资源后，再connect
            # 但后续使用中可能需要注意将MR区域清空
            # self.mr_recv = self.cmid.reg_msgs(100)
            # self.mr_send = self.cmid.reg_msgs(100)
            root_logger.info("waiting for connect")
            self.cmid.connect()
            root_logger.info("connected")
    
    def handshake(self, **kwargs):
        import json
        root_logger.info("kwargs to handshake: {}".format(kwargs))
        msg_str = json.dumps(kwargs)

        # 准备接收MR，并post_recv等待接收
        # ---- WARNING ----
        # 应先post_recv，否则本端的get_recv_comp无法终止（kill/reboot也不凑效，需要物理重启...）
        mr_recv = self.cmid.reg_msgs(100)
        root_logger.info("register new mr_recv")
        self.cmid.post_recv(mr_recv)

        # 准备发送MR，并post_send发送数据
        #   mr.write()会自动帮传入的str编码
        #   但因为mr.read()只能读到字节流，所以最好显式将需要交换的信息编码后再传入mr_send
        mr_send = self.cmid.reg_msgs(100)
        root_logger.info("register new mr_send")
        send_msg_bytes = msg_str.encode()
        mr_send.write(send_msg_bytes, len(send_msg_bytes))
        self.cmid.post_send(mr_send)

        # 等待post事件完成
        self.cmid.get_send_comp()
        recv_wc = self.cmid.get_recv_comp()
        assert recv_wc
        root_logger.info("recv_wc.byte_len={}".format(recv_wc.byte_len))

        recv_msg_bytes = mr_recv.read(recv_wc.byte_len, offset=0)

        # 此处的处理有些微妙：如果不替换掉空字节，decode后的字符串长度==self.mr_recv的长度
        # 所以如果多次handshake都使用同一个mr_recv，需要每次用完都清空mr_recv
        recv_msg_str = recv_msg_bytes.replace(b'\x00', b'').decode()
        root_logger.info("got recv_msg_str={} (type={}, len={})".format(
            recv_msg_str,
            type(recv_msg_str),
            len(recv_msg_str)
        ))

        recv_msg = None
        if len(recv_msg_str) == 0:
            root_logger.error("handshake() recv 0 after sending msg: [{}]".format(msg_str))
        else:
            recv_msg = json.loads(recv_msg_str)
            root_logger.info("got recv_msg: {}".format(recv_msg))

        return recv_msg