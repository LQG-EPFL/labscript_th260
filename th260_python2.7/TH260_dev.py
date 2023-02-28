#####################################################################
# TH260 device                                                      
# by Timo, 14.04.2022                                                      
#                                                                   
#####################################################################

import sys
import threading
import numpy as np
import h5py
import zmq

import ctypes as ct
from ctypes.util import find_library
import time

th260=ct.WinDLL(find_library('th260lib64'))

MAXHISTLEN = 5
TTREADMAX = 131072
T2WRAPAROUND = 33554432

tacq = 100 #snap time in ms

# Data handling classes
class TH260_POINT(ct.Structure):
    _fields_ = [("time", ct.c_uint, 25), ("channel", ct.c_uint, 6), ("special", ct.c_uint, 1)]
    
class TH260_DATA(ct.Union):
    _fields_ = [("allbits", ct.c_uint), ("bits", TH260_POINT)]

class TH260_Card(object):
    
    def __init__(self, devidx):
        self.devidx=devidx
        #parameters for event dtection
        self.binning = 0 # meaningful only in T3 mode
        self.offset = 0 # meaningful only in T3 mode
        self.tacq = tacq # in ms
        self.syncDivider = 1 # Read the manual carefully
        self.syncTriggerEdge = 1
        self.syncTriggerLevel = 100
        self.inputTriggerEdge = 1
        self.inputTriggerLevel = 100
        
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

        # Find the card:
        print("Finding counter card and connecting ...")
        self.serial_number = ct.create_string_buffer(8)
        retCode = th260.TH260_OpenDevice(self.devidx,self.serial_number)
        if retCode != 0 :
            if retCode == -1: # TH260_ERROR_DEVICE_OPEN_FAIL
                print("  %1d        no device" % self.id)
            else :
                th260.TH260_GetErrorString(self.errorString, ct.c_int(retCode))
                print("  %1d        %s" % (self.devidx, self.errorString.value.decode("utf8")))
                raise Exception('device not initialized')
        else : print('serial number is '+str(self.serial_number.value))
        
        print("Initializing TH260 in T2 mode ...")
        if th260.TH260_Initialize(self.devidx,2) != 0 : print('issue initializing')
        else : print('... initialized')

        if th260.TH260_SetInputEdgeTrg(ct.c_int(0),ct.c_int(0),ct.c_int(self.inputTriggerLevel),ct.c_int(self.inputTriggerEdge)) != 0 : print('issue setting input trigger')
        else : print('Trigger level set to '+str(self.inputTriggerLevel)+' mV with edge '+str(self.inputTriggerEdge))
        
        if th260.TH260_SetBinning(ct.c_int(0),ct.c_int(self.binning)) != 0 : print('issue setting binning')
        else : print('Binning number set to '+str(self.binning))
        
        if th260.TH260_SetSyncEdgeTrg(ct.c_int(0),ct.c_int(self.syncTriggerLevel),ct.c_int(self.syncTriggerEdge)) != 0 : print('issue setting sync trigger')
        else : print('Sync trigger level set to '+str(self.syncTriggerLevel)+' mV with edge '+str(self.syncTriggerEdge))

    def enable_input_channel(self, channel = 0) :
        if th260.TH260_SetInputChannelEnable(self.devidx,ct.c_int(channel),ct.c_int(1)) != 0 : print('issue enabling input channel')
    def disable_input_channel(self, channel = 0) :
        if th260.TH260_SetInputChannelEnable(self.devidx,ct.c_int(channel),ct.c_int(0)) != 0 : print('issue disabling input channel')
            
    def get_cnt_rate (self) :
        currentCountRate = ct.pointer(ct.c_int(122))
        if th260.TH260_GetCountRate(self.devidx,0,currentCountRate) != 0 : print('issue getting count rates')
        return currentCountRate[0]
    
    def snap (self, acqTime = None):
        if acqTime == None : acqTime = self.tacq
        """ Acquire a trace in live mode and return it as an array of arrival times """        
        self.configure_acquisition(mode='ctc')
        if th260.TH260_SetInputChannelEnable(self.devidx,ct.c_int(0),ct.c_int(1)) != 0 : print('issue enabling input channel')
        if th260.TH260_StartMeas(self.devidx,acqTime) != 0 : print('issue starting measurement')
        time.sleep(acqTime/1000. + 0.001)
        self.stop_acquisition()
        
        return 0 #self.readBuffer()

    def configure_acquisition (self, mode='gated', startedge = 'rising', stopedge='falling', gate_logic='low'):
        """
        Set Meas Control :
        first number is device # -> 0
        second number is trigger mode :
            0 -> ctc(internal counter, requires tacq parameter later) ,
            1 -> gate on C1 : acquires while C1 is active (high or low defined later)
            2 -> edge to ctc : starts at C1 edge and runs for tacq
            3 -> edge to edge : starts on C1 edge, stops on C2 edge
        third number : starting edge
            0 -> falling ; 1 -> rising
            also defines in gate mode if the gate is high (1) or low(0) (check correspondence)
        fourth number : stopping edge
            0 -> falling ; 1 -> rising
        """
        if startedge == 'rising' : startedge = 1
        elif startedge == 'falling' : startedge = 0
        if stopedge == 'rising' : stopedge = 1
        elif stopedge == 'falling' : stopedge = 0
        if gate_logic == 'low' : gate_logic = 0
        elif gate_logic == 'high' : gate_logic = 1
        if mode == 'ctc':
            if th260.TH260_SetMeasControl(self.devidx,0,0,0) != 0 : print ('issue setting trig mode')
        elif mode == 'gated' :
            if th260.TH260_SetMeasControl(self.devidx,1,gate_logic,0) != 0 : print ('issue setting trig mode')
        elif mode == 'edge to ctc' :
            if th260.TH260_SetMeasControl(self.devidx,2,startedge,0) != 0 : print ('issue setting trig mode')
        elif mode == 'edge to edge' :
            if th260.TH260_SetMeasControl(self.devidx,3,startedge,stopedge) != 0 : print ('issue setting trig mode')


    def start_acquisition(self,acqTime=None,gate_logic='low'):
        """
        acquire a triggered trace in gated mode
        """
        if acqTime == None : acqTime = self.tacq
        if th260.TH260_SetInputChannelEnable(self.devidx,ct.c_int(0),ct.c_int(1)) != 0 : print('issue enabling input channel')
        self.configure_acquisition(mode='gated',gate_logic=gate_logic)
        if th260.TH260_StartMeas(self.devidx,acqTime) != 0 : print('issue starting measurement')
        print('acquiring ...')
        return 0
        

    def stop_acquisition(self):
        if th260.TH260_StopMeas(self.devidx) != 0 : print('issue stopping measmt')
        if th260.TH260_SetInputChannelEnable(self.devidx,ct.c_int(0),ct.c_int(0)) != 0 : print('issue disabling input channel')

    def abort_acquisition(self):
        self._abort_acquisition = True

    def tryfunc(self, retcode, funcName, measRunning = False):
        """
        Error handling function, user should not interact with it
        """
        
        if retcode < 0:
            th260lib.TH260_GetErrorString(self.errorString, ct.c_int(retcode))
            print("TH260_%s error %d (%s). Aborted." % (funcName, retcode,\
                  self.errorString.value.decode("utf-8")))
            if measRunning :
                self.stop_acquisition()
            else:
                self.close()
                
    def readBuffer(self, print_flag=True):
        """
        Reads the FiFo, emptying it in the process
        The max number of TTTR records the buffer can hold is TTREADMAX = 131072
        
        returns a np array containing the time tagged records
        """
        
        times = np.array([])
        sync_times = np.array([])
        
        # Checks for FiFo overflow
        th260.TH260_GetFlags(self.devidx, ct.byref(self.flags), "GetFlags")
        if self.flags.value & 0x0002 > 0: # 0x0002 is the flag for a full fifo
            print("FiFo overflow !")
            self.stop_acquisition()
            self.close()
        
        # Read buffer
        self.full_buffer = []
        self.nRec_total = 0
        while True:
            self.buffer = (ct.c_uint * TTREADMAX)()
            self.nRecords = ct.c_int64()
            # print ('read from buffer')
            self.tryfunc(th260.TH260_ReadFiFo(self.devidx, ct.byref(self.buffer),
                                                TTREADMAX,
                                                ct.byref(self.nRecords)), "ReadFiFo", measRunning = False)
            nRec = self.nRecords.value
            self.nRec_total += nRec
            self.full_buffer.extend(self.buffer[:nRec])
            
            if nRec == 0: break
        
        # Process data
        # if self.nRec_total > 0:
        if print_flag : print("Read " + str(self.nRec_total) + " values from buffer")
        for d in self.full_buffer:
            thd = TH260_DATA(allbits = d)
            if thd.bits.channel == 0x3F: # 0x3F is 63, meaning an overflow occured, we then add the correction to the time tags
                self.oflcorrection += T2WRAPAROUND * int(thd.bits.time)
            elif int(thd.bits.special) == 1 : # a sync event happened at that time
                sync_times = np.append(sync_times, self.oflcorrection + int(thd.bits.time))
            else : # no overflow, we simply save that point as data
                times = np.append(times, self.oflcorrection + int(thd.bits.time))
        # else:
            # if print_flag : print("Found an empty buffer")
        
        self.oflcorrection=0
        
        return sync_times*250e-12, times*250e-12 # resolution is 250ps, ugly implementation but we will unlikely change TH model so why bother
    
    def close(self):
        retCode = th260.TH260_CloseDevice(self.devidx)
        if retCode != 0 : print('issue closing the card') ; print(retCode)
        else : print('card closed')
        return
    
