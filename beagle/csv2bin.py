import os
import sys
import optparse

VERBOSE = False

def read_hexfile(fname):
    if VERBOSE: print('Reading from {0}'.format(fname))
    data = False
    res = []
    with open(fname, 'r') as inf:
        for line in inf:
            if line.find(',02,OUT txn') > 0:
                txnpos = line.index('OUT txn')
                txn = line[txnpos:]
                hexpos = txn.find(',')
                hexstring = txn[hexpos+1:]
                res.extend(int(hex, 16) for hex in hexstring.split())
#            if line.find(',02,OUT txn.*,') > 0:
#                pos = line.index('OUT txn.*,')
#                hexstring = line[pos + 8:]
#                by = hexstring.split(' ')
#                res.extend(int(hex, 16) for hex in hexstring.split())
    if VERBOSE: print('  {0} bytes read'.format(len(res)))
    return res

def write_binfile(fname, data):
    if VERBOSE: print('Writing to {0}'.format(fname))
    with open(fname, 'wb') as outf:
        #outf.write(''.join(chr(i) for i in data))
        outf.write(bytes(data))
    if VERBOSE: print('  {0} bytes written'.format(len(data)))

def main(input, output):
    data = read_hexfile(input)
    write_binfile(output, data)

if __name__=="__main__":
    parser = optparse.OptionParser()
    parser.add_option('-i', '--input',   dest='input',   help='name of HEX input file')
    parser.add_option('-o', '--output',  dest='output',  help='name of BIN output file')
    parser.add_option('-v', '--verbose', dest='verbose', help='output extra status information', action='store_true', default=False)
    (options, args) = parser.parse_args()
    VERBOSE = options.verbose
    main(options.input, options.output)