#!/usr/bin/env python
"""
HAL interface to National Instruments cards.

Hazen 04/17
"""

import storm_control.hal4000.halLib.halMessage as halMessage

import storm_control.sc_hardware.baseClasses.hardwareModule as hardwareModule
import storm_control.sc_hardware.nationalInstruments.nicontrol as nicontrol

import storm_control.sc_library.hdebug as hdebug
import storm_control.sc_library.halExceptions as halExceptions


class NidaqModuleException(halExceptions.HardwareException):
    pass


class NidaqFunctionality(hardwareModule.HardwareModule):

    def __init__(self, used_during_filming = True, **kwds):
        self.source = None
        self.task = None
        self.used_during_filming = used_during_filming

    def getChannel(self):
        return self.channel

    def getSource(self):
        return self.source
    
    def getUsedDuringFilming(self):
        return self.used_during_filming
        
    def setInvalid(self):
        super().setInvalid()
        if self.task is not None:
            self.task.stopTask()
            self.task = None


class DOTaskFunctionality(NidaqFunctionality):

    def __init__(self, source = None, **kwds):
        super().__init__(**kwds)
        self.source = source

    def createTask(self):
        self.task = nicontrol.DigitalOutput(source = self.source)
        self.task.startTask()
        
    def output(self, state):
        if self.task is None:
            self.createTask()
        try:
            self.task.output(state)
        except nicontrol.NIException as exception:
            hdebug.logText("DoTaskFunctionality Error", str(exception))
            self.task.stopTask()
            self.createTask()
        

class NidaqModule(hardwareModule.HardwareModule):

    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)

        # These are the waveforms to output during a film.
        self.analog_waveforms = []
        self.digital_waveforms = []

        # These are the tasks that are used for waveform output.
        self.ao_task = None
        self.do_task = None
        self.ct_task = None

        self.oversampling = 1
        
        configuration = module_params.get("configuration")
        self.default_timing = configuration.get("timing")
        self.timing = self.default_timing.copy()

        # Create functionalities we will provide, these are all Daq tasks.        
        self.daq_fns = {}
        for fn_name in configuration.getAttrs():
            
            # Don't provide a timing configuration, at least for now.
            if (fn_name == "timing"):
                continue

            task = configuration.get(fn_name)
            for task_name in task.getAttrs():
                task_params = task.get(task_name)
            
                daq_fn_name = ".".join([self.module_name, fn_name, task_name])
                print(">", daq_fn_name)
                if (task_name == "do_task"):
                    self.daq_fns[daq_fn_name] = DOTaskFunctionality(source = task_params.get("source"),
                                                                    used_during_filming = task_params.get("used_during_filming", True))
                else:
                    raise NidaqModuleException("Unknown task type", task_name)

    def filmTiming(self, message):
        self.ao_task = None
        self.ct_task = None
        self.do_task = None
        film_settings = message.getData("film settings")
        if film_settings.runShutters():

            # Invalidate all the tasks that we'll need for waveform output. This
            # is maybe not so important as these tasks are able to reset themselves
            # anyway in the event that there is an error.
            for daq_fn in self.daq_fns():
                if self.daq_fns[daq_fn].getUsedDuringFilming():
                    self.daq_fns[daq_fn].setInvalid()

            # Get frames per second from the timing functionality. This is
            # a property of the camera that drives the timing functionality.
            fps = message.getData("functionality").getFPS()
            
            # Calculate frequency. This is set slightly higher than the camere
            # frequency so that we are ready at the start of the next frame.
            frequency = 1.01 * fps * float(self.oversampling)

            # If oversampling is 1 then just trigger the ao_task 
            # and do_task directly off the camera fire pin.
            if (self.oversampling == 1):
                wv_clock = self.timing.get("camera_fire_pin")
            else:
                wv_clock = self.timing.get("counter_out")

            # Setup the counter.
            if self.counter_board and (oversampling > 1):
                def startCtTask():
                    try:
                        self.ct_task = nicontrol.CounterOutput(source = self.timing.get("counter"), 
                                                               frequency = frequency, 
                                                               duty_cyle = 0.5)
                        self.ct_task.setCounter(number_samples = self.oversampling)
                        self.ct_task.setTrigger(trigger_source = self.timing.get("camera_fire_pin"))
                        self.ct_task.startTask()
                    except nicontrol.NIException as exception:
                        print(exception)
                        return True

                    return False

                iters = 0
                while (iters < 5) and startCtTask():
                    hdebug.logText("startCtTask failed " + str(iters))
                    self.ct_task.clearTask()
                    time.sleep(0.5)
                    iters += 1

                if (iters == 5):
                    hdebug.logText("startCtTask critical failure")
                    raise NidaqModuleException("NIException: startCtTask critical failure")

            # Setup analog waveforms.
            if (len(self.analog_waveforms) > 0):

                # Sort by source.
                analog_data = sorted(self.analog_waveforms, key = lambda x: x[0])

                # Set waveforms.
                waveforms = []
                for i in range(len(analog_data)):
                    waveforms.append(analog_data[i][1])

                def startAoTask():
                
                    try:
                        # Create channels.
                        self.ao_task = nicontrol.AnalogWaveformOutput(source = analog_data[0][0])
                        for i in range(len(analog_data) - 1):
                            self.ao_task.addChannel(source = analog_data[i+1][0])

                        # Add waveforms
                        self.ao_task.setWaveforms(waveforms = waveforms,
                                                  sample_rate = frequency,
                                                  clock = wv_clock)

                        # Start task.
                        self.ao_task.startTask()
                    except nicontrol.NIException as exception:
                        print(exception)
                        return True
                    
                    return False

                iters = 0
                while (iters < 5) and startAoTask():
                    hdebug.logText("startAoTask failed " + str(iters))
                    self.ao_task.clearTask()
                    time.sleep(0.1)
                    iters += 1

                if (iters == 5):
                    hdebug.logText("startAoTask critical failure")
                    raise NidaqModuleException("NIException: startAoTask critical failure")

        # Setup digital waveforms.
        if (len(self.digital_waveforms) > 0):

            # Sort by board, channel.
            digital_data = sorted(self.digital_waveforms, key = lambda x: x[0])

            # Set waveforms.
            waveforms = []
            for i in range(len(digital_data)):
                waveforms += digital_data[i][1]

            def startDoTask():

                try:
                    # Create channels.
                    self.do_task = nicontrol.DigitalWaveformOutput(source = digital_data[0][0])
                    for i in range(len(digital_data) - 1):
                        self.do_task.addChannel(source = digital_data[i+1][0])

                    # Add waveform
                    self.do_task.setWaveforms(waveforms = waveforms,
                                              sample_rate = frequency,
                                              clock = wv_clock)

                    # Start task.
                    self.do_task.startTask()
                except nicontrol.NIException as exception:
                    print(exception)
                    return True

                return False

            iters = 0
            while (iters < 5) and startDoTask():
                hdebug.logText("startDoTask failed " + str(iters))
                self.do_task.clearTask()
                time.sleep(0.1)
                iters += 1

            if iters == 5:
                hdebug.logText("startDoTask critical failure")
                raise NidaqModuleException("NIException: startDoTask critical failure")
            
    def getFunctionality(self, message):
        daq_fn_name = message.getData()["name"]
        if daq_fn_name in self.daq_fns:
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"functionality" : self.daq_fns[daq_fn_name]}))
            
    def stopFilm(self, message):
        """
        Handle the 'stop film' message.
        """
        for task in [self.ct_task, self.ao_task, self.do_task]:
            if task is not None:
                try:
                    task.stopTask()
                except nicontrol.NIException as e:
                    hdebug.logText("stop / clear failed for task " + str(task) + " with " + str(e))