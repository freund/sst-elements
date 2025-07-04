import sst
import math

# globals
CPUQuads = 2  # "Quads" per CPU
PIMQuads = 1  # "Quads per PIM
PIMs = 2      # number of PIMs
ccLat = "5ns" # cube to cube latency i.e. PIM to PIM

vaultsPerCube = 8
fakeCPU_DC = 0
fakePIM_DC = 0
coreNetBW = "36GB/s"
memNetBW = "36GB/s"
xbarBW = coreNetBW
flit_size = "72B"
coherence_protocol = "MESI"
busLat = "50ps"
netLat = "6ns"
useAriel = 1
useVaultSim = 1
baseclock = 1500  # in MHz
clock = "%g MHz"%(baseclock)
l2clock = "%g MHz"%(baseclock *0.25)
memclock = "500 MHz"
memDebug = 0
memDebugLevel = 6

rank_size = 512 // PIMs
interleave_size = 1024*4
corecount = (CPUQuads + (PIMQuads * PIMs)) * 4

class corePorts:
    def __init__(self):
        self._next = 0
    def nextPort(self):
        res = self._next
        self._next = self._next + 1
        return res
coreCtr = corePorts()

# common
memParams = {
        "mem_size": str(rank_size) + "MiB",
        "access_time" : "50ns"
        }
l1PrefetchParams = { }
l2PrefetchParams = {
    #"prefetcher": "cassini.StridePrefetcher",
    #"reach": 8
    }
cpuParams = {
    "verbose" : "0",
    "workPerCycle" : "1000",
    "commFreq" : "100",
    "memSize" : "0x1000000",
    "do_write" : "1",
    "num_loadstore" : "100000"
    }
#figure number of local ports
if CPUQuads == PIMQuads + 1:
    localPorts = CPUQuads
elif CPUQuads > PIMQuads + 1:
    localPorts = CPUQuads
    fakePIM_DC = localPorts - PIMQuads - 1
else:
    localPorts = PIMQuads + 1
    fakeCPU_DC = localPorts - CPUQuads

routerParams = {"topology": "merlin.torus",
                "link_bw": coreNetBW,
                "xbar_bw": xbarBW,
                "input_latency": "6ns",
                "output_latency": "6ns",
                "input_buf_size" : "4KiB",
                "output_buf_size" : "4KiB",
                "flit_size" : flit_size,
                "torus.shape" : PIMs+1,
                "torus.width" : 1,
                "torus.local_ports": localPorts ,
                "num_ports" : localPorts + 2}

def makeAriel():
    ariel = sst.Component("a0", "ariel.ariel")
    ariel.addParams({
        "verbose" : 0,
        "clock" : clock,
        "maxcorequeue" : 256,
        "maxissuepercycle" : 2,
        "pipetimeout" : 0,
        #"executable" : "/home/student/tlvlstream/sstgups",
        #"executable" : "/home/student/tlvlstream/ministream",
        "executable" : "/home/student/tlvlstream/miniFE_openmp_opt/miniFE.x",
        "corecount" : corecount,
        "arielmode" : 0,
        "arieltool": "/home/student/sst-simulator/tools/ariel/fesimple/fesimple_r.so"
            })
    coreCounter = 0
    return ariel

def doQuad(quad, cores, rtr, rtrPort, netAddr):
    sst.pushNamePrefix("q%d"%quad)

    bus = sst.Component("membus", "memHierarchy.Bus")
    bus.addParams({
        "bus_frequency" : clock,
        "bus_latency_cycles" : 1,
        })

    for x in range(cores):
        core = 4*quad + x
        # make the core
        if (useAriel == 0):
            coreObj = sst.Component("cpu_%d"%core,"memHierarchy.streamCPU")
            coreObj.addParams(cpuParams)
        # make l1
        l1id = sst.Component("l1cache_%d"%core, "memHierarchy.Cache")
        l1id.addParams({
            "coherence_protocol": coherence_protocol,
            "cache_frequency": clock,
            "replacement_policy": "lru",
            "cache_size": "8KB",
            "associativity": 8,
            "cache_line_size": 64,
            "access_latency_cycles": 2,
            "L1": 1,
            "debug": memDebug,
            "debug_level" : 6,
            })
        l1id.addParams(l1PrefetchParams)
        #connect L1 & Core
        if useAriel:
            arielL1Link = sst.Link("core_cache_link_%d"%core)
            portName = "cache_link_" + str(coreCtr.nextPort())
            arielL1Link.connect((ariel, portName,
                                 busLat),
                                (l1id, "highlink", busLat))
        else:
            coreL1Link = sst.Link("core_cache_link_%d"%core)
            coreL1Link.connect((coreObj, "mem_link", busLat),
                               (l1id, "highlink", busLat))
        membusLink = sst.Link("cache_bus_link_%d"%core)
        membusLink.connect((l1id, "lowlink", busLat), (bus, "highlink%d"%x, busLat))

    #make the L2 for the quad cluster
    l2 = sst.Component("l2cache_nid%d"%netAddr, "memHierarchy.Cache")
    l2.addParams({
        "coherence_protocol": coherence_protocol,
        "cache_frequency": l2clock,
        "replacement_policy": "lru",
        "cache_size": "128KB",
        "associativity": 16,
        "cache_line_size": 64,
        "access_latency_cycles": 23,
        "mshr_num_entries" : 4096, #64,   # TODO: Cesar will update
        "L1": 0,
        "debug_level" : 6,
        "debug": memDebug
        })
    l2.addParams(l2PrefetchParams)
    l2_nic = l2.setSubComponent("lowlink", "memHierarchy.MemNIC")
    l2_nic.addParams({
        "network_bw" : coreNetBW,
        "group" : 1,
        })

    link = sst.Link("l2cache_%d_link"%quad)
    link.connect((l2, "highlink", busLat), (bus, "lowlink0", busLat))
    link = sst.Link("l2cache_%d_netlink"%quad)
    link.connect((l2_nic, "port", netLat), (rtr, "port%d"%(rtrPort), netLat))

    sst.popNamePrefix()

# make a cube
def doVS(num, cpu) :
    sst.pushNamePrefix("cube%d"%num)
    ll = sst.Component("logicLayer", "vaultsim.logicLayer")
    ll.addParams ({
            "clock" : """500Mhz""",
            "vaults" : str(vaultsPerCube),
            "llID" : """0""",
            "bwlimit" : """32""",
            "LL_MASK" : """0""",
            "terminal" : """1"""
            })
    fromCPU = sst.Link("link_cpu_cube");
    fromCPU.connect((cpu, "cube_link", ccLat),
                    (ll, "toCPU", ccLat))
    #make vaults
    for x in range(0, vaultsPerCube):
        v = sst.Component("ll.Vault"+str(x), "vaultsim.vaultsim")
        v.addParams({
                "clock" : """750Mhz""",
                "VaultID" : str(x),
                "numVaults2" : math.log(vaultsPerCube,2)
                })
        ll2V = sst.Link("link_ll_vault" + str(x))
        ll2V.connect((ll,"bus_" + str(x), "1ns"),
                     (v, "bus", "1ns"))
    sst.popNamePrefix()

def doFakeDC(rtr, nextPort, netAddr, dcNum):
    memory = sst.Component("fake_memory", "memHierarchy.MemController")
    memory.addParams({
            "clock": memclock,
            "debug": memDebug
            })
    memory = memctrl.setSubComponent("backend", "memHierarchy.simpleMem")
    # use a fixed latency
    memory.addParams(memParams)
    # add fake DC
    dc = sst.Component("dc_nid%d"%netAddr, "memHierarchy.DirectoryController")
    print(("DC nid%d\n %x to %x\n iSize %x iStep %x" % (netAddr, 0, 0, 0, 0)))
    dc.addParams({
            "coherence_protocol": coherence_protocol,
            "network_bw": memNetBW,
            "addr_range_start": 0,
            "addr_range_end":  1,
            "interleave_size": 0//1024,   # in KB
            "interleave_step": 0,         # in KB
            "entry_cache_size": 128*1024, #Entry cache size of mem/blocksize
            "clock": memclock,
            "debug": memDebug,
            })
    dc_nic = dc.setSubComponent("highlink", "memHierarchy.MemNIC")
    dc_nic.addParams({
        "network_bw" : memNetBW,
        "group" : 2,
        })

    #wire up
    memLink = sst.Link("fake_mem%d_link"%dcNum)
    memLink.connect((memctrl, "highlink", busLat), (dc, "lowlink", busLat))
    netLink = sst.Link("fake_dc%d_netlink"%dcNum)
    netLink.connect((dc_nic, "port", netLat), (rtr, "port%d"%(nextPort), netLat))

def doDC(rtr, nextPort, netAddr, dcNum):
    start_pos = (dcNum * interleave_size);
    interleave_step = PIMs*(interleave_size//1024) # in KB
    end_pos = start_pos + ((512*1024*1024)-(interleave_size*(PIMs-1)))

    # add memory
    #TODO: add vaults
    memctrl = sst.Component("memory", "memHierarchy.MemController")
    memctrl.addParams({
            "clock": memclock,
            "debug": memDebug
            })
    if (useVaultSim == 1):
        # use vaultSim
        memory = memctrl.setSubComponent("backend", "memHierarchy.vaultsim")
        memory.addParams({"mem_size": str(rank_size) + "MiB"})
        doVS(dcNum, memory)
    else:
        # use a fixed latency
        memctrl.setSubComponent("backend", "memHierarchy.simpleMem")
        memory.addParams(memParams)

    # add DC
    dc = sst.Component("dc_nid%d"%netAddr, "memHierarchy.DirectoryController")
    print(("DC nid%d\n %x to %x\n iSize %x iStep %x" % (netAddr, start_pos, end_pos, interleave_size, interleave_step)))
    dc.addParams({
            "coherence_protocol": coherence_protocol,
            "network_bw": memNetBW,
            "addr_range_start": start_pos,
            "addr_range_end":  end_pos,
            "interleave_size": interleave_size//1024,   # in KB
            "interleave_step": interleave_step,         # in KB
            "entry_cache_size": 128*1024, #Entry cache size of mem/blocksize
            "clock": memclock,
            "debug": memDebug,
            })
    dc_nic = dc.setSubComponent("highlink", "memHierarchy.MemNIC")
    dc_nic.addParams({
        "network_bw" : memNetBW,
        "group" : 2,
        })
    #wire up
    memLink = sst.Link("mem%d_link"%dcNum)
    memLink.connect((memctrl, "highlink", busLat), (dc, "lowlink", busLat))
    netLink = sst.Link("dc%d_netlink"%dcNum)
    netLink.connect((dc_nic, "port", netLat), (rtr, "port%d"%(nextPort), netLat))

def doCPU():
    sst.pushNamePrefix("cpu")
    # make the router
    rtr = sst.Component("cpuRtr", "merlin.hr_router")
    rtr.addParams(routerParams)
    rtr.addParams({"id" : 0})
    nextPort = 2 #0,1 are reserved for router-to-router
    nextAddr = 0 # Merlin-level network address

    #make the quads
    for x in range(CPUQuads):
        doQuad(x, 4, rtr, nextPort, nextAddr)
        nextPort += 1
        nextAddr += 1

    #fake DCs
    for x in range(fakeCPU_DC):
        doFakeDC(rtr, nextPort, nextAddr, -1)
        nextPort += 1
        nextAddr += 1

    sst.popNamePrefix()
    return rtr

def doPIM(pimNum, prevRtr):
    sst.pushNamePrefix("pim%d"%(pimNum))
    #make the router
    rtr = sst.Component("pimRtr" + str(pimNum), "merlin.hr_router")
    rtr.addParams(routerParams)
    rtr.addParams({"id" : pimNum+1})
    nextPort = 2 #0,1 are reserved for router-to-router
    nextAddr = (pimNum+1)*localPorts # Merlin-level network address

    #make the quads
    for x in range(PIMQuads):
        doQuad(x, 4, rtr, nextPort, nextAddr)
        nextPort += 1
        nextAddr += 1

    # real DC
    doDC(rtr, nextPort, nextAddr, pimNum)
    nextPort += 1
    nextAddr += 1

    #fake DCs
    for x in range(fakePIM_DC):
        doFakeDC(rtr, nextPort, nextAddr, pimNum)
        nextPort += 1
        nextAddr += 1

    # connect to chain
    wrapLink = sst.Link("p%d"%pimNum)
    wrapLink.connect((prevRtr,"port0", netLat),
                     (rtr, "port1", netLat))

    sst.popNamePrefix()
    return rtr


# "MAIN"

# Define SST core options
sst.setProgramOption("partitioner", "self")
#sst.setProgramOption("stop-at", "2000 us")

#if needed, create the ariel component
if useAriel:
    ariel = makeAriel()

#make the CPU
cpuRtr = doCPU()

#make the PIMs
prevRtr = cpuRtr
for x in range(PIMs):
    prevRtr = doPIM(x, prevRtr)

# complete the torus
wrapLink = sst.Link("wrapLink")
wrapLink.connect((prevRtr,"port0", netLat),
                 (cpuRtr, "port1", netLat))
