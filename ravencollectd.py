import sys
import time
import re
import xml.etree.ElementTree as ET
import logging as log
import serial

class ravencollectd:
    '''This class handles all communication to/from the RAVEn and the MQTT     broker'''

    def __init__(self, serDevice, hostName, hostPort, hostUser, hostPwd, topic):
        '''The constructor requires all connection information for both MQTT and the RAVEn'''
        self.serDevice = serDevice
        self.ser = None

        # Various Regex's
        self.reStartTag = re.compile('^<[a-zA-Z0-9]+>') # to find a start XML tag (at very beginning of line)
        self.reEndTag = re.compile('^<\/[a-zA-Z0-9]+>') # to find an end XML tag (at very beginning of line)

    def __del__(self):
        '''This will close all connections (serial/MQTT)'''
        self.close()

    def _openSerial(self):
        '''This function opens the serial port looking for a RAVEn. Returns True if successful, False otherwise.'''
        try:
            self.ser = serial.Serial(self.serDevice, 115200, serial.EIGHTBITS, serial.PARITY_NONE, timeout=0.5)
            self.ser.close()
            self.ser.open()
            self.ser.flushInput()
            self.ser.flushOutput()
            log.info("Connected to: " + self.ser.portstr)
            return True
        except Exception as e:
            log.critical("Cannot open serial port: " + str(e))
            return False

    def _closeSerial(self):
        '''This function will close the serial port talking to the RAVEn'''
        if self.ser is not None:
            self.ser.close()
            log.info("Serial port closed.")
        else:
            log.debug("Asking to close serial port, but it was never open.")

    def open(self):
        '''This function will open all necessary connections for the RAVEn to talk to the MQTT broker'''
        if not self._openSerial():
            log.critical("Serial port was not opened due to an error.")
            return False
        else:
		  return True

    def close(self):
        '''This function will close all previously opened connections'''
        if self.ser is not None: self._closeSerial()

    def _isReady(self):
        '''This function is used to check if this object has been initialised correctly and is ready to process data'''
        return  (self.ser is not None)

    def run(self):
        '''This function will read from the serial device, process the data and publish MQTT messages'''
        if self._isReady():
            # begin listening to RAVEn
            rawxml = ""

            while True:
                # wait for /n terminated line on serial port (up to timeout)
                rawline = self.ser.readline()
                # remove null bytes that creep in immediately after connecting
                rawline = rawline.strip('\0')
                # only bother if this isn't a blank line
                if len(rawline) > 0:
                    # start tag
                    if self.reStartTag.match(rawline):
                        rawxml = rawline
                        log.debug("Start XML Tag found: " + rawline)
                    # end tag
                    elif self.reEndTag.match(rawline):
                        rawxml = rawxml + rawline
                        log.debug("End XML Tag Fragment found: " + rawline)
                        try:
                            xmltree = ET.fromstring(rawxml)
                            if xmltree.tag == 'InstantaneousDemand':
                                self.client.publish(self.topic, payload=self._getInstantDemandKWh(xmltree), qos=0)
                                log.debug(self._getInstantDemandKWh(xmltree))
                            else:
                                log.warning("*** Unrecognised (not implemented) XML Fragment")
                                log.warning(rawxml)
                        except Exception as e:
                          log.error("Exception triggered: " + str(e))
                        # reset rawxml
                        rawxml = ""
                    # if it starts with a space, it's inside the fragment
                    else:
                        rawxml = rawxml + rawline
                        log.debug("Normal inner XML Fragment: " + rawline)
                else:
		  pass

        else:
            log.error("Was asked to begin reading/writing data without opening connections.")

    def _getInstantDemandKWh(self, xmltree):
        '''Returns a single float value for the Demand from an Instantaneous Demand response from RAVEn'''
        # Get the Instantaneous Demand
        fDemand = float(int(xmltree.find('Demand').text,16))
        fResult = self._calculateRAVEnNumber(xmltree, fDemand)
        return fResult

    def _calculateRAVEnNumber(self, xmltree, value):
        '''Calculates a float value from RAVEn using Multiplier and Divisor in XML response'''
        # Get calculation parameters from XML - Multiplier, Divisor
        fDivisor = float(int(xmltree.find('Divisor').text,16))
        fMultiplier = float(int(xmltree.find('Multiplier').text,16))
        if (fMultiplier > 0 and fDivisor > 0):
            fResult = float( (value * fMultiplier) / fDivisor)
        elif (fMultiplier > 0):
            fResult = float(value * fMultiplier)
        else: # (Divisor > 0) or anything else
            fResult = float(value / fDivisor)
        return fResult*1000
