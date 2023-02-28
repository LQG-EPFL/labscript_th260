# import labscript_utils.h5_lock
import sys
import time
import zprocess
import h5py
# from labscript_utils import check_version
# import labscript_utils.shared_drive
import datetime
# from TH260_dev_dummy import TH260_Card
from TH260_dev import TH260_Card
# from matplotlib import pyplot as pt
import numpy as np

def path_to_local(path):
    """
    Convenience function, taken from labscript source code
    """
    """
    if path.startswith('Z:\\'):
        path = path.split('Z:\\', 1)[1]
        path = path.replace('\\', os.path.sep)
        path = os.path.join(prefix, path)
    """   
    return path

class GenericServer(zprocess.ZMQServer):
    def __init__(self, port):
           zprocess.ZMQServer.__init__(self, port, type='string')
           self._h5_filepath = None
           self.enable = True

    def handler(self, request_data):
        try:
            print(request_data)
            if request_data == 'hello':
                return 'hello'
            elif request_data.endswith('.h5'):
                self._h5_filepath = path_to_local(request_data)
                # self._h5_filepath = path_to_local(request_data)
                self.send('ok')
                self.recv()
                self.transition_to_buffered(self._h5_filepath)
                print('here')
                return 'done'
            elif request_data == 'done':
                self.send('ok')
                self.recv()
                self.transition_to_static(self._h5_filepath)
                self._h5_filepath = None
                return 'done'
            elif request_data == 'abort':
                self.abort()
                self._h5_filepath = None
                return 'ok'
            else:
                raise ValueError('invalid request: %s'%request_data)
        except Exception:
            if self._h5_filepath is not None and request_data != 'abort':
                try:
                    self.abort()
                except Exception as e:
                    sys.stderr.write('Exception in self.abort() while handling another exception:\n{}\n'.format(str(e)))
            self._h5_filepath = None
            raise

    def transition_to_buffered(self, h5_filepath):
        print('transition to buffered')

    def transition_to_static(self, h5_filepath):
        print('transition to static')

    def abort(self):
        print('abort')


class TH260Server(GenericServer):
    """
    Implementation of a server to handle the TH260 card.
    
    The specified port during the instantiation of the class should match the
    one written in the connection table (and therefore in BLACS).
    """

    interface_class = TH260_Card 

    def __init__(self, port, name):
        print("Setting attributes...")
        GenericServer.__init__(self, port)
        self.device_name = name
        self.devidx=0
        self.card = self.get_card()
        self.exposures = None
        self.acquisition_thread = None
        print("Initialisation complete")

    def get_card(self):
        """Return an instance of the camera interface class. Subclasses may override
        this method to pass required arguments to their class if they require more
        than just the serial number."""
        return self.interface_class(self.devidx)

        
    def transition_to_buffered(self, h5_filepath):                       
        # Feedback
        print (self.device_name+' transition to buffered at %s' %(str(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S.%f"'))))

        with h5py.File(h5_filepath, 'r') as f:
            group = f['devices'][self.device_name]
            if not 'EXPOSURES' in group:
                return {}
            self._h5_filepath = h5_filepath
            self.exposures = group['EXPOSURES'][:]
            self.n_traces = len(self.exposures)
        print(self.exposures)
        print("Configuring card for triggered acquisition.")
        self.card.start_acquisition(acqTime=5000)

        return {}
    
    def transition_to_static(self, h5_filepath):           
        # Feedback
        print (self.device_name+' transition to static at %s' %(str(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S.%f"'))))
        # self.card.stop_acquisition()
        ### Write how to save and display traces 
        if self._h5_filepath is None:
            print('No traces in this shot.\n')
            return True

        self.traces = []
        print ('reading buffer')
        sync_times, arrival_times = self.card.readBuffer()
        # print('sync times :') ; print(sync_times)
        # print('arrival times :') ; print(arrival_times)
        print('buffer read, saving trace')
                
        """
        Sorting traces as a function of sync events :
        """
        sync_times = sync_times[:2*self.n_traces]  #we had to add 20 sync pulses at the end so the buffer transfer doesn't go crazy because of very low count numbers (see manual for TH260lib.dll, section 5.3)
                                                    # so now we're just taking the right amount of flags, defined by the number of exposures we expect.
        sync_flags=sync_times.copy()
        # print(sync_flags)
        # print(arrival_times)
        while sync_flags.size > 1 :
            self.traces.append(arrival_times[np.where((arrival_times > sync_flags[0]) & (arrival_times < sync_flags[1]))] - sync_flags[0])
            sync_flags = sync_flags[2:]
            # print(sync_flags)
        if sync_flags.size == 1 :
            print('last sync missed, sending all the rest')
            self.traces.append((arrival_times[np.where(arrival_times > sync_flags[0])] - sync_flags[0]))
            sync_flags = sync_flags[1:]
        print(self.traces)
        print("Saving {len(self.traces)}/{len(self.exposures)} traces.")

        with h5py.File(self._h5_filepath, 'r+') as f:
            trace_path = 'data/time_arrays/' + self.device_name
            trace_group = f.require_group(trace_path)
            trace_group.attrs['camera'] = self.device_name

            # Whether we failed to get all the expected exposures:
            trace_group.attrs['failed_shot'] = len(self.traces) != len(self.exposures)


            # Iterate over expected exposures, sorted by acquisition time, to match them
            # up with the acquired images:
            self.exposures.sort(order='t')

            dset = trace_group.create_dataset(
                'sync_times',data=sync_times, dtype='float', compression='gzip'
            )
            dset = trace_group.create_dataset(
                'arrival_times',data=arrival_times, dtype='float', compression='gzip'
            )

            traces = {
                # (exposure['name'], exposure['frametype']): []
                exposure['name']: []
                for exposure in self.exposures
            }
            
            for trace, exposure in zip(self.traces, self.exposures):
                traces[exposure['name']].append(trace)
                expos_group = trace_group.require_group(exposure['name'])
                dset= expos_group.create_dataset(
                    exposure['frametype'],data = trace, dtype='float', compression='gzip'
                    )
                # print(trace)


        self.traces = None
        traces_to_send = None
#         self.attributes_to_save = None
        self.exposures = None
        self.h5_filepath = None
        self.stop_acquisition_timeout = None
        self.exception_on_failed_shot = None
        print("Setting manual mode.\n")

        # return True  

    def abort(self):
        # if self.acquisition_thread is not None:
        #     self.card.abort_acquisition()
        #     self.acquisition_thread.join()
        #     self.acquisition_thread = None
        #     self.card.stop_acquisition()
        # self.card._abort_acquisition = False
        self.traces = None
        self.n_traces = None
        self.exposures = None
        self.acquisition_thread = None
        self._h5_filepath = None
        self.exception_on_failed_shot = None
        return True

    def abort_buffered(self):
        return self.abort()

    def abort_transition_to_buffered(self):
        return self.abort()

    def program_manual(self, values):
        return {}

    def shutdown(self):
        self.card.close()
    
def start_main_server():
    port = 1028
    print("Starting TH260 server on port %d" % port)
    th260_server = TH260Server(port, "th260")
    th260_server.shutdown_on_interrupt()  
        
if __name__ == '__main__':
    start_main_server()           
    