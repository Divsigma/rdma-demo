# 重要参考文档

[OpenUCX文档 | Running UCX](https://openucx.readthedocs.io/en/master/running.html)

[OpenMPI文档 | FAQ: Building Open MPI](https://www.open-mpi.org/faq/?category=building)

[OpenMPI文档 | FAQ](https://www.open-mpi.org/faq/)

# 配置步骤

## （1）根据文档，编译UCX

```shell
$ wget https://github.com/openucx/ucx/releases/download/v1.14.1/ucx-1.14.1.tar.gz
$ tar xzf ucx-1.14.1.tar.gz
$ cd ucx-1.14
$ mkdir build
$ cd build
$ ../configure --enable-mt
$ make
$ sudo make install
```

configure参数说明：

- `--enable-mt`：允许多线程模式。不加该参数可能导致openmpi无法加载ucx模块，参考[ucx not work with openmpi4.0.3:No components were able to be opened in the pml framework](https://github.com/openucx/ucx/issues/5284)

## （2）根据文档，编译OMPI

```shell
$ wget https://download.open-mpi.org/release/open-mpi/v4.1/openmpi-4.1.5.tar.gz
$ tar -zxvf openmpi-4.1.5.tar.gz
$ cd openmpi-4.1.5
$ ./configure --with-ucx --without-verbs --disable-mpi-fortran
$ make
$ sudo make install
```

configure参数说明：

- `--with-ucx`：使用UCX来支持OpenFabrics（也可以尝试使用openib，但未成功配置）

- `--without-verbs`：根据[FAQ](https://www.open-mpi.org/faq/?category=openfabrics)，OMPI4.0.x版本UCX和openib可能有兼容问题

- `--disable-mpi-fortran`：可能跟系统上fortran编译器有关，不加该参数可能报错。参考[Could not determine size of CHARACTER while installing openmpi - Stack Overflow](https://stackoverflow.com/questions/49130563/could-not-determine-size-of-character-while-installing-openmpi)

## （3）安装libopenmpi-dev包

安装libopenmpi-dev主要是提供orted（该模块程序应该是OMPI用于节点间通信的daemon程序？）：

```shell
# 更新apt源，旧版本libopenmpi-dev可能与OMPI4.x有兼容性问题，导致运行时无法连接到动态库（比如common_ucx.so）
$ sudo apt-get update
$ sudo apt install libopenmpi-dev
```

**注1**：不安装orted，运行mpi程序时，可能报错：

```shell
orted: error while loading shared libraries: libopen-rte.so.40: cannot open shared object file: No such file or directory
```

可以通过`find /usr/lib -name *libopen-rte*`寻找包位置确认是否存在libopen-rte.so，参考[16.04 - mpirun: error while loading shared libraries: libopen-rte.so.12: - Ask Ubuntu](https://askubuntu.com/questions/997681/mpirun-error-while-loading-shared-libraries-libopen-rte-so-12)

**注2**：注意更新apt源，旧版本libopenmpi-dev可能与OMPI4.x有兼容性问题，导致运行时无法连接到动态库

虽然该动态库能在/usr/local/lib底下能找到，但ldd ompi却发现程序找不到），参考[unable to open mca_pml_ucx: libucp.so.0: cannot open shared object file:](https://github.com/open-mpi/ompi/issues/7461)

## （4）配置多机环境

若需要多机运行mpi程序，需要在各台机器上重复（1）~（3），同时配置master节点到worker节点的ssh免密登录

注：与配置分布式系统多机环境类似，注意设置/etc/hosts和使用相同用户名的用户（最好用root）配置环境

```shell
master$ ssh-keygen
master$ ssh-copy-id -i ~/.ssh/id_rsa.pub <worker>
# 验证免密登录
master$ ssh <username>@<worker>
```

# OMPI验证示例

参考OMPI的FAQ中对应章节执行多机任务：[OpenMPI文档 | FAQ: Running MPI jobs](https://www.open-mpi.org/faq/?category=running)

## （1）使用mpi4py官方文档程序

### 命令示例

```shell
# 代码链接：https://mpi4py.readthedocs.io/en/stable/tutorial.html#running-python-scripts-with-mpi
# 单机测试
$ mpirun -np 4 python3 script.py
# 多机测试：抓包可见TCP包，说明MPI底层使用TCP
$ mpirun -np 4 -H master:2,worker:2 \
      --mca btl_tcp_if_include enp0s8 \
      python3 script.py
```

### FAQ

**Q1**：报错`Open MPI accepted a TCP connection from what appears to be a
  another Open MPI process but cannot find a corresponding process
  entry for that peer`
  
可抓包分析，看是否有SSH报文和TCP报文，确认已经配置好ssh免密登录；

事实上，如果除lo外有多网卡，需要指定网卡。参考[OpenMPI文档 | FAQ：How do I tell Open MPI which IP interfaces / networks to use?](https://www.open-mpi.org/faq/?category=tcp#tcp-selection)、参考[cluster computing - Running MPI on two hosts - Stack Overflow](https://stackoverflow.com/questions/15072563/running-mpi-on-two-hosts)

（当初使用openib时根据官方文档尝试Soft-RoCE+OMPI+OPENIB联调，未指定Soft-RoCE网卡，一直报这个错，未解决......）

**Q2**：报错`python3: can't open file 'script.py': [Errno 2] No such file or directory`
  
个人验证后发现，可能需要所有机器上都存在相同路径的代码（？？居然由用户维持一致性？），但代码内容可以不同。抓包可见，各机器执行的都是本机代码，特定rank的print信息从tom传输到了bigger-tom

## （2）使用OSU-microbench

除了自己写demo，还有许多针对MPI测试的benchmark程序（类似rdma的perftest、nccl的nccl-test），参考[suggest a Benchmark program to compare MPICH and OpenMPI](https://stackoverflow.com/questions/5360306/suggest-a-benchmark-program-to-compare-mpich-and-openmpi)。

Intel MPI Benchmarks是针对Intel MPI的测试程序，OMPI无法使用（使用的mpipcc需要另外安装）；

OSU-microbench是针对MVAPICH的测试程序，经测试部分程序可以用OMPI运行，[测试程序官网](http://mvapich.cse.ohio-state.edu/benchmarks/)；

### 命令示例

```shell
# 根据测试程序README运行
# 单机测试
$ mpirun -np 2 \
    python3 run.py --benchmark latency --buffer numpy
# 多机测试：抓包可见TCP包
$ mpirun -np 2 -H master:1,host:1 \
      --mca btl_tcp_if_include enp0s8 \
      python3 run.py --benchmark latency --buffer numpy
```

# UCX验证示例

## （1）使用ucx_perftest

根据`ucx_perftest -h`的说明和OpenUCX文档说明，需要设置UCX_NET_DEVICES和UCX_TLS参数。可以通过`~/.bashrc`指定。（对OMPI+UCX联调，似乎只需要指定UCX_NET_DEVICES，OMPI会自动选择UCX_TLS）

如何根据`ucx_info -d`设置参数：[Frequently Asked Questions &mdash; OpenUCX documentation](https://openucx.readthedocs.io/en/master/faq.html#which-transports-does-ucx-use)

```shell
# 根据ucx_perftest -h的要求：先根据ucx_info -d设置~/.bashrc中环境变量：UCX_NET_DEVICES、UCX_TLS
export UCX_NET_DEVICES=enp0s8

# 如果ucx支持ib设备且ib设备正常，应该能看到相应信息
$ ucx_info -d

# 再运行下述测试&抓包：若使用以太网卡，抓包可见TCP包
# 指定cpu affinity，不然系统默认使用所有cpu，可能卡死
divsigma@bigger-tom$ ucx_perftest -t tag_bw -c 0 -n 50000
divsigma@tom$ ucx_perftest bigger-tom -t tag_bw -c 0 -n 50000
```

# DEMO

## （1）使用SoftRoCE协议栈，联调OMPI+UCX

如何在OMPI上通过IB协议栈通信：[OpenMPI文档 | FAQ： OpenFabrics](https://www.open-mpi.org/faq/?category=openfabrics#ompi-over-roce-ucx-pml)

很有帮助的（显示更详细运行信息的）OMPI联调参数：

- `--mca pml_base_verbose`
- `--mca pml_ucx_verbose`

### （1.1）联调mpi4py官方文档程序

#### 命令示例

```shell
# 注意：需要-x设置多机的UCX环境变量，各台机器上的~/.bashrc中的参数在多机模式下似乎不生效
mpirun -np 2 -H tom:1,bigger-tom:1 \
 --mca btl ^openib \
 --mca pml ucx \
 --mca pml_base_verbose 10 \
 --mca pml_ucx_verbose 10 \
 -x UCX_NET_DEVICES=r0:1,enp0s8 \
 -x UCX_IB_GID_INDEX=1 \
 python3 script.py
```

#### FAQ

**Q1**：为什么要`--mca btl ^openib`

为避免ucx和openib兼容问题，btl可以禁用openib：[OpenMPI文档 | FAQ：OFA device error](https://www.open-mpi.org/faq/?category=openfabrics#ofa-device-error)

**Q2**：如何设置`UCX_NET_DEVICES`

按照官方文档，只需要指定一个RDMA设备即可，但经Soft-RoCE上测试，需要增加一张以太网卡，否则UCX会一直以UD方式通信，最后报错`UD endpoint 0xc576d0 to <no debug data>: unhandled timeout error`，原因未明。

（个人测试）各种常见`UCX_NET_DEVICES`和`UCX_TLS`参数组合下ucx_perftest的表现：

```shell
# 组合1，抓到TCP
export UCX_NET_DEVICES=enp0s8
export UCX_TLS=tcp

# 组合2，抓到TCP+RRoCE的RC包
export UCX_NET_DEVICES=r0:1,enp0s8
export UCX_TLS=ud_verbs,rc_verbs,tcp

# 组合3
# 抓包：RRoCE协议的只有UD Send Only，无RC；或无RRoCE协议包
# 报错：ud_ep.c:280  Fatal: UD endpoint 0xc576d0 to <no debug data>: unhandled timeout error
export UCX_NET_DEVICES=r0:1
export UCX_TLS=ud_verbs,rc_verbs

# 组合4
# 抓包：无RRoCE协议包
# 报错：：select.c:629  UCX  ERROR   no auxiliary transport to <no debug data>: Unsupported operation
#       [bigger-tom:03190] pml_ucx.c:419  Error: ucp_ep_create(proc=0) failed: Destination is unreachable
export UCX_NET_DEVICES=r0:1
export UCX_TLS=rc_verbs
```

**Q3**： 报错`No components were able to be opened in the pml framework`

通过`--mca pml_ucx_verbose 10`和`--mca pml_base_verbose 10`查看更多报错信息，发现有`dose not support MPI_THREAD_MULTIPLE`，利用`--enable-mt`重新编译openucx。

参考：[ucx not work with openmpi4.0.3:No components were able to be opened in the pml framework](https://github.com/openucx/ucx/issues/5284)

### （1.2）联调OSU-microbenchmark程序

#### 命令示例

```shell
# 根据README使用run.py
divsigma@bigger-tom$ mpirun -np 2 -H tom:1,bigger-tom:1 \
 --mca pml ucx \
 --mca btl ^openib \
 -x UCX_NET_DEVICES=r0:1,enp0s8 \
 python3 run.py --benchmark latency --buffer numpy

# 输出，
# 抓包规律：size较小时主要是RC Send Only
#         size较大时主要是RC Send Only + RC RDMA Read Response
# OMB Python MPI Latency Test
# Size (B)      Latency (us)
0                     397.10
1                     406.88
2                     436.32
4                     421.87
8                     443.15
16                    438.04
...
262144              10749.28
524288              12516.49
1048576             58189.49
2097152            154345.07
4194304            298051.17
```

#### FAQ

