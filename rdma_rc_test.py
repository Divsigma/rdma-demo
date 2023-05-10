#!/usr/bin/env python3


from pyverbs import device
from pyverbs import pd
from pyverbs import cq
from pyverbs import qp
from pyverbs import addr
from pyverbs import enums
from pyverbs import wr
from pyverbs import mr

import argparse
import time
import utils.connection
from utils.logging_utils import root_logger

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--server_ip', dest='server_ip', type=str, default='')
    parser.add_argument('--device', dest='device_name', type=str, required=True)
    args = parser.parse_args()

    # ---- 获取通讯设备名 ----
    lst = device.get_device_list()

    RECV_WR_ID = 2021
    SEND_WR_ID = 2017

    root_logger.info("get lst: {}".format(lst))

    device_name = args.device_name
    ctx = device.Context(name=device_name)
    root_logger.info("device_name = {}".format(device_name))


    is_server = True if args.server_ip == '' else False
    if is_server:
        root_logger.info(" ==== Working as Server ====")
    else:
        root_logger.info(" ==== Working as Client ====")

    # ---- 建链 ----
    conn = utils.connection.Connection(ip=args.server_ip)

    # ---- 注册通信用的QP资源 ----
    pd0 = pd.PD(ctx)
    cq0 = cq.CQ(ctx, 100)
    cap0 = qp.QPCap(1, 1)
    # qia0 = qp.QPInitAttr(cap=cap0, qp_type=enums.IBV_QPT_UD, scq=cq0, rcq=cq0)
    qia0 = qp.QPInitAttr(cap=cap0, qp_type=enums.IBV_QPT_RC, scq=cq0, rcq=cq0)
    rcqp = qp.QP(pd0, qia0, qp.QPAttr())

    # ---- 获取本端信息 ----
    # RoCEv2对设备的每个端口维护一张GID表，所以只需要通过gid_index即可获取GID（类似AH）
    # 有效的port和gid_index可以用过`ibv_devinfo -v`查看
    # 硬编码：使用port1
    sport_num = 1
    # 硬编码：使用IPv6
    sgid_index = 2
    sgid = ctx.query_gid(port_num=sport_num, index=sgid_index)

    # ---- 注册对端信息（AH+QPN=PORT+GID+QPN） ----
    # UD通信中，对所有可能的通信对端，创建一个AH
    # 通过建链获取对端GID+QPN
    remote_node_info = conn.handshake(gid=sgid.gid, qpn=rcqp.qp_num)
    root_logger.info("remote gid={}, remote qpn=0x{:x}".format(
        remote_node_info['gid'], int(remote_node_info['qpn'])
    ))

    dgid0 = addr.GID(remote_node_info['gid'])
    gr0 = addr.GlobalRoute(dgid=dgid0, sgid_index=sgid_index)
    ah_attr0 = addr.AHAttr(port_num=sport_num, is_global=1, gr=gr0)
    ah0 = addr.AH(pd0, attr=ah_attr0)
    # QP状态转入RTS，该部分挺重要：
    # 不调用to_rts可能在post_send时有errno=22（为何？）
    # 不设置ah_attr可能在to_rtr时有errno=22（为何？）
    # 却可以不设置dest_qp_num，此时无法通过post_send完成mr_recv的修改（为何？）
    qa0 = qp.QPAttr()
    qa0.ah_attr = ah_attr0
    qa0.dest_qp_num = remote_node_info['qpn']
    rcqp.to_rts(qa0)

    # ---- 准备scatter/gather读写区域 ----
    mr_send = mr.MR(pd0, 
                    length=50, 
                    access=enums.IBV_ACCESS_LOCAL_WRITE | enums.IBV_ACCESS_REMOTE_READ)
    send_sge_list = [
        wr.SGE(addr=mr_send.buf, length=mr_send.length, lkey=mr_send.lkey)
    ]
    # 参考ibv_reg_mr，REMOTE_WRITE和LOCAL_WRITE必须同时设置
    mr_recv = mr.MR(pd0,
                    length=50,
                    access=enums.IBV_ACCESS_LOCAL_WRITE | enums.IBV_ACCESS_REMOTE_WRITE)
    recv_sge_list = [
        wr.SGE(addr=mr_recv.buf, length=mr_recv.length, lkey=mr_recv.lkey)
    ]
    # 通过建链获取对端MR的rkey和addr
    remote_mr_info = conn.handshake(rkey=mr_recv.rkey, addr=mr_recv.buf)

    # ---- 开始交换数据 ----
    if is_server:
        # 服务端只管接受
        recv_content_str_data = "[Default Empty Recv Data]"
        mr_recv.write(recv_content_str_data, len(recv_content_str_data))
        wr_recv = wr.RecvWR(wr_id=RECV_WR_ID, num_sge=len(recv_sge_list), sg=recv_sge_list)
        root_logger.warning("mr_recv content before: [{}]".format(mr_recv.read(mr_recv.length, offset=0).decode()))

        # 同步：发送方post_send前、接收方post_recv后
        # 否则接收方可能无法从CQ中poll出post_recv的CQE
        # time.sleep(2)
        rcqp.post_recv(wr_recv)
        conn.handshake(syn=1)
    else:
        # 客户端只管发送
        send_content_str_data = ">>> client saying hello .......... |"
        mr_send.write(send_content_str_data, len(send_content_str_data))
        root_logger.info("mr_send content to send: [{}]".format(mr_send.read(mr_send.length, offset=0).decode()))
        wr_send = wr.SendWR(wr_id=SEND_WR_ID, opcode=enums.IBV_WR_SEND, num_sge=1, sg=send_sge_list)

        # wr_send.set_wr_ud(ah0, rqpn=udqp.qp_num, rqkey=0)
        rkey = remote_mr_info['rkey']
        addr = remote_mr_info['addr']
        root_logger.info("remote rkey=0x{:x}, remote addr=0x{:x}".format(rkey, addr))
        wr_send.set_wr_rdma(rkey=rkey, addr=addr)
        # 同步：发送方post_send前、接收方post_recv后
        # 否则接收方可能无法从CQ中poll出post_recv的CQE
        conn.handshake(syn=1)
        rcqp.post_send(wr_send)

    # 等待接收WR或发送WR完成
    npolled = -1
    wcs = None
    while npolled <= 0:
        npolled, wcs = cq0.poll()
    # npolled, wcs = cq0.poll()
    # time.sleep(1)

    root_logger.warning("mr_recv content after: [{}]".format(mr_recv.read(mr_recv.length, offset=0).decode()))


# ctx = device.Context(name = 'test_name')

# print(ctx.query_device())
