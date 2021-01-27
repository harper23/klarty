import os
import sys
import optparse

VERBOSE = False
control_data = ""
annotate_data = ""

def annotate(s):
#    print ("{:99}{}".format('',s))
    global annotate_data
    annotate_data = s

def vendor_request_setup(dir, bReq, wValue, wIndex, wLength, payload):
    global annotate_data
    annotate_data = ''

    if bReq == 0xA2 and wValue == 0x20: annotate("read i1")
    if bReq == 0xA2 and wValue == 0x08: annotate("read i2")
    if bReq == 0x50 and wValue == 0x00 and wLength == 4: annotate("bitstream size")
    if bReq == 0x50 and wValue == 0x00 and wLength == 1: annotate("bitstream upload result")
    if bReq == 0x10 and wValue == 0x01: annotate("enable fpga")
    if bReq == 0x60 and wValue == 0x00: annotate("unknown")
    if bReq == 0x20 and wValue == 0x48: annotate("threshold");
    if bReq == 0x20 and wValue == 0x70: annotate("PWM1");
    if bReq == 0x20 and wValue == 0x78: annotate("PWM2");
    if bReq == 0x20 and wValue == 0x02: annotate("PWM enable");    
    if bReq == 0x20 and wValue == 0x20: annotate("sampling");
    if dir == 0 and bReq == 0x20 and wValue == 0x10: annotate("trigger");
    if dir == 1 and bReq == 0x20 and wValue == 0x10: annotate("capture info");
    if dir == 0 and bReq == 0x20 and wValue == 0x00: annotate("control run");
    if dir == 1 and bReq == 0x20 and wValue == 0x00: annotate("run state");
    if bReq == 0x38 and wValue == 0x00: annotate("reset bulk state")
    if bReq == 0x20 and wValue == 0x68: annotate("fastflo would send bulk config to wValue=0x10")

    print("REQUEST {} bReq:{:02x} wValue:{:04x} wIndex:{:02x} wLength:{:2d} [{:54}] {}".format(    
      ['OUT',' IN'][dir], bReq, wValue, wIndex, wLength, control_data, annotate_data))
    
def read_csvfile(fname):
    if VERBOSE: print('Reading from {0}'.format(fname))
    data = False
    res = []
    with open(fname, 'r') as inf:
        for line in inf:
            cols = line.split(',')
            if cols.__len__() > 10:
                # cols[8]: EP 
                if cols[8] == '00' and cols[9].find('SETUP txn') > 0:
                    txn = cols[10].rstrip().split()
                    print("{}".format(cols[10].rstrip()), end='   ')
                    bReqType = int(txn[0],16)
                    bReq = int(txn[1],16)
                    wValue = int("".join(txn[2:4][::-1]),16)
                    wIndex = int("".join(txn[4:6][::-1]),16)
                    wLength = int("".join(txn[6:8][::-1]),16)
                    dir = bReqType >> 7
                    type = (bReqType and 0x60) >> 5 # 0 standard, 1 class, 2 vendor, 3 reserved
                    recipient = bReqType and 31 # 0 device, 1 interface, 2 EP, 3 other 
                    #print("bReqType:{:2x} bReq:{:2x} wValue:{:04x} wIndex:{:3d} wLength:{:2x}".format(
                    #    bReqType, bReq, wValue, wIndex, wLength), end='  ')
                    payload = cols[10].rstrip()
                    vendor_request_setup(dir, bReq, wValue, wIndex, wLength, payload)
                if cols[8] == '00' and cols[9] == 'Control Transfer':
                    global control_data
                    control_data = cols[10].rstrip()
    return res

def main(input, output):
    data = read_csvfile(input)

if __name__=="__main__":
    parser = optparse.OptionParser()
    parser.add_option('-i', '--input',   dest='input',   help='name of HEX input file')
    parser.add_option('-o', '--output',  dest='output',  help='name of BIN output file')
    parser.add_option('-v', '--verbose', dest='verbose', help='output extra status information', action='store_true', default=False)
    (options, args) = parser.parse_args()
    VERBOSE = options.verbose
    main(options.input, options.output)