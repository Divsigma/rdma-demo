import argparse
import utils.connection
from utils.logging_utils import root_logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--server_ip', dest='server_ip', type=str, default='')
    args = parser.parse_args()

    is_server = False if args.server_ip == '' else True

    conn = utils.connection.Connection(ip=args.server_ip)

    import random
    gid = random.randint(1, 10000)
    qpn = random.randint(10000, 20000)
    conn.handshake(gid=gid, qpn=qpn)

    rkey = str(random.randint(1000, 10000))
    addr = random.randint(20000000, 80000000)
    conn.handshake(rkey=rkey, addr=addr)