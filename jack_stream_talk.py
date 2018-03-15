#!/usr/bin/env python3

"""
Create a JACK client that serves audio to jack_stream_listen.
"""

# standard imports
# import os
import sys
import json
import time
import uuid
import janus
import queue
import signal
import struct
import socket
import asyncio
import logging
import argparse
import threading
import websockets
# import collections

import numpy as np

import queue # non-standard import???
import jack

from jack_stream_common import get_ip, JACK_STREAM_VERSION

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
jack_client = jack.Client(clientname, servername=servername)

# check jack server status and possible jack_client renaming
if jack_client.status.server_started:
    logging.info('JACK server started')
if jack_client.status.name_not_unique:
    logging.warning('unique name {0!r} assigned'.format(jack_client.name))

# this is to support python2 - should we even bother?
event = threading.Event()


# helper functions for channel buffer stats
def calcrms(x):
    return np.sqrt(np.mean(x**2))
def countclips(x):
    return np.sum(abs(x) > 1.0)

async def ws_recv_json_dict(ws):
    jss = await ws.recv()
    try:
        jsd = json.loads(jss)
    except json.JSONDecodeError as de:
        logging.warning(str(de))
        return jss # binary?
    return jsd

async def ws_send_json_fields(ws, **kwargs):
    try:
        await ws.send(json.dumps(kwargs))
        return False
    except:
        return True


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
                rms  =(np.nan,)*channels,
                clips=(np,)*channels
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
    def __init__(self, wsock, wsaddr, id=None, channel=None, connected=None):
        if id        == None: id = str(uuid.uuid1())
        if channel   == None: channel = 1
        if connected == None: connected = False
        
        # shadow inputs to class variables
        self.wsock     = wsock
        self.wsaddr    = wsaddr
        self.id        = id
        self.channel   = channel
        self.connected = connected
# end ClientsType


# list of clients to be appended by handle_incoming_threads
# this list will be looped over/serviced by handle_buffers_and_clients


g_client_d = dict()
g_loopback_time = 0.0
async def handle_wsock_coro(wsock, wsuri):
    global g_client_d, g_loopback_time
    logging.debug('path = {}'.format(wsuri))

    # # check for 'back-to-back' connections from the localhost or 127.0.0.1 
    # if any(map(lambda ip: ip in wsuri, ('127.0.0.1', 'localhost'))):
    #     if time.time() - loopback_time < 5.0:
    #         pass # close things???
    #     else:
    #         loopback_time = time.time()

    # wait for 'connect' message
    while True:
        connect = await ws_recv_json_dict(wsock)
        if 'message' in connect and 'connect' == connect['message']:
            client = ClientType(wsock, wsuri, connected=True)
            g_client_d[client.id] = client
            await ws_send_json_fields(client.wsock, 
                    message        = 'connected', 
                    id             = client.id,
                    channel_select = client.channel)
            break

    # after 'connect', wait for messages of the types...
    # ('channel_select', )
    while True:
        msg = await ws_recv_json_dict(wsock)
        assert 'message' in msg
        if msg['message'] in ('channel_select',):
            try:
                g_client_d[client.id].channel = int(msg['channel_select'])
            except Exception as e:
                print(str(e))
# end async def handle_incoming


async def sendbufs_wsock_coro(bufQ, clientD):
    channel_stats = ChannelsStatsType()
    last_meta_send_time = time.time()

    while True:
        jackbufs = await bufQ.get()

        if jackbufs is None:
            break # end the thread

        # send buffers ASAP
        for client in clientD.values():
            if 1 <= client.channel and client.channel <= len(jackbufs):
                # channel-1 --> convert 1-based TO 0-based
                await client.wsock.send(jackbufs[client.channel-1])
                # FIXME, add exceptions to this in try/except ?

        # update channel statistics with 'rms' and 'clips'
        channel_stats.update_with_bufs(jackbufs)

        if time.time() - last_meta_send_time > 1.0:
            last_meta_send_time = time.time()

            meta_dict = channel_stats.collect_as_dict()
            meta_dict['format'] = dict(
                channel_count = len(jack_client.inports),
                samplerate    = jack_client.samplerate,
                samplesize    = 32,
                sampletype    = "float",
                byteorder     = "little",
                codec         = "audio/pcm")

            for client in clientD.values():
                await ws_send_json_fields(client.wsock, **meta_dict)
                # FIXME with multiple exception types!
        # end stats / meta check
    # end while True

    # close all the netclient sockets before ending thread
    for client in clientD.values():
        client.wsock.close()
# end async def sendbufs


g_wsock_loop = None
def wsock_thread_func(asyncBufQ, clientD):
    global g_wsock_loop
    # create coroutine OBJECT for incoming connections and sending data
    ws_handle_incoming = websockets.serve(handle_wsock_coro, 'localhost', port=args.port)

    # create websocket event loop
    g_wsock_loop = asyncio.get_event_loop()

    # 'put' ws_handle_incoming AND sendbufs_coro() on g_wsock_loop
    asyncio.ensure_future(ws_handle_incoming, loop=g_wsock_loop)
    asyncio.ensure_future(sendbufs_wsock_coro(asyncBufQ, clientD), loop=g_wsock_loop)

    # go!
    g_wsock_loop.run_()
# end def wsock_thread_func

# create global buffer queue, spin up 
g_buf_q = janus.Queue() # mixed mode queue, async AND sync methods
g_wsock_thread = threading.Thread( 
    target=wsock_thread_func, args=(g_buf_q.async_q, g_client_d))
g_wsock_thread.start()

@jack_client.set_process_callback
def jack_process(frames):
    # put tuple of channel buffers in to queue
    g_buf_q.sync_q.put( (inport.get_buffer() for inport in jack_client.inports) )
# end jack_process


@jack_client.set_shutdown_callback
def jack_shutdown(status, reason):
    print('JACK shutdown!')
    print('    status:', status)
    print('    reason:', reason)
    clean_up_threads_etc()
    event.set()


# create input ports
for chidx in range(channels):
    jack_client.inports.register('input_{:02d}'.format(chidx))


def clean_up_threads_etc():
    # global g_wsock_loop
    # global g_wsock_thread

    # I think this is enough to stop g_wsock_loop and g_wsock_thread...
    g_wsock_loop.call_soon_threadsafe( g_wsock_loop.stop )

    # wait for those threads to finish
    logging.debug('waiting for network/buffer g_wsock_thread to cleanly exit')
    g_wsock_thread.join()

    # incoming_thread.join()
    # bufclient_thread.join()
    logging.info('network/buffer g_wsock_thread has cleanly exited')
# end def clean_up_threads_etc()


with jack_client:
    print('\nPress Ctrl+C to stop\n')
    try:
        event.wait()
    except KeyboardInterrupt:
        logging.warning('Interrupted by user')

    clean_up_threads_etc()


# When the above with-statement is left (either because the end of the# signal buf handler thread to end
# code block is reached, or because an exception was raised inside),
# jack_client.deactivate() and jack_client.close() are called automatically.
