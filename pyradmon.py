#!/usr/bin/python

import sys, os
import serial
import time, datetime
import threading, thread
import socket
from collections import deque
import random

################################################################################
# pyRadMon - logger for Geiger counters
# version is a.b.c, change in a or b means new functionality/bugfix,
# change in c = bugfix
# do not uncomment line below, it's currently used in HTTP headers
VERSION="0.3.0"
# Please visit http://www.radmon.org to see your logs
# Found a bug? Need a feature? E-mail me: pyradmon@10g.pl
################################################################################


################################################################################
# Part 1 - configuration procedures
#
# Read configuration from file + constants definition
################################################################################
'''
Configuration realated functions
'''
class config():
    # used as enums
    UNKNOWN=0
    DEMO=1
    MYGEIGER=2
    GMC=3
    NETIO=4

    '''
    Class instance initialization
    '''
    def __init__(self):
        # define constants
        self.CONFIGFILE="config.txt"
        self.UNKNOWN=0
        self.DEMO=1
        self.MYGEIGER=2
        self.GMC=3
        self.NETIO=4

        self.user="not_set"
        self.password="not_set"

        self.portName=None
        self.portSpeed=2400
        self.timeout=40 # not used for now
        self.protocol=self.UNKNOWN

    '''
    Get configuration from file
    '''
    def readConfig(self):
        print "Reading configuration:"

        # check if file exists, if not, create one and exit
        if (os.path.isfile(self.CONFIGFILE)==0):
            print "\tNo configuration file, creating default one."

            try:
                f = open(self.CONFIGFILE, 'w')
                f.write("# Parameter names are not case-sensitive\r\n")
                f.write("# Parameter values are case-sensitive\r\n")
                f.write("user=test_user\r\n")
                f.write("password=test_password\r\n")
                f.write("# Port is usually /dev/ttyUSBx in Linux and COMx in Windows\r\n")
                f.write("serialport=/dev/ttyUSB0\r\n")
                f.write("speed=2400\r\n")
                f.write("# Protocols: demo, mygeiger, gmc, netio\r\n")
                f.write("protocol=demo\r\n")
                f.close()
                exit(1)
                print "\tPlease open config.txt file using text editor and update configuration.\r\n"
            except Exception as e:
                print "\tFailed to create configuration file\r\n\t",str(e)
            exit(1)

        # if file is present then try to read configuration from it
        try:
            f = open(self.CONFIGFILE)
            line=" "
            # analyze file line by line, format is parameter=value
            while (line):
                line=f.readline()
                params=line.split("=")

                if len(params)==2:
                    parameter=params[0].strip().lower()
                    value=params[1].strip()
                    
                    if parameter=="user":
                        self.user=value
                        print "\tUser name configured"

                    elif parameter=="password":
                        self.password=value
                        print "\tPassword configured"

                    elif parameter=="serialport":
                        self.portName=value
                        print "\tSerial port name configured"

                    elif parameter=="speed":
                        self.portSpeed=int(value)
                        print "\tSerial port speed configured"

                    elif parameter=="protocol":
                        value=value.lower()
                        if value=="mygeiger":
                            self.protocol=self.MYGEIGER
                        elif value=="demo":
                            self.protocol=self.DEMO
                        elif value=="gmc":
                            self.protocol=self.GMC
                        elif value=="netio":
                            self.protocol=self.NETIO

                        if self.protocol!=self.UNKNOWN:
                            print "\tProtocol configured"
                # end of if
            # end of while
            f.close()
        except Exception as e:
            print "\tFailed to read configuration file:\r\n\t",str(e), "\r\nExiting\r\n"
            exit(1)
        # well done, configuration is ready to use
        print ""

################################################################################
# Part 2 - Geiger counter communication
#
# It should be easy to add different protocol by simply
# creating new class based on baseGeigerCommunication, as it's done in
# classes Demo and myGeiger
################################################################################
'''
Base class for geiger counter communication
Implement all communication using this class as base
timeout is currently not used
'''
class baseGeigerCommunication(threading.Thread):

    def __init__(self, cfg):
        super(baseGeigerCommunication, self).__init__()
        self.sPortName=cfg.portName
        self.sPortSpeed=cfg.portSpeed
        self.timeout=cfg.timeout
        self.stopwork=0
        self.queue=deque()
        self.queueLock=0
        self.is_running=1

    '''
    Main function where data from geiger is processed for later sending to RadMon
    '''
    def run(self):
        try:
            print "Gathering data started\r\n"
            self.serialPort = serial.Serial(self.sPortName, self.sPortSpeed, timeout=1)
            self.serialPort.flushInput()
            
            self.initCommunication()

            while(self.stopwork==0):
                result=self.getData()
                while (self.queueLock==1):
                    print "Geiger communication: quene locked!"
                    time.sleep(0.5)
                self.queueLock=1
                self.queue.append(result)
                self.queueLock=0
                print "Geiger sample:\tCPM =",result[0],"\t",str(result[1])

            self.serialPort.close()
            print "Gathering data from Geiger stopped\r\n"
        except serial.SerialException as e:
            print "Problem with serial port:\r\n\t", str(e),"\r\nExiting\r\n"
            self.stop()
            sys.exit(1)

    '''
    Initialize geiger counter communication, needed by some protocols
    this function does nothing in base class
    '''
    def initCommunication(self):
        print "Initializing geiger communication"
 
    '''
    Send command to device and return response
    '''
    def sendCommand(self, command):
        self.serialPort.flushInput()
        self.serialPort.write(command)
        # assume that device responds within 0.5s
        time.sleep(0.5)
        response=""
        while (self.serialPort.inWaiting()>0 and self.stopwork==0):
            response = response + self.serialPort.read()
        return response
   
    '''
    Override this function depending on Geiger protocol used
    This one returns constant value and current UTC time
    '''
    def getData(self):
        cpm=25
        utcTime=datetime.datetime.utcnow()
        data=[cpm, utcTime]
        return data

    '''
    Stop geiger communication
    '''
    def stop(self):
        self.stopwork=1
        self.queueLock=0
        self.is_running=0

    '''
    Get data from queue, process it, return single result with average CPM and latest date
    '''
    def getResult(self):
        # check if we have some data in queue
        if len(self.queue)>0:

            # check if it's safe to process queue
            while (self.queueLock==1):
                print "getResult: quene locked!"
                time.sleep(0.5)

            # put lock so measuring process will not interfere with queue,
            # processing should be fast enought to not break data acquisition from geiger
            self.queueLock=1

            cpm=0
            # now get sum of all CPM's
            for singleData in self.queue:
                cpm=cpm+singleData[0]

            # and divide by number of elements
            # to get mean value, 0.5 is for rounding up/down
            cpm=int( ( float(cpm) / len(self.queue) ) +0.5)
            # report with latest time from quene
            utcTime=self.queue.pop()[1]

            # clear queue and remove lock
            self.queue.clear()
            self.queueLock=0

            data=[cpm, utcTime]
        else:
            # no data in queue, return invalid CPM data and current time
            data=[-1, datetime.datetime.utcnow()]

        return data

'''
Demo geiger counter class
'''
class Demo(baseGeigerCommunication):
    '''
    Demo Geiger code - just return random value in range 5-40 every few seconds
    As it won't need to open any serial port also run() method needs to be overriden
    '''
    def run(self):
        print "Gathering data started\r\n"

        while(self.stopwork==0):
            result=self.getData()
            while (self.queueLock==1):
                print "Geiger communication: quene locked!"
                time.sleep(0.5)
            self.queueLock=1
            self.queue.append(result)
            self.queueLock=0
            print "Geiger sample:\t",result

        print "Gathering data from Geiger stopped\r\n"

    '''
    Demo code - just return random value in range 5-40 every few seconds
    '''
    def getData(self):
        for i in range(0,5):
            time.sleep(1)
        cpm=random.randint(5,40)
        utcTime=datetime.datetime.utcnow()
        data=[cpm, utcTime]
        return data

'''
For myGeiger communication protocol
'''
class myGeiger(baseGeigerCommunication):
    def getData(self):
        cpm=-1
        try:
            # wait for data
            while (self.serialPort.inWaiting()==0 and self.stopwork==0):
                time.sleep(1)

            time.sleep(0.1) # just to ensure all CPM bytes are in serial port buffer
            # read all available data
            x=""
            while (self.serialPort.inWaiting()>0 and self.stopwork==0):
                x = x + self.serialPort.read()

            if len(x)>0:
                cpm=int(x)

            utcTime=datetime.datetime.utcnow()
            data=[cpm, utcTime]
            return data
        except Exception as e:
            print "\r\nProblem in getData procedure (disconnected USB device?):\r\n\t",str(e),"\r\nExiting"
            self.stop()
            sys.exit(1)

'''
For GMC communication protocol used by http://www.gqelectronicsllc.com products
'''
class gmc(baseGeigerCommunication):
    '''
    Initialize communication using GMC protocol
    '''
    def initCommunication(self):
        
        print "Initializing GMC protocol communication"
        # get firmware version
        response=self.sendCommand("<GETVER>>")
        
        if len(response)>0:
            print "Found GMC-compatible device, firmware version: ", response
            # disable heartbeat, we will request data from script
            self.sendCommand("<HEARTBEAT0>>")
            print "Please note data will be acquired once per 30 seconds"

        else:
            print "No response from device"
            self.stop()
            sys.exit(1)
    
    '''
    Get CPM from GMC protocol compatible device
    '''
    def getData(self):
        cpm=-1
        try:
            # wait, we want sample every 30s
            for i in range(0,30):
                time.sleep(1)
            
            # send request
            response=self.sendCommand("<GETCPM>>")
            
            if len(response)==2:
                # convert bytes to 16 bit int
                cpm=ord(response[0])*256+ord(response[1])
            else:
                print "Unknown response to CPM request, device is not GMC-compatible?"
                self.stop()
                sys.exit(1)
                
            utcTime=datetime.datetime.utcnow()
            data=[cpm, utcTime]
            return data
            
        except Exception as e:
            print "\r\nProblem in getData procedure (disconnected USB device?):\r\n\t",str(e),"\r\nExiting"
            self.stop()
            sys.exit(1)

'''
For NetIO geiger counter protocol
It's basically the same as MyGeiger
But sends also CR+LF and data is sent every second
'''
class netio(baseGeigerCommunication):
    def getData(self):
        cpm=-1
        try:
            # we want data only once per 30 seconds, ignore rest
            # it's averaged for 60 seconds by device anyway
            for i in range(0,30):
                time.sleep(1)

            # wait for data, should be already there (from last 30s)
            while (self.serialPort.inWaiting()==0 and self.stopwork==0):
                time.sleep(0.5)
            
            time.sleep(0.1) # just to ensure all CPM bytes are in serial port buffer
            # read all available data

            # do not stop receiving unless it ends with \r\n
            x=""
            while ( x.endswith("\r\n")==False and self.stopwork==0):
                while ( self.serialPort.inWaiting()>0 and self.stopwork==0 ):
                    x = x + self.serialPort.read()

            # if CTRL+C pressed then x can be invalid so check it
            if x.endswith("\r\n"):
                # we want only latest data, ignore older
                tmp=x.splitlines()
                x=tmp[len(tmp)-1]
                cpm=int(x)
            
            utcTime=datetime.datetime.utcnow()
            data=[cpm, utcTime]
            return data

        except Exception as e:
            print "\r\nProblem in getData procedure (disconnected USB device?):\r\n\t",str(e),"\r\nExiting"
            self.stop()
            sys.exit(1)

    def initCommunication(self):
        print "Initializing NetIO"
        # send "go" to start receiving CPM data
        response=self.sendCommand("go\r\n")
        print "Please note data will be acquired once per 30 seconds"
        
################################################################################
# Part 3 - Web server communication
################################################################################
'''
Holds function needed to send data to www.radmon.org
For now it uses old version of code, not urllib python package
'''
class webCommunication():
    HOST="www.radmon.org"
    #HOST="127.0.0.1" # uncomment this for debug purposes on localhost
    PORT=80

    def __init__(self, mycfg):
        self.user=mycfg.user
        self.password=mycfg.password

    def sendSample(self, sample):

        print "Connecting to server"
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.HOST, self.PORT))

        BUFFER_SIZE=1024

        sampleCPM=sample[0]
        sampleTime=sample[1]

        # format date and time as required
        dtime=sampleTime.strftime("%Y-%m-%d%%20%H:%M:%S")

        url="GET /radmon.php?user="+self.user+"&password="+self.password+"&function=submit&datetime="+dtime+"&value="+str(sampleCPM)+"&unit=CPM HTTP/1.1"

        request=url+"\r\nHost: www.radmon.org\r\nUser-Agent: pyRadMon "+VERSION+"\r\n\r\n"
        print "Sending average sample"
        #print "\r\n### HTTP Request ###\r\n"+request

        s.send(request)
        data = s.recv(BUFFER_SIZE)
        httpResponse=str(data).splitlines()[0]
        print "Server response: ",httpResponse,"\r\n"

        if "incorrect login" in data.lower():
            print "You are using incorrect user/password combination!\r\n"
            geigerCommunication.stop()
            sys.exit(1)
            
        #print "\r\n### HTTP Response ###\r\n"+data+"\r\n"
        s.close


################################################################################
# Main code
################################################################################

# create and read configuration data
cfg=config()
cfg.readConfig()

# create geiger communication object
if cfg.protocol==config.MYGEIGER:
    print "Using myGeiger protocol"
    geigerCommunication=myGeiger(cfg)
elif cfg.protocol==config.DEMO:
    print "Using Demo mode"
    geigerCommunication=Demo(cfg)
elif cfg.protocol==config.GMC:
    print "Using GMC protocol"
    geigerCommunication=gmc(cfg)
elif cfg.protocol==config.NETIO:
    print "Using NetIO protocol"
    geigerCommunication=netio(cfg)
else:
    print "Unknown protocol configured, can't run"
    sys.exit(1)

# create web server communication object
webService=webCommunication(cfg)

# main loop is in while loop
try:
    # start measuring thread
    geigerCommunication.start()

    # Now send data to web site every 30 seconds
    while(geigerCommunication.is_running==1):
        sample=geigerCommunication.getResult()

        if sample[0]!=-1:
            # sample is valid, CPM !=-1
            print "Average result:\tCPM =",sample[0],"\t",str(sample[1])
            try:
                webService.sendSample(sample)
            except Exception as e:
                print "Error communicating server:\r\n\t", str(e),"\r\n"

            print "Waiting 30 seconds"
            # actually waiting 30x1 seconds, it's has better response when CTRL+C is used, maybe will be changed in future
            for i in range(0,30):
                time.sleep(1)
        else:
            print "No samples in queue, waiting 5 seconds"
            for i in range(0,5):
                time.sleep(1)

    # well, when we will go to this line it looks like geigerCommunication thread stops running
    # most likely because of serial port problems...

except KeyboardInterrupt as e:
    print "\r\nCTRL+C pressed, exiting program\r\n\t", str(e)
    geigerCommunication.stop()
except Exception as e:
    geigerCommunication.stop()
    print "\r\nUnhandled error\r\n\t",str(e)

geigerCommunication.stop()
