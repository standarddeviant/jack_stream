
'''FIXME add jack_stream_utils doc string'''

import json
import struct
import logging

JACK_STREAM_VERSION = '0.01'

def msgify_pkt(prevpkt, curpkt, msgtypes=('META', 'DATA'), log=logging):
    '''FIXME add msgify_pkt doc string'''
    prevpkt.extend(curpkt) # bytearray
    msgtype = ''
    for mtloop in msgtypes:
        try:
            metaidx = prevpkt.index(bytearray(mtloop.encode()))
            msgtype = mtloop
        except:
            continue

    if not msgtype:
        log.warning('out of sync, should automatically re-sync')
        return ('WARNING', None)

    # if we get here, try to grab prevpkt len, and then following data
    # if errors, just return None and wait for client.prevpkt to 'grow'
    try:
        pktlen = struct.unpack('i', prevpkt[metaidx+4:metaidx+4+4])[0]
        barr = prevpkt[metaidx+4+4:metaidx+4+4+pktlen]

        # if we get here, return of some data should be guaranteed
        # so we can remove the msgtype, pktlen, and data from client.prevpkt
        del(prevpkt[0:metaidx+4+4+pktlen])

    except:
        log.warning('not enough data for packet, waiting for more data')
        return ('WARNING', None)

    if msgtype == 'META': # try to json decode the meta object and return it
        try:
            return ('META', json.loads(barr.decode()))
        except:
            log.error('unable to decode json data from META msg')
            return ('ERROR', None)
    else:
        return(msgtype, barr)
# end msgify_pkt


import socket
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP