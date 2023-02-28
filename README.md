# labscript_th260

This project integrates the [Picoquant TimeHarp 260](https://www.picoquant.com/products/category/tcspc-and-time-tagging-modules/timeharp-260-tcspc-and-mcs-board-with-pcie-interface), (TH260) into the [labscript suite](http://labscriptsuite.org/),
which is a control system for autonomous, hardware timed experiments. The TH260 is a compact, easy to use, Time-Correlated Single  Photon Counting (TCSPC) and Multi-Channel Scaling (MCS) board for the  PCIe interface. The project is used for single-photon counting experiments in a CavityQED setup.

## Notes:

- the implementation of the TH260 labscript device relies on a seperate TH260 server being the labscript worker for the corresponding labscript device 'th260.py'.
- the TH260 server relies on the picoquant's dll 'th260lib64.dll'
- the actual labscript device is contained in 'TH260_new.py' and its user interface in 'th260.ui' and are currently run in an old labscript version using python 2.7
- the TH260 server has to be run in python from the 'Command Prompt'
- the TH260 server is the actual 'worker' process for the TH260 labscript device which does
the communication with the TH260 card via its API
- 'TH260_dev_dummy.py' is a dummy for 'TH260_dev.py' replacing the actual API for testing of the server and its communication with labscript as well as saving the data in the h5 shot file



