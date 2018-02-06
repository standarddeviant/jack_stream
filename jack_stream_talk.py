#!/usr/bin/env python3

"""Create a JACK client that serves audio to jack_stream_listen.

This is somewhat modeled after the "thru_client.c" example of JACK 2:
http://github.com/jackaudio/jack2/blob/master/example-clients/thru_client.c

If you have a microphone and loudspeakers connected, this might cause an
acoustical feedback!

"""
# standard imports
# import os
import sys
import json
import time
import signal
import struct
import socket
import logging
import argparse
import threading
# import collections

import numpy as np

import queue # non-standard import???
import jack

from jack_stream_utils import msgify_pkt

if sys.version_info < (3, 0):
    # In Python 2.x, event.wait() cannot be interrupted with Ctrl+C.
    # Therefore, we disable the whole KeyboardInterrupt mechanism.
    # This will not close the JACK client properly, but at least we can
    # use Ctrl+C.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
else:
    # If you use Python 3.x, everything is fine.
    pass


 # create arg parser
parser = argparse.ArgumentParser(description='Process args for jack_stream_talk.py')

parser.add_argument('-c', '--channels', type=int, default=2,\
        help = "number of channels to serve")

parser.add_argument('-n', '--name', type=str, default='jack_stream_talk', \
        help = "name of jack-client")

parser.add_argument('-p', '--port', type=int, default=4242, \
        help = "port to listen on")

parser.add_argument('--loglevel', default='info', \
        choices=['debug', 'info', 'warning', 'error'])

# parse args
args = parser.parse_args()

# init things and set settings according to args
logging.root.setLevel(args.loglevel.upper())
clientname = args.name
servername = None
channels = args.channels
port = args.port
client = jack.Client(clientname, servername=servername)

# check jack server status and possible client renaming
if client.status.server_started:
    logging.info('JACK server started')
if client.status.name_not_unique:
    logging.warning('unique name {0!r} assigned'.format(client.name))

# this is to support python2 - should we even bother?
event = threading.Event()


# helper functions for channel buffer stats
def calcrms(x):
    return np.sqrt(np.mean(x**2))
def countclips(x):
    return np.sum(abs(x) > 1.0)

class ChannelsStatsType:
    def __init__(self, rms=None, clips=None):
        if list != type(rms): rms=list()
        if list != type(clips): clips=list()

        # shadow inputs to class variables
        self.rms = rms
        self.clips = clips
    
    def clear(self):
        self.rms, self.clips = [], []
    
    def update_with_bufs(self, jackbufs):
        # make numpy arrays for calculating stats
        jackarrs = tuple(np.frombuffer(jb, np.dtype('float32')) 
            for jb in jackbufs)

        self.rms.append( tuple((calcrms(ja) for ja in jackarrs)) )
        self.clips.append( tuple((countclips(ja) for ja in jackarrs)) )

    def collect_as_dict(self):
        logging.debug('rms = {}'.format(self.rms))
        logging.debug('clips = {}'.format(self.clips))

        if len(self.rms) <= 0 or len(self.clips) <= 0:
            outp = dict(
                rms  =(nan,)*channels,
                clips=(nan,)*channels
            )
        else:
            outp = dict(
                rms  =np.mean(np.array(self.rms), 0).tolist(),
                clips=np.sum(np.array(self.clips), 0).tolist()
            )

        self.clear()
        return outp
# end ChannelsStatsType


class ClientType:
    def __init__(self, sock, addr, channel=None, pkt=None):
        if channel == None: channel = 1
        if pkt     == None: pkt     = bytearray()
        
        # shadow inputs to class variables
        self.sock    = sock
        self.addr    = addr
        self.channel = channel
        self.pkt     = pkt
# end ClientsType


# list of clients to be appended by handle_incoming_threads
# this list will be looped over/serviced by handle_buffers_and_clients
client_list = []


def handle_incoming_connections():
    bind_ip = '0.0.0.0'
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server.bind((bind_ip, port))
    server.listen()
    logging.info('Waiting for connections on {}:{}'.format(bind_ip, port))

    while True:
        (client_sock, client_addr) = server.accept()

        logging.info('connected client_addr is {}'.format(client_addr))
        logging.info('client_list ='.format(
            ''.join('\n    {}'.format(c.addr[0]) for c in client_list)))

        # if we connect back to ourself, then break while loop
        if client_addr[0] in ('localhost', '127.0.0.1'):
            client_sock.close() # close the socket just used for signalling
            server.close() # close incoming listener socket
            break

        logging.info('Accepted connection from {}:{}'.format(
            client_addr[0], client_addr[1]))

        # set client to blocking
        client_sock.setblocking(False)

        # create client object for handle_buffers_and_clients
        client_list.append(
            ClientType(client_sock, client_addr, 1, bytearray())
        )
#end handle_incoming_connections


# start thread for handle_incoming_connections
incoming_thread = threading.Thread(target=handle_incoming_connections)
incoming_thread.start()


gBufQ = queue.Queue()
def handle_buffers_and_clients():
    channel_stats = ChannelsStatsType()
    last_stats_send_time = time.time()

    while True:
        # pull a buffer, this is a blocking call
        jackbufs = gBufQ.get()

        if jackbufs is None:
            break # end the thread

        # send buffers ASAP
        for client in client_list:
            if client.channel > 0:
                try:
                    client.sock.send(
                        bytearray('DATA'.encode()) +
                        struct.pack('<i', len(jackbuf[client.channel-1])) +
                        jackbuf[client.channel-1]) # 1-based vs. 0-based
                except:
                    pass # FIXME with multiple exception types!
                    # tuple index out of bounds
                    # client socket issue
                    # etc...

        # update channel statistics with 'rms' and 'clips'
        channel_stats.update_with_bufs(jackbufs)

        if time.time() - last_stats_send_time > 1.0:
            last_stats_send_time = time.time()
            stats_dict = channel_stats.collect_as_dict()

            logging.debug(stats_dict)
            stats_str = json.dumps(stats_dict)
            
            for client in client_list:
                try:
                    client.sock.send(
                        bytearray('META'.encode()) +
                        struct.pack('<i', len(stats_str.encode())) +
                        bytearray(stats_str.encode()))
                except:
                    pass # FIXME with multiple exception types!
                    # tuple index out of bounds
                    # client socket issue
                    # etc...
        # end stats / meta check


        # FIXME, should we yield here????
        # or set thread priorities so jack thread has higher priority...

        # check if clients sent control information on the sockets
        for client in client_list:
            cur_pkt = client.sock.recv(1024)
            if cur_pkt:
                (msgtype, cur_msg) = msgify_pkt(client, cur_pkt)
                if cur_msg and msgtype == 'META' and 'channel_select' in cur_msg:
                    # update channel
                    client.channel = cur_msg['channel_select']

    # end while True

    # close all the client sockets before ending thread
    for client in client_list:
        client.sock.close()
# end def handle_buffers_and_clients


# end handle_buffers_and_clients
bufclient_thread = threading.Thread(target=handle_buffers_and_clients)
bufclient_thread.start()


@client.set_process_callback
def jack_process(frames):
    # put tuple of channel buffers in to queue
    gBufQ.put( (inport.get_buffer() for inport in client.inports) )
# end jack_process


@client.set_shutdown_callback
def jack_shutdown(status, reason):
    print('JACK shutdown!')
    print('    status:', status)
    print('    reason:', reason)
    clean_up_threads_etc()
    event.set()


# create input ports
for chidx in range(channels):
    client.inports.register('input_{:02d}'.format(chidx))


def clean_up_threads():
    # signal incoming_thread AND bufclient_thread to end
    tmpsock = socket.socket().connect(('localhost', port))
    gBufQ.put(None) # signal buf handler thread to end

    # wait for those threads to finish
    logging.debug('waiting for network and buffer threads to cleanly exit')
    incoming_thread.join()
    bufclient_thread.join()
    logging.info('network and buffer threads cleanly exited')


with client:
    logging.info('Press Ctrl+C to stop')
    try:
        event.wait()
    except KeyboardInterrupt:
        logging.warning('Interrupted by user')

    clean_up_threads()


# When the above with-statement is left (either because the end of the
# code block is reached, or because an exception was raised inside),
# client.deactivate() and client.close() are called automatically.
