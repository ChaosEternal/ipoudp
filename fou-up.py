#!/usr/bin/env python2
import sys, os, popen2, csv


class Positioning:
    def __init__(self, realip = None, intraip = None):
        if realip is None:
            try:
                fp = file("%s/.realip"%(os.getenv("HOME")), "r")
                self.realip = fp.read().strip()
                fp.close()
            except IOError:
                self.realip = os.popen('curl -s https://ifconfig.co').read().strip()
                try:
                    fp = file("%s/.realip"%(os.getenv("HOME")), "w")
                    fp.write("%s\n"%self.realip)
                    fp.close()
                except:
                    pass
        else:
            self.realip = realip
        self.intraip = self.realip
        if intraip is None:
            intras = os.popen('hostname -i').read().strip().split(' ')
            for i in intras:
                if i.find('127.0') == 0:
                    continue
                self.intraip = i
                break
        else:
            self.intraip = intraip
    def myrealip(self):
        return self.realip
    def myintraip(self):
        return self.intraip
        

class LinkException(Exception):
    pass

class Link:
    def __init__(self, linkid, sides = [], bridges = [], port = 0,
                 lrport = 0, lfport = 0, bupport = 0, bdownport = 0,
                 mtu=1400):
        if len(sides) > 1:
            raise LinkException("Link can not has more than two sides")
        self.sides = [ x for x in sides ]
        self.bridges = [ x for x in bridges ]
        self.port = port
        self.lfport = lfport
        self.lrport = lrport
        self.linkid = linkid
        self.bupport = bupport
        self.bdownport = bdownport
        self.mtu = mtu
    def search_realip(self, realip):
        if len(self.sides) != 2:
            raise LinkException("Link must have two sides, but now have %d sides."%len(self.sides))
        for s in self.sides:
            if s.realip == realip:
                return s
        return None
    def search_bridge(self, realip):
        for b in self.bridges:
            if b.realip == realip:
                return b
        return None
    def start_link(self, pos = None, monitrc = None):
        if monitrc is None:
            def dummymonitrc(cmd):
                print " ".join(cmd)
            monitrc = dummymonitrc
        if pos is None:
            pos = Positioning()
        myip = pos.myrealip()
        myintraip = pos.myintraip()
        side = self.search_realip(myip)
        if (self.port == 0 or self.lfport == 0 or self.lrport == 0 or
            self.bupport == 0 or self.bdownport == 0):
            raise LinkException("Link must have port, lrport and lfport defined")
        bridge = self.search_bridge(myip)
        if side is not None:
            side.intraip = myintraip
            self.start_link_side(side, monitrc)
        if bridge is not None:
            bridge.intraip = myintraip
            self.start_link_bridge(bridge, monitrc)
    def get_other_side(self, side):
        for s in self.sides:
            if s.role != side.role:
                return s
    def start_link_side(self, side, monitrc):
        tunname = "tun-fou-%s"%self.linkid
        oppo_side = self.get_other_side(side)
        cmd = ["socat", tunname, self.port,
               self.lfport, side.vip, oppo_side.vip]
        monitrc(cmd)
        myintra = side.intraip
        if myintra is None:
            myintra = side.realip
        cmd = ['samplicate',"rptr-%s"%tunname, self.lfport,
               '127.0.0.1', "%s/%d"%(oppo_side.realip, self.lrport) ]
        if side.role == 'up':
            bport = self.bupport
        else:
            bport = self.bdownport
        for b in self.bridges:
            cmd.append("%s/%d"%(b.realip, bport))
        monitrc(cmd)

        cmd = ['samplicate', "rptr-%s"%tunname, self.lrport,
               '%s'%myintra, '127.0.0.1/%d'%self.port]
        monitrc(cmd)
    def start_link_bridge(self, bridge, monitrc):
        upip = None
        downip = None
        for s in self.sides:
            if s.role == 'up':
                upip = s.realip
            if s.role == 'down':
                downip = s.realip
        if upip is None or downip is None:
            raise LinkException("not enough sides")
        for p, ip in [(self.bupport, downip), (self.bdownport, upip)]:
            cmd = ['samplicate', "blnk-%s"%self.linkid,  p,
                   "%s"%bridge.intraip, "%s/%d"%(ip, self.lrport)]
            monitrc(cmd)
        
class SideException(Exception):
    pass
class Side:
    def __init__(self, role, vip, realip, intraip = None):
        if role not in ["up", "down"]:
            raise SideException("invalid role")
        self.role = role
        self.vip = vip
        self.realip = realip
        self.intraip = intraip
        

class Bridge:
    def __init__(self, realip, intraip = None):
        self.realip = realip
        self.intraip = intraip

class Monitrc():
    def __init__(self, tunrunner="socat", rptr = "samplicate", opath=None):
        self.tunrunner = tunrunner
        self.rptr = rptr
        self.opath = opath
        pass
    def _writer(self, rc, tag):
        if self.opath is None:
            print rc
            return
        with file("%s/cfu-%s.cfg"%(self.opath, tag), "w") as rcfile:
            rcfile._write(rc)
    def _gen_tun(self, tunname, lrport, lfport, vip, vippeer):
        rc = """
# tun starter for {tunname}, port={lrport}, lfport={lfport}, vip={vip}, peer={vippeer}
check process runtun-{tunname:s} with pidfile /var/run/runtun-{tunname:s}.pid
        start = "/bin/bash -c 'socat -L /var/run/runtun-{tunname:s}.pid\\
                 TUN,iff-pointopoint,iff-up,tun-type=tun,tun-name={tunname:s}\\
                 UDP-RECV:{lrport:d}\!\!UDP-SEND:127.0.0.1:{lfport:d} & 
                 sleep 1
                 ip link set {tunname:s} mtu 1400
                 ip ad add {vip:s} peer {vippeer:s} dev {tunname:s} '"
        stop  = "/usr/bin/pkill -F /var/run/runtun-{tunname:s}.pid"
""".format(tunname=tunname, lrport=lrport, lfport=lfport, vip=vip, vippeer=vippeer)
        tag = "runtune-%s"%tunname
        self._writer(rc, tag)
    def _gen_rptr(self, tunname, portself, ipself, remote ):
        tag = "%s-%d"%(tunname, portself)
        rc = """
# forwarder for {tunname}-{portself}
check process {tag} with pidfile /var/tmp/rptr-{portself:d}.pid
        start = "/usr/local/bin/samplicate -f -m /var/tmp/rptr-{portself:d}.pid  -p {portself:d} -s {ipself:s} {remote:s}"
        stop = "/usr/bin/pkill -F /var/tmp/rptr-{portself:d}.pid"
""".format(tag=tag, tunname=tunname, portself=portself, ipself=ipself, remote=remote)
        self._writer(rc, tag)
    def __call__(self, cmd):
        if cmd[0] == self.tunrunner :
            self._gen_tun(cmd[1], cmd[2], cmd[3], cmd[4], cmd[5])
        if cmd[0] == self.rptr:
            self._gen_rptr(cmd[1], cmd[2], cmd[3], " ".join(cmd[3:]))
            
def links_factory(links_tbl, links_ports_tbl, links_bridges_tbl):
    """ return: dict of Link"""
    l = {}
    for i in links_ports_tbl:
        lid = i[0]
        l[lid] = Link(lid, sides = [], bridges = [],
                      port = int(i[1]),
                      lrport = int(i[2]),
                      lfport = int(i[3]),
                      bupport = int(i[4]),
                      bdownport = int(i[5]))
    for i in links_bridges_tbl:
        lid = i[0]
        l[lid].bridges.append(Bridge(i[1]))
    for i in links_tbl:
        lid = i[0]
        l[lid].sides.append(Side(i[1], i[2], i[3]))
    return l
        
def links_all_table_parse(links_tbl, links_ports_tbl, links_bridges_tbl, delim = '|'):
    """
     Data Flow:
     | a vip | a real ip | a listen port | a to b port| bridge up port| bridge down port | b to a port | b listen port | b real ip | b vip |
        +-------------->>---------------------^  +---->>------^ +------------->>-----------------------------^ +----------->>----------^
          ^-----------<<-----* ^------------------------<<----------------+ ^-------<<-------+ ^------------------<<--------------------+

     links_ports_tbl
     | link | port  | lrport | lf port | bridge up | bridge down |
     | 1    | 87676 | 7676   | 87677   | 7676      | 7677        |

     links_tbl
     | link | side | vip           | real ip         |
     | 1    | up   | 192.168.xxx.xxx | xxx.xxx.xxx.xxx  |
     | 1    | down | 192.168.xxx.yyy | yyy.yyy.yyy.yyy   |
    
     links_bridges_tbl
     | link | bridge          |
     | 1    | xxx.xxx.xxx.zzz  |
    """

    def sns_factory(delim = '|'):
        def split_n_strip(x):
            return map(lambda y: y.strip(), x.split(delim))[1:][:-1]
        return split_n_strip

    return tuple((map(sns_factory(delim), (x.strip()).split('\n')[1:])
                  for x in (links_tbl, links_ports_tbl, links_bridges_tbl) ))


def main():
    import sys
    l = {}
    execfile(sys.argv[1], {}, l)
    links, links_ports, links_bridges = links_all_table_parse(l["links_tbl"], l["links_ports_tbl"], l["links_bridges_tbl"])
    links_dict = links_factory(links, links_ports, links_bridges)
    p = Positioning()
    print "## === Acting", p.realip, p.intraip
    for ll in links_dict.values():
        ll.start_link(p, Monitrc())

    
if __name__ == "__main__":
    main()
