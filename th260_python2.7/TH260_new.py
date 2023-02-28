#####################################################################
#                                                                   
# /labscript_devices/TH260.py                     
#                                                                   
# adapted from /labscript_devices/IMAQdxCamera/labscript_devices.py 
#                                                      
# Timo Zwettler, 11.04.2022                                                                  
#####################################################################
from __future__ import print_function
import sys
from labscript_devices import labscript_device, BLACS_tab, BLACS_worker
from labscript import Device, Trigger, TriggerableDevice, set_passed_properties, LabscriptError
import numpy as np
import labscript_utils.h5_lock
import h5py


@labscript_device
class TH260_new(TriggerableDevice):
    description = 'TimeHarp 260 Nano counter card from PicoQuant'
    
    allowed_children =[]
    trigger_edge_type = 'rising'
    minimum_recovery_time = 0

    @set_passed_properties(
        property_names={
            "connection_table_properties": ['devidx'
            ],
            "device_properties": ["stop_acquisition_timeout"
            ],
        }
    )
    
    def __init__(
            self,
            name,
            parent_device, connection,
            gate_device, gate_connection,
            devidx,
            trigger_duration=1e-3,
            stop_acquisition_timeout=5.0,
            **kwargs
        ) :

        self.trigger_duration = trigger_duration
        self.exposures = []
        self.BLACS_connection = devidx
        self.gate_device = gate_device
        self.gate_connection = gate_connection
        self.tmin= 0.
        self.tmax = 0.
        self.n_exposures = 0
        self.gate_delay=5e-3
        self.code_generated = 0
        
        if None in [parent_device, connection] and not parentless:
            raise LabscriptError('No parent specified. If this device does not require a parent, set parentless=True')
        if isinstance(parent_device, Trigger):
            if self.trigger_edge_type != parent_device.trigger_edge_type:
                raise LabscriptError('Trigger edge type for %s is \'%s\', ' % (name, self.trigger_edge_type) + 
                                      'but existing Trigger object %s ' % parent_device.name +
                                      'has edge type \'%s\'' % parent_device.trigger_edge_type)
            self.trigger_device = parent_device
        elif parent_device is not None:
            # Instantiate a trigger object to be our parent:
            self.trigger_device = Trigger(name + '_trigger', parent_device, connection, self.trigger_edge_type)
            parent_device = self.trigger_device
            connection = 'trigger'

        
        if isinstance(gate_device, Trigger):
            if self.trigger_edge_type != gate_device.trigger_edge_type:
                raise LabscriptError('Trigger edge type for %s is \'%s\', ' % (name, self.trigger_edge_type) + 
                                      'but existing Trigger object %s ' % gate_device.name +
                                      'has edge type \'%s\'' % gate_device.trigger_edge_type)
            self.gate_device = gate_device
        elif gate_device is not None:
            # Instantiate a gate object :
            # print(gate_device, gate_connection)
            self.gate_device = Trigger(name + '_gate', gate_device, gate_connection, self.trigger_edge_type)
            gate_device = self.gate_device
            gate_connection = 'gate'
            
        self.__triggers = []
        self.__gates = []
        
        self.gate_device = gate_device
        self.gate_connection= gate_connection
        self.connection = 'trigger'
        self.name = 'TH260'
        
        if gate_device :
            gate_device.add_device(self)
            
        TriggerableDevice.__init__(self, name, parent_device, connection, 
                                    #gate_device=gate_device, gate_connection = gate_connection, 
                                    **kwargs)
        
        
    def trigger(self, t, duration, trigger_device = None, triggers = None):
        """Request parent trigger device to produce a trigger at time t with given
        duration."""
        # Only ask for a trigger if one has not already been requested by another device
        # attached to the same trigger:
        if duration == 0. : duration = self.trigger_duration
        # print(duration)
        if trigger_device is None :
            trigger_device = self.trigger_device
        if triggers is None :
            triggers = self.__triggers

        already_requested = False
        for other_device in trigger_device.child_devices:
            if other_device is not self:
                for other_t, other_duration in other_device.__triggers:
                    if t == other_t and duration == other_duration:
                        already_requested = True
        if not already_requested:
            # print(trigger_device)
            trigger_device.trigger(t, duration)
        # Check for triggers too close together (check for overlapping triggers already
        # performed in Trigger.trigger()):
        start = t
        end = t + duration
        for other_t, other_duration in triggers:
            other_start = other_t
            other_end = other_t + other_duration
            if (
                abs(other_start - end) < self.minimum_recovery_time
                or abs(other_end - start) < self.minimum_recovery_time
            ):
                msg = """%s %s has two triggers closer together than the minimum
                    recovery time: one at t = %fs for %fs, and another at t = %fs for
                    %fs. The minimum recovery time is %fs."""
                msg = msg % (
                    self.description,
                    self.name,
                    t,
                    duration,
                    start,
                    duration,
                    self.minimum_recovery_time,
                )
                raise LabscriptError(msg)
        triggers.append([t, duration])
                
    
    def expose(self, t, name, frametype, trigger_duration=None):
        if isinstance(t, str) and isinstance(name, (int, float)):
            msg = """expose() takes `t` as the first argument and `name` as the second
                argument, but was called with a string as the first argument and a
                number as the second. Swapping arguments for compatibility, but you are
                advised to modify your code to the correct argument order."""
            print(LabscriptError(msg), file=sys.stderr)
            t, name = name, t
        if trigger_duration is None:
            trigger_duration = self.trigger_duration
        if trigger_duration is None:
            msg = """%s %s has not had an trigger_duration set as an instantiation
                argument, and none was specified for this exposure"""
            raise LabscriptError(msg % (self.description, self.name))
        if not trigger_duration > 0:
            msg = "trigger_duration must be > 0, not %s" % str(trigger_duration)
            raise ValueError(msg)

        self.trigger(t,2.51e-6)
        self.trigger(t+trigger_duration,2.51e-6)

        # print('banana')

        self.exposures.append((t, name, frametype, trigger_duration))

        if self.n_exposures == 0 :
            self.tmin=t
            self.tmax = t+trigger_duration
        if self.n_exposures > 0 :
            if t < self.tmin : self.tmin = t
            if (t+trigger_duration) > self.tmax : self.tmax = t+trigger_duration
        self.n_exposures += 1
        return trigger_duration
    
    def make_gate(self) :
        if self.n_exposures > 0 :
            self.trigger(self.tmin-self.gate_delay, self.tmax+self.gate_delay-(self.tmin-self.gate_delay), trigger_device = self.gate_device, triggers = self.__gates)
        for i in range (20):    #we had to add 20 sync pulses at the end so the buffer transfer doesn't go crazy because of very low count numbers (see manual for TH260lib.dll, section 5.3)
            self.trigger(self.tmax+1e-3+(i+1)*5.02e-6,2.51e-6)


    def generate_code(self, hdf5_file):
        if self.code_generated == 0 :
            # print(self.__gates,self.__triggers)
            # self.do_checks()
            vlenstr = h5py.special_dtype(vlen=str)
            table_dtypes = [
                ('t', float),
                ('name', vlenstr),
                ('frametype',vlenstr),
                ('trigger_duration', float),
            ]
            data = np.array(self.exposures, dtype=table_dtypes)
            group = self.init_device_group(hdf5_file)
            if self.exposures:
                group.create_dataset('EXPOSURES', data=data)
            self.code_generated = 1


import os
import json
import ast
import numpy as np
import pyqtgraph as pg

from blacs.tab_base_classes import Worker, define_state
from blacs.tab_base_classes import MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED  
from blacs.device_base_class import DeviceTab

import labscript_utils.properties

from qtutils import UiLoader

@BLACS_tab
class TH260Tab(DeviceTab):
    def initialise_GUI(self):
        layout = self.get_tab_layout()
        ui_filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'th260.ui')
        self.ui = UiLoader().load(ui_filepath)
        layout.addWidget(self.ui)
        
        port = int(self.settings['connection_table'].find_by_name(self.settings["device_name"]).BLACS_connection)
        self.ui.port_label.setText(str(port)) 
        
        self.ui.is_responding.setVisible(False)
        self.ui.is_not_responding.setVisible(False)
        
        self.ui.host_lineEdit.returnPressed.connect(self.update_settings_and_check_connectivity)
        self.ui.use_zmq_checkBox.toggled.connect(self.update_settings_and_check_connectivity)
        self.ui.check_connectivity_pushButton.clicked.connect(self.update_settings_and_check_connectivity)
        
    def get_save_data(self):
        return {'host': str(self.ui.host_lineEdit.text()), 'use_zmq': self.ui.use_zmq_checkBox.isChecked()}
    
    def restore_save_data(self, save_data):
        print('restore save data running')
        if save_data:
            host = save_data['host']
            self.ui.host_lineEdit.setText(host)
            if 'use_zmq' in save_data:
                use_zmq = save_data['use_zmq']
                self.ui.use_zmq_checkBox.setChecked(use_zmq)
        else:
            self.logger.warning('No previous front panel state to restore')
        
        # call update_settings if primary_worker is set
        # this will be true if you load a front panel from the file menu after the tab has started
        if self.primary_worker:
            self.update_settings_and_check_connectivity()
            
    def initialise_workers(self):
        worker_initialisation_kwargs = {'port': self.ui.port_label.text()}
        self.create_worker("main_worker", TH260ServerWorker, worker_initialisation_kwargs)
        self.primary_worker = "main_worker"
        self.update_settings_and_check_connectivity()
       
    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def update_settings_and_check_connectivity(self, *args):
        self.ui.saying_hello.setVisible(True)
        self.ui.is_responding.setVisible(False)
        self.ui.is_not_responding.setVisible(False)
        kwargs = self.get_save_data()
        responding = yield(self.queue_work(self.primary_worker, 'update_settings_and_check_connectivity', **kwargs))
        self.update_responding_indicator(responding)
        
    def update_responding_indicator(self, responding):
        self.ui.saying_hello.setVisible(False)
        if responding:
            self.ui.is_responding.setVisible(True)
            self.ui.is_not_responding.setVisible(False)
        else:
            self.ui.is_responding.setVisible(False)
            self.ui.is_not_responding.setVisible(True)


@BLACS_worker
class TH260ServerWorker(Worker):
    def init(self):#, port, host, use_zmq):
#        self.port = port
#        self.host = host
#        self.use_zmq = use_zmq
        global socket; import socket
        global zmq; import zmq
        global zprocess; import zprocess
        global shared_drive; import labscript_utils.shared_drive as shared_drive
        
        self.host = ''
        self.use_zmq = False
        
    def update_settings_and_check_connectivity(self, host, use_zmq):
        self.host = host
        self.use_zmq = use_zmq
        if not self.host:
            return False
        if not self.use_zmq:
            return self.initialise_sockets(self.host, self.port)
        else:
            response = zprocess.zmq_get_raw(self.port, self.host, data='hello')
            if response == 'hello':
                return True
            else:
                raise Exception('invalid response from server: ' + str(response))
                
    def initialise_sockets(self, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        assert port, 'No port number supplied.'
        assert host, 'No hostname supplied.'
        assert str(int(port)) == port, 'Port must be an integer.'
        s.settimeout(10)
        s.connect((host, int(port)))
        s.send('hello\r\n')
        response = s.recv(1024)
        s.close()
        if 'hello' in response:
            return True
        else:
            raise Exception('invalid response from server: ' + response)
    
    def transition_to_buffered(self, device_name, h5file, initial_values, fresh):
        h5file = shared_drive.path_to_agnostic(h5file)
        if not self.use_zmq:
            return self.transition_to_buffered_sockets(h5file,self.host, self.port)
        response = zprocess.zmq_get_raw(self.port, self.host, data=h5file)
        if response != 'ok':
            raise Exception('invalid response from server: ' + str(response))
        response = zprocess.zmq_get_raw(self.port, self.host, timeout = 120)
        if response != 'done':
            raise Exception('invalid response from server: ' + str(response))
        return {} # indicates final values of buffered run, we have none
        
    def transition_to_buffered_sockets(self, h5file, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(120)
        s.connect((host, int(port)))
        s.send('%s\r\n'%h5file)
        response = s.recv(1024)
        if not 'ok' in response:
            s.close()
            raise Exception(response)
        response = s.recv(1024)
        if not 'done' in response:
            s.close()
            raise Exception(response)
        return {} # indicates final values of buffered run, we have none
        
    def transition_to_manual(self):
        if not self.use_zmq:
            return self.transition_to_manual_sockets(self.host, self.port)
        response = zprocess.zmq_get_raw(self.port, self.host, 'done')
        if response != 'ok':
            raise Exception('invalid response from server: ' + str(response))
        response = zprocess.zmq_get_raw(self.port, self.host, timeout = 60)
        if response != 'done':
            raise Exception('invalid response from server: ' + str(response))
        return True # indicates success
        
    def transition_to_manual_sockets(self, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(120)
        s.connect((host, int(port)))
        s.send('done\r\n')
        response = s.recv(1024)
        if response != 'ok\r\n':
            s.close()
            raise Exception(response)
        response = s.recv(1024)
        if not 'done' in response:
            s.close()
            raise Exception(response)
        return True # indicates success
        
    def abort_buffered(self):
        return self.abort()
        
    def abort_transition_to_buffered(self):
        return self.abort()
    
    def abort(self):
        if not self.use_zmq:
            return self.abort_sockets(self.host, self.port)
        response = zprocess.zmq_get_raw(self.port, self.host, 'abort')
        if response != 'done':
            raise Exception('invalid response from server: ' + str(response))
        return True # indicates success 
        
    def abort_sockets(self, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(120)
        s.connect((host, int(port)))
        s.send('abort\r\n')
        response = s.recv(1024)
        if not 'done' in response:
            s.close()
            raise Exception(response)
        return True # indicates success 
    
    def program_manual(self, values):
        return {}
    
    def shutdown(self):
        return