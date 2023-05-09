#!/usr/bin/env python3


from pyverbs import device
from pyverbs import pd
from pyverbs import cq
from pyverbs import qp
from pyverbs import addr
from pyverbs import enums
from pyverbs import wr
from pyverbs import mr

lst = device.get_device_list()

RECV_WR_ID = 2021
SEND_WR_ID = 2017

print("get lst: {}".format(lst))

for i in lst:
    name = i.name.decode()
    ctx = device.Context(name=name)
    print(i.name.decode(), device.translate_node_type(i.node_type))
    # print(ctx.query_device())
    print('-' * 80)

    pd0 = pd.PD(ctx)

    cq0 = cq.CQ(ctx, 100)
    cap0 = qp.QPCap(1, 1)
    # qia0 = qp.QPInitAttr(cap=cap0, qp_type=enums.IBV_QPT_UD, scq=cq0, rcq=cq0)
    qia0 = qp.QPInitAttr(cap=cap0, qp_type=enums.IBV_QPT_RC, scq=cq0, rcq=cq0)

    rcqp = qp.QP(pd0, qia0, qp.QPAttr())

    # ---- 发送方信息 ----
    # RoCEv2对设备的每个端口维护一张GID表，所以只需要通过gid_index即可获取GID（类似AH）
    # 有效的port和gid_index可以用过`ibv_devinfo -v`查看
    sport_num = 1
    # 使用IPv6
    sgid_index = 2
    sgid = ctx.query_gid(port_num=sport_num, index=sgid_index)

    # ---- 接收方信息（AH+QPN=PORT+GID+QPN） ----
    # UD通信中，对所有可能的通信对端，创建一个AH
    # 对端0：本机
    dgid0 = sgid
    gr0 = addr.GlobalRoute(dgid=dgid0, sgid_index=sgid_index)
    ah_attr0 = addr.AHAttr(port_num=sport_num, is_global=1, gr=gr0)
    ah0 = addr.AH(pd0, attr=ah_attr0)

    # ---- 准备交换数据（QP状态转入RTS） ----
    # 该部分挺重要，不调用to_rts可能在post_send时有errno=22（为何？）
    #              不设置ah_attr可能在to_rtr时有errno=22（为何？）
    #              却可以不设置dest_qp_num，此时无法通过post_send完成mr_recv的修改（为何？）
    qa0 = qp.QPAttr()
    qa0.ah_attr = ah_attr0
    qa0.dest_qp_num = rcqp.qp_num
    rcqp.to_rts(qa0)

    # ---- 开始交换数据 ----
    # 准备scatter/gather读写区域
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

    recv_content_str_data = "[i am default recv data]"
    mr_recv.write(recv_content_str_data, len(recv_content_str_data))
    wr_recv = wr.RecvWR(wr_id=RECV_WR_ID, num_sge=len(recv_sge_list), sg=recv_sge_list)
    # wr_recv.set_wr_ud(ah0, rqpn=0x000000, rqkey=0)
    rcqp.post_recv(wr_recv)
    print("mr_recv content before: {}".format(mr_recv.read(mr_recv.length, offset=0).decode()))

    send_content_str_data = "i am sender..........xxx"
    mr_send.write(send_content_str_data, len(send_content_str_data))
    print("mr_send content to send: {}".format(mr_send.read(mr_send.length, offset=0).decode()))
    wr_send = wr.SendWR(wr_id=SEND_WR_ID, opcode=enums.IBV_WR_SEND, num_sge=1, sg=send_sge_list)
    # wr_send.set_wr_ud(ah0, rqpn=udqp.qp_num, rqkey=0)
    wr_send.set_wr_rdma(rkey=mr_recv.rkey, addr=mr_recv.buf)
    print("qp_num {}".format(rcqp.qp_num))
    rcqp.post_send(wr_send)
    # 等待发送完成
    _, _ = cq0.poll()

    print("mr_recv content after: {}".format(mr_recv.read(mr_recv.length, offset=0).decode()))


# ctx = device.Context(name = 'test_name')

# print(ctx.query_device())