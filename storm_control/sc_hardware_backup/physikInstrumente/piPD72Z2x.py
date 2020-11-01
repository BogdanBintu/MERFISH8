import storm_control.sc_hardware.nationalInstruments.nicontrol as nicontrol

import sys
sys.path.append(r'C:\Software\microscope\PIPython-1.3.5.37')

from copy import deepcopy

import storm_control.sc_library.parameters as params
import storm_control.sc_hardware.baseClasses.voltageZModule as voltageZModule
from pipython import GCSDevice, pitools

CONTROLLERNAME = "E-709.CRG"
# STAGES = ['P-725.2CD']  # name in piMicroMove
SERIALNUM='120031914'

class piPD72Z2x(voltageZModule.VoltageZ):
    
    def __init__(self, module_params=None, qt_settings=None, **kwds):
        super().__init__(module_params, qt_settings, **kwds)
        
        ## __init__
        # @param board The DAQ board to use.
        # @param line The analog output line to use
        # @param scale (Optional) Conversion from microns to volts (default is 10.0/250.0)

        print(f"Serial number: {SERIALNUM}")

        # Connect to piezo
        pidevice = GCSDevice(CONTROLLERNAME)
        pidevice.ConnectUSB(SERIALNUM)
        print("Connected: {}".format(pidevice.qIDN().strip()))

        # In the module pipython.pitools there are some helper
        # functions to make using a PI device more convenient. The "startup"
        # function will initialize your system. There are controllers that
        # cannot discover the connected stages hence we set them with the
        # "stages" argument. The desired referencing method (see controller
        # user manual) is passed as "refmode" argument. All connected axes
        # will be stopped if they are moving and their servo will be enabled.
        
        # set volaltile reference mode to analog input

        print("Setting up analog input")
        pidevice.SPA('Z', 0x06000500, 2)
        self.pidevice = pidevice
    

        # Connect to the piezo.
        self.good = 1

        # get min and max range
        #self.rangemin = pidevice.qTMN()
        #self.rangemax = pidevice.qTMX()
        #self.curpos = pidevice.qPOS()

        # NI relevant bits
        #print(f"Initializing NI board {board}, {line}")
        #self.board = board
        #self.line = line
        #self.trigger_source = trigger_source
        #self.scale = scale
        #self.ni_task = nicontrol.AnalogOutput(self.board, self.line)
        #self.ni_task.StartTask()

    def zPosition(self):
        """
        Query current z position in microns.
        """
        if self.good:
            z0 = self.pidevice.qPOS()['Z']
            return {'z': z0}

    def shutDown(self):
        self.ni_task.stopTask()
        self.ni_task.clearTask()

    def zSetVelocity(self, z_vel):
        pass
    
    def getStatus(self):
        return self.good

    def zMoveTo(self, z):
        try:
            #nicontrol.setAnalogLine(self.board, self.line, z * self.scale)
            voltage = z * self.scale
            if (voltage > 0.0) and (voltage < 10.0):
                self.ni_task.output(voltage)
        except AssertionError as e:
            print("Caught outputVoltage error:", type(e), str(e))
            self.ni_task.stopTask()
            self.ni_task.clearTask()
            self.ni_task = nicontrol.AnalogOutput(self.board, self.line)
            self.ni_task.startTask()
            
    def shutDown(self):
        if self.good:
            pidevice.StopAll(noraise=True)
            pitools.waitonready(pidevice)  # there are controllers that need some time to halt all axes
            pidevice.CloseConnection()

#
# Testing
# 

if __name__ == "__main__":
    stage = piPD72Z2x("USB-6002", 0)
    stage.zMoveTo(125.0)

        