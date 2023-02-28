#####################################################################
#                                                                   #
# /labscript_devices/TH260/blacs_workers.py                         #
#                                                                   #
# derived from /labscript_devices/IMAQdxCamera/blacs_workers.py     #
# by Tigrane                                                        #
#                                                                   #
#####################################################################

import sys
# from time import perf_counter
import threading
import numpy as np
# from labscript_utils import dedent
# import labscript_utils.h5_lock
import h5py
# import labscript_utils.properties
import zmq

# from labscript_utils.ls_zprocess import Context
# from labscript_utils.shared_drive import path_to_local
# from labscript_utils.properties import set_attributes

import ctypes as ct
from ctypes.util import find_library
import time
#from func_timeout import func_timeout, FunctionTimedOut

# th260=ct.WinDLL(find_library('th260lib64'))

MAXHISTLEN = 5
TTREADMAX = 131072
T2WRAPAROUND = 33554432

tacq = 100 #snap time in ms

class TH260_Card(object):
    
    def __init__(self, devidx):
        self.devidx=devidx
        #parameters for event dtection
        self.binning = 0 # meaningful only in T3 mode
        self.offset = 0 # meaningful only in T3 mode
        self.tacq = tacq # in ms
        self.syncDivider = 1 # Read the manual carefully
        self.syncTriggerEdge = 0
        self.syncTriggerLevel = 500
        self.inputTriggerEdge = 1
        self.inputTriggerLevel = 500
        
        self.oflcorrection=0
        
        #parameters for data storage
        self.buffer = (ct.c_uint * TTREADMAX)()
        self.counts = [(ct.c_uint * MAXHISTLEN)()]
        self.hwSerial = ct.create_string_buffer(b"", 8)
        self.hwPartno = ct.create_string_buffer(b"", 8)
        self.hwVersion = ct.create_string_buffer(b"", 16)
        self.hwModel = ct.create_string_buffer(b"", 16)
        self.errorString = ct.create_string_buffer(b"", 40)
        self.numChannels = ct.c_int()
        self.histoLen = ct.c_int()
        self.resolution = ct.c_double()
        self.syncRate = ct.c_int()
        self.countRate = ct.c_int()
        self.flags = ct.c_int()
        self.nRecords = ct.c_int64()
        self.ctcstatus = ct.c_int()
        self.warnings = ct.c_int()
        self.warningstext = ct.create_string_buffer(b"", 16384)
                
    def readBuffer(self, print_flag=True):
        """
        Reads the FiFo, emptying it in the process
        The max number of TTTR records the buffer can hold is TTREADMAX = 131072
        
        returns a np array containing the time tagged records
        """
        
        # times = np.array([])
        # sync_times = np.array([])
        
        # # Checks for FiFo overflow
        # th260.TH260_GetFlags(self.devidx, ct.byref(self.flags), "GetFlags")
        # if self.flags.value & 0x0002 > 0: # 0x0002 is the flag for a full fifo
        #     print("FiFo overflow !")
        #     self.stop_acquisition()
        #     self.close()
        
        # # Read buffer
        # self.full_buffer = []
        # self.nRec_total = 0
        # while True:
        #     self.buffer = (ct.c_uint * TTREADMAX)()
        #     self.nRecords = ct.c_int64()
        #     # print ('read from buffer')
        #     self.tryfunc(th260.TH260_ReadFiFo(self.devidx, ct.byref(self.buffer),
        #                                         TTREADMAX,
        #                                         ct.byref(self.nRecords)), "ReadFiFo", measRunning = False)
        #     nRec = self.nRecords.value
        #     self.nRec_total += nRec
        #     self.full_buffer.extend(self.buffer[:nRec])
            
        #     if nRec == 0: break
        
        # # Process data
        # # if self.nRec_total > 0:
        # if print_flag : print("Read " + str(self.nRec_total) + " values from buffer")
        # for d in self.full_buffer:
        #     thd = TH260_DATA(allbits = d)
        #     if thd.bits.channel == 0x3F: # 0x3F is 63, meaning an overflow occured, we then add the correction to the time tags
        #         self.oflcorrection += T2WRAPAROUND * int(thd.bits.time)
        #     elif int(thd.bits.special) == 1 : # a sync event happened at that time
        #         sync_times = np.append(sync_times, self.oflcorrection + int(thd.bits.time))
        #     else : # no overflow, we simply save that point as data
        #         times = np.append(times, self.oflcorrection + int(thd.bits.time))
        # # else:
        #     # if print_flag : print("Found an empty buffer")
        
        # self.oflcorrection=0
        tres = 250e-12
        ttotal = 0.3/tres
        gate_times = np.linspace(ttotal+1, ttotal+21, num=20)
        sync_times = np.concatenate((np.array([tres, 0.1/tres, 0.2/tres, ttotal]), gate_times))

        times = np.random.randint(tres, ttotal, size=20)
        times = np.sort(times)

        return sync_times*250e-12, times*250e-12 # resolution is 250ps, ugly implementation but we will unlikely change TH model so why bother
    
    def close(self):
        print('close card')
    
