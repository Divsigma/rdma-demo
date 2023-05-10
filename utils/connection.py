from utils.logging_utils import root_logger
import socket

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
        recv_msg = json.loads(recv_msg_str)

        root_logger.info("got recv_msg: {}".format(recv_msg))
        
        return recv_msg