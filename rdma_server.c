/*
 * Copyright (c) 2005-2009 Intel Corporation.  All rights reserved.
 *
 * This software is available to you under the OpenIB.org BSD license
 * below:
 *
 *     Redistribution and use in source and binary forms, with or
 *     without modification, are permitted provided that the following
 *     conditions are met:
 *
 *      - Redistributions of source code must retain the above
 *        copyright notice, this list of conditions and the following
 *        disclaimer.
 *
 *      - Redistributions in binary form must reproduce the above
 *        copyright notice, this list of conditions and the following
 *        disclaimer in the documentation and/or other materials
 *        provided with the distribution.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 * MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AWV
 * NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
 * BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
 * ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
 * CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <getopt.h>
#include <netdb.h>
#include <rdma/rdma_cma.h>
#include <rdma/rdma_verbs.h>


// =================================================
// 强烈建议：man看入门手册rdma_cm
//          对server和client端系统调用流程作概览
// 
// NOTE：服务端总体流程如下（客户端类似，去掉监听、accept综合成connect。connect时发送REQ和RTU）
//       -> 创建cmid（socket的fd），需要绑定RDMA设备（获取GID？） -> 创建qp（socket）
//       -> 监听（bind+listen）
//       -> 前半段accept（get_request），分配cmid和qp 
//        -> 准备RDMA的读写MR，握手包private-data校验等
//       -> 后半段accept，发送二次握手的REP或REJ包
//       -> （读写操作）
//       -> 销毁
// =================================================


static const char *server = "0.0.0.0";
// librdmacm接口作为兼容iWARP和RoCEv2的接口，port对不同协议有不同含义：
// （1）iWARP传输层基于TCP，port就是TCP端口。抓包可见TCP报的端口号==port
// （2）RoCEv2传输层基于IB Transport，port是IB Transport层的端口，而IB Transport基于UDP
//      抓包可见UDP报的端口号!=port，而是UDP:4791。
//      观察到rdma_rxe模块加载后udp的4791端口即被占用，猜测是Soft-RoCE中使用SOCK_DGRAM的socket，对4791调用了bind
//      UDP的socket编程参考：https://runsisi.com/2020/01/06/udp-listen/
//      大致流程：UDP端口大致只有SS_CLOSED和SS_ESTAB两种状态，前者代表UDP已bind（TCP的已bind应该也是CLOSED只是不显示？）
//               server通过bind指定源端口+源IP后（netstat看到显示“-”，其实是内核的TCP_CLOSED状态；ss -nupa看到显示UNCONN状态）
//               client就可以recvfrom/sendto这个公知端口完成UDP通信。
//               client端也可以connect来隐式bind本端源端口+源IP，并将该socket与server的端口+IP绑定，
//               形成一个五元组（netstat看到ESTABLISHED，其实是复用了内核的TCP_ESTABLISHED状态；ss -nupa看到显示ESTAB状态）。
//               UDP建链的好处主要是可以获得ECONNREFUSED：https://zhuanlan.zhihu.com/p/380109394
//      为什么ss -nupl显示出“监听状态”的UDP socket？其实l参数显示了SS_LISTEN和SS_CLOSE的socket。bind之后的UDP服务器socket属于后者
static const char *port = "7471";

// 根据rdma_create_qp手册：
//   An rdma_cm_id may only be associated with a single QP
// 以及rdma_create_ep手册中关于rdma_cm_id的用法，
//   推测：rdma_cm_id不光用于CM建链，更像本机的通讯端点句柄（即socket的fd。QP类似socket）
//   实锤：rdma_create_id手册指出，Rdma_cm_id's are conceptually equivalent to a socket for RDMA communication
//       同时指出，rdma_cm_id天生支持同步和异步两种模式。本程序是同步模式。
static struct rdma_cm_id *listen_id, *id;

static struct ibv_mr *mr, *send_mr;
static int send_flags;
static uint8_t send_msg[16] = {'e', 'f', 'g', 'h'};
static uint8_t recv_msg[16];

static int run(void)
{
	struct rdma_addrinfo hints, *res;
	struct ibv_qp_init_attr init_attr;
	struct ibv_qp_attr qp_attr;
	struct ibv_wc wc;
	int ret;

	memset(&hints, 0, sizeof hints);
	// 根据rdma_create_ep手册：
	//   不设置则意味着communication id是用作active side of a connection
	// 根据rdma_cm手册和rdma_create_ep源码：
	//   服务端和客户端在rdma_getaddrinfo->rdma_accept/rdma_connect的流水线不一样
	//   hints.ai_flags应该也是控制wrapper函数（rdma_create_ep）执行函数流程的
	hints.ai_flags = RAI_PASSIVE;

	// 实验：
	//   对RoCEv2，似乎去掉也不影响正常运作。毕竟RoCEv2的RDMA技术是基于UDP的。
	// 根据rdma_create_id手册：
	//   指明RDMA通信类型RC/UC/IB(任何类型)
	hints.ai_port_space = RDMA_PS_TCP;

	// 作用：类似socket编程前htonl之类的操作？
	ret = rdma_getaddrinfo(server, port, &hints, &res);
	if (ret) {
		printf("rdma_getaddrinfo: %s\n", gai_strerror(ret));
		return ret;
	}

	memset(&init_attr, 0, sizeof init_attr);
	init_attr.cap.max_send_wr = init_attr.cap.max_recv_wr = 1;
	init_attr.cap.max_send_sge = init_attr.cap.max_recv_sge = 1;
	init_attr.cap.max_inline_data = 16;
	init_attr.sq_sig_all = 1;

	// 类似socket系统调用：
	//   创建用于监听的socket（QP1），传入监听地址信息（rdma_addrinfo），返回fd（listen_id）
	// rdma_create_ep手册有建链api调用说明，值得一看。
	// rdma_create_ep vs rdma_create_id：
	//   根据rdma_cm手册，前者封装了若干函数
	// 根据rdma_create_ep源码：
	//   封装了rdma_create_id、bind_addr、resolve_addr（创建cmid需要绑定RDMA设备）、create_qp等
	ret = rdma_create_ep(&listen_id, res, NULL, &init_attr);
	if (ret) {
		perror("rdma_create_ep");
		goto out_free_addrinfo;
	}
	
	// 类似listen。
	// 但不同于socket编程：
	//   此时服务端listen_id在rdma_listen前不用rdma_bind_addr
	// 为啥不用bind（猜测）：
	//   因为CM建链属于GSI（通用服务接口），在IB协议中约定GSI使用QP1
	ret = rdma_listen(listen_id, 0);
	if (ret) {
		perror("rdma_listen");
		goto out_destroy_listen_ep;
	}

	// 类似accept前半部，根据rdma_get_request手册和源码：
	//   尝试分配一个新的socket（QPN）来后续通信，返回socket的fd（cmid）作为操作句柄
	//   在listen_id上（QP1）用id接收链接请求，按rdma_create_ep中指定的qp_init_attr为id分配QP
	ret = rdma_get_request(listen_id, &id);
	if (ret) {
		perror("rdma_get_request");
		goto out_destroy_listen_ep;
	}

	// 根据IB协议，QP有INIT->RTR->RTS的状态变化，
	// QP需要进入RTR后才能post_send和post_recv
	// 根据rdma_create_qp手册：对cmid创建好QP后（rdma_create_qp后），QP已经进入RTR；

	// 准备用于recv和send的MR及其缓冲区
	memset(&qp_attr, 0, sizeof qp_attr);
	memset(&init_attr, 0, sizeof init_attr);
	ret = ibv_query_qp(id->qp, &qp_attr, IBV_QP_CAP,
			   &init_attr);
	if (ret) {
		perror("ibv_query_qp");
		goto out_destroy_accept_ep;
	}
	if (init_attr.cap.max_inline_data >= 16)
		send_flags = IBV_SEND_INLINE;
	else
		printf("rdma_server: device doesn't support IBV_SEND_INLINE, "
		       "using sge sends\n");

	mr = rdma_reg_msgs(id, recv_msg, 16);
	if (!mr) {
		ret = -1;
		perror("rdma_reg_msgs for recv_msg");
		goto out_destroy_accept_ep;
	}
	if ((send_flags & IBV_SEND_INLINE) == 0) {
		send_mr = rdma_reg_msgs(id, send_msg, 16);
		if (!send_mr) {
			ret = -1;
			perror("rdma_reg_msgs for send_msg");
			goto out_dereg_recv;
		}
	}

	// 根据rdma_post_recv手册：
	//   对端发送信息前，接收端需要post_recv且保证缓冲区够大
	ret = rdma_post_recv(id, NULL, recv_msg, 16, mr);
	if (ret) {
		perror("rdma_post_recv");
		goto out_dereg_send;
	}

	// 类似accept后半部。
	// 根据rdma_accept手册：
	//   不同于socket编程，对于一个RDMA_CM_EVENT_CONNECT_REQUEST，
	//   rdma_get_request后，要先分配资源&准备状态&校验
	//   再决定对这个REQUEST，rdma_reject还是rdma_accept。
	// 待抓包验证：
	//   猜测此处产生CM建链第二次+第三次握手包
	ret = rdma_accept(id, NULL);
	if (ret) {
		perror("rdma_accept");
		goto out_dereg_send;
	}

	// 根据手册：阻塞式。轮询调度ibv_poll_cq，直到至少有一个CQE
	while ((ret = rdma_get_recv_comp(id, &wc)) == 0);
	if (ret < 0) {
		perror("rdma_get_recv_comp");
		goto out_disconnect;
	}

	ret = rdma_post_send(id, NULL, send_msg, 16, send_mr, send_flags);
	if (ret) {
		perror("rdma_post_send");
		goto out_disconnect;
	}

	while ((ret = rdma_get_send_comp(id, &wc)) == 0);
	if (ret < 0)
		perror("rdma_get_send_comp");
	else
		ret = 0;

out_disconnect:
	rdma_disconnect(id);
out_dereg_send:
	if ((send_flags & IBV_SEND_INLINE) == 0)
		rdma_dereg_mr(send_mr);
out_dereg_recv:
	rdma_dereg_mr(mr);
out_destroy_accept_ep:
	rdma_destroy_ep(id);
out_destroy_listen_ep:
	rdma_destroy_ep(listen_id);
out_free_addrinfo:
	rdma_freeaddrinfo(res);
	return ret;
}

int main(int argc, char **argv)
{
	int op, ret;

	while ((op = getopt(argc, argv, "s:p:")) != -1) {
		switch (op) {
		case 's':
			server = optarg;
			break;
		case 'p':
			port = optarg;
			break;
		default:
			printf("usage: %s\n", argv[0]);
			printf("\t[-s server_address]\n");
			printf("\t[-p port_number]\n");
			exit(1);
		}
	}

	printf("rdma_server: start\n");
	ret = run();
	printf("rdma_server: end %d\n", ret);
	return ret;
}
